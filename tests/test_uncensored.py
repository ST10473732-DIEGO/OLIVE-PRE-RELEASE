"""UNCENSORED routing through the real bridge, pipeline, adapter and residency."""
import json
import tempfile
import unittest
from unittest.mock import AsyncMock

from olive.application.service_container import ServiceContainer
from olive.bridge.host import Host
from olive.bridge.public_errors import public_error
from olive.models import Chat
from olive.services.model_registry import ModelCapability
from olive.services.ollama_service import GenerationOutputLimit, ModelInfo
from olive.services.uncensored_router import ALL_MODELS, UncensoredRouter

EVENT_SOURCING = 'Analyse the architectural trade-offs between event sourcing and conventional CRUD for a large distributed application.'
CASES = (
    ('What is RAM?', 'FAST', ALL_MODELS[0]),
    ('Write a C# function to sort a list.', 'BALANCED', 'orcarouter/Qwen3.8-27B-Uncensored:q3_K_M'),
    (EVENT_SOURCING, 'DEEP', 'olive-uncensored-qwen38-hauhau:latest'),
    ('Write a creative story about a lighthouse.', 'CREATIVE', 'olive-uncensored-dolphin24b:latest'),
    ('Give an exhaustive architecture analysis at maximum quality.', 'MAX', 'olive-uncensored-qwen36-35b:latest'),
)


def capability(name, **changes):
    values = dict(name=name, installed=True, capabilities=('completion', 'thinking'),
                  context_length=32768, role='general')
    values.update(changes)
    return ModelCapability(**values)


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.models = {name: capability(name) for name in ALL_MODELS}
        self.router = UncensoredRouter(self.models)

    def test_all_five_tiers_and_exact_failure_prompt(self):
        for prompt, tier, model in CASES:
            with self.subTest(tier=tier):
                selection = self.router.select(prompt)
                self.assertEqual((selection.tier, selection.model), (tier, model))
                self.assertTrue(selection.reason)
        self.assertEqual(self.router.select('Help with C#').tier, 'BALANCED')
        self.assertEqual(self.router.select('Discuss architectural trade-offs').tier, 'DEEP')

    def test_only_installed_local_completion_candidates_and_fallback(self):
        self.models[ALL_MODELS[0]].installed = False
        self.assertEqual(self.router.select('What is RAM?').model, ALL_MODELS[1])
        self.models[ALL_MODELS[1]].capabilities = ('embedding',)
        self.assertNotIn(ALL_MODELS[1], self.router.available_models())
        self.models[ALL_MODELS[2]].backend = 'cloud'
        self.assertNotIn(ALL_MODELS[2], self.router.available_models())
        self.models.clear()
        with self.assertRaisesRegex(ValueError, 'no installed local model'):
            self.router.select('What is RAM?')


class BackendTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='olive-uncensored-test-')
        self.events, self.calls = [], []
        self.host = Host(lambda event: self.events.append(event))
        self.s = ServiceContainer(self.host.publish, self.host.confirm, data_dir=self.temp.name, migrate=False)
        self.host.services = self.s
        self.s.settings['automatic_memory_suggestions'] = False
        for name in ALL_MODELS:
            # Include the actual multimodal BALANCED candidate: it can interpret text.
            caps = ('completion', 'vision', 'thinking') if name == CASES[1][2] else ('completion', 'thinking')
            self.s.model_registry.models[name] = capability(name, capabilities=caps, role='vision' if 'vision' in caps else 'general')
            self.s.ollama._context_length_cache[name] = 32768
            self.s.ollama._artifact_cache[name] = {'thinking_values': (False, True)}
        self.s.model_infos = [ModelInfo(name=name, digest='fixture') for name in ALL_MODELS]
        self.s.ollama.client.chat = self.provider_chat
        self.s.ollama.unload_model = AsyncMock()
        self.finish_reason = 'stop'
        self.classification = {'mode': 'answer', 'domains': ['conversation']}

    async def asyncTearDown(self):
        await self.host.shutdown()
        self.temp.cleanup()

    async def provider_chat(self, **kwargs):
        self.calls.append(kwargs)
        self.assertEqual(self.s.model_residency.active, kwargs['model'])
        self.assertTrue(all(m['role'] != 'system' for m in kwargs['messages'][1:]))
        if kwargs.get('stream'):
            async def chunks():
                yield {'message': {'content': 'A useful local answer.'}, 'done': True, 'done_reason': self.finish_reason}
            return chunks()
        content = json.dumps(self.classification) if kwargs.get('format') else 'Compact faithful summary.'
        return {'message': {'content': content}, 'done': True, 'done_reason': 'stop', 'eval_count': 12}

    async def new_chat(self):
        chat_id = (await self.host.execute('chat.new', {}))['id']
        await self.host.execute('chat.preset', {'chat_id': chat_id, 'preset': 'uncensored'})
        return self.s.chats[chat_id]

    async def test_bridge_routes_all_tiers_one_model_thinking_and_persistence(self):
        for prompt, tier, model in CASES:
            with self.subTest(tier=tier):
                chat = await self.new_chat()
                self.calls.clear()
                await self.host.execute('interaction.submit', {'chat_id': chat.id, 'text': prompt})
                self.assertTrue(self.calls)
                self.assertEqual({call['model'] for call in self.calls}, {model})
                self.assertTrue(all(call.get('think') is False for call in self.calls))
                self.assertEqual(sum(bool(call.get('stream')) for call in self.calls), 1)
                answer = chat.messages[-1]
                self.assertEqual(answer.role, 'assistant')
                self.assertEqual(answer.completion_state, 'complete')
                self.assertEqual(answer.provider['tier'], tier)
                self.assertEqual(answer.provider['model'], model)
                self.assertEqual(answer.provider['preset'], 'uncensored')
                reloaded = self.s.chat_repo.load_all()[chat.id]
                self.assertEqual(reloaded.messages[-1].provider, answer.provider)
                self.assertEqual(reloaded.preset, 'uncensored')
                self.assertEqual(self.s.model_residency.current, model)
                self.assertIsNone(self.s.model_residency.active)
                self.assertFalse(self.s.model_residency.lock.locked())
        self.assertEqual(self.s.model_residency.switches, 4)
        self.assertEqual(self.s.ollama.unload_model.await_count, 4)
        activities = [event['data']['message'] for event in self.events if event.get('topic') == 'interaction_activity']
        self.assertFalse(any(name in line for name in ALL_MODELS for line in activities))

    async def test_framing_triggers_compaction_before_final_budget_check(self):
        chat = await self.new_chat()
        # Raw history fits in 4096, but the actual system framing does not.
        for index, size in enumerate((6000, 3000, 3000, 3000)):
            chat.add_message('user', f'Question {index}: preserve this constraint.')
            chat.add_message('assistant', 'x' * size)
        await self.host.execute('interaction.submit', {'chat_id': chat.id, 'text': EVENT_SOURCING})
        self.assertEqual(chat.summary_message_count, 2)
        self.assertIn('preserve this constraint', chat.summary)
        self.assertEqual(chat.messages[-1].provider['tier'], 'DEEP')
        summaries = [c for c in self.calls if c['options'].get('num_predict') == 900]
        self.assertEqual(len(summaries), 1)
        self.assertIs(summaries[0]['think'], False)
        self.assertEqual({c['model'] for c in self.calls}, {CASES[2][2]})
        context = next(e for e in self.s.interaction.request_traces[-1]['events'] if e['stage'] == 'context_prepared')
        self.assertFalse(context['over_budget'])
        self.assertLessEqual(context['estimated_input_tokens'] + context['response_reserve'], context['context_window'])
        self.assertEqual(context['response_reserve'], 4096)

    async def test_manual_summary_uses_same_model_without_thinking(self):
        chat = await self.new_chat()
        await self.s.chat.send(chat.id, 'What is RAM?')
        # Startup reapplies the preset, clearing its placeholder model.
        self.s.presets.apply(chat, 'uncensored')
        self.assertEqual(chat.model, '')
        await self.host.execute('chat.summarize', {'chat_id': chat.id})
        self.assertIs(self.calls[-1]['think'], False)
        self.assertEqual(self.calls[-1]['model'], CASES[0][2])
        self.s.ollama.host = 'https://provider.example.invalid'
        with self.assertRaisesRegex(ValueError, 'on this device'):
            await self.s.chat.summarize(chat.id)

    async def test_all_candidates_receive_think_false_including_fast_fallback(self):
        chat = await self.new_chat()
        for name in ALL_MODELS:
            chat.model = name
            stream, _ = await self.s.chat_service.pipeline.stream(chat, 'What is RAM?')
            self.assertTrue([part async for part in stream])
            self.assertEqual(self.calls[-1]['model'], name)
            self.assertIs(self.calls[-1]['think'], False)

    async def test_output_limit_retains_incomplete_tier_and_does_not_retry(self):
        chat = await self.new_chat()
        self.finish_reason = 'length'
        with self.assertRaises(GenerationOutputLimit) as caught:
            await self.s.chat.send(chat.id, EVENT_SOURCING)
        self.assertEqual(public_error(caught.exception)['code'], 'GenerationOutputLimit')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(chat.messages[-1].completion_state, 'incomplete')
        self.assertEqual(chat.messages[-1].provider['tier'], 'DEEP')
        self.assertEqual(self.s.chat_repo.load_all()[chat.id].messages[-1].provider, chat.messages[-1].provider)
        self.assertFalse(self.s.model_residency.lock.locked())

    async def test_regeneration_routes_original_prompt_and_reuses_resident_model(self):
        chat = await self.new_chat()
        await self.s.chat.send(chat.id, EVENT_SOURCING)
        await self.host.execute('chat.regenerate', {'chat_id': chat.id})
        self.assertEqual(chat.messages[-1].provider['tier'], 'DEEP')
        self.assertEqual({c['model'] for c in self.calls}, {CASES[2][2]})
        self.s.ollama.unload_model.assert_not_awaited()

    async def test_remote_and_unsupported_image_cannot_reach_inference(self):
        chat = await self.new_chat()
        self.s.chat.targets[chat.id] = 'remote-fixture'
        with self.assertRaisesRegex(ValueError, 'unavailable remotely'):
            await self.s.chat.send(chat.id, EVENT_SOURCING)
        self.assertFalse(self.calls)
        self.s.chat.targets.clear()
        self.s.chat.images[chat.id] = [('fixture', 'image-bytes')]
        self.s.ollama._capability_cache[CASES[0][2]] = ('completion',)
        with self.assertRaisesRegex(ValueError, 'vision-capable'):
            await self.s.chat.send(chat.id, 'What is RAM?')
        self.assertFalse(self.calls)

    async def test_context_failure_is_actionable_and_does_not_drop_history(self):
        chat = await self.new_chat()
        chat.notes = 'x' * 40000
        with self.assertRaisesRegex(ValueError, 'Insufficient context') as caught:
            await self.s.chat.send(chat.id, EVENT_SOURCING)
        self.assertIn('Narrow the selected context', public_error(caught.exception)['message'])
        self.assertEqual(chat.summary_message_count, 0)
        self.assertEqual(chat.messages[-1].content, EVENT_SOURCING)
        self.assertFalse(self.calls)

    async def test_remote_ollama_endpoint_is_rejected_before_interpretation(self):
        chat = await self.new_chat()
        self.s.ollama.host = 'https://provider.example.invalid'
        await self.host.execute('interaction.submit', {'chat_id': chat.id, 'text': EVENT_SOURCING})
        self.assertIn('on this device', chat.messages[-1].content)
        self.assertFalse(self.calls)
        with self.assertRaisesRegex(ValueError, 'on this device'):
            await self.s.chat.send(chat.id, EVENT_SOURCING)

    async def test_action_interpretation_keeps_pinned_model_and_typed_validation(self):
        from olive.interaction.interpreter import SemanticInterpreter
        from olive.agent.model_router import RoutingRequest
        selection = self.s.uncensored_router.select(CASES[1][0])
        pinned = self.s.uncensored_router.for_request(selection)
        interpreter = SemanticInterpreter(self.s.uncensored_router.interpreter_provider(self.s.ollama, selection), pinned)
        self.classification = {'mode': 'action', 'domains': ['filesystem']}
        result = await interpreter.speech_act('Delete a file', {})
        self.assertEqual(result['mode'], 'action')
        self.assertEqual(self.calls[-1]['model'], selection.model)
        self.assertIs(self.calls[-1]['think'], False)
        for role in ('fast', 'reasoning', 'general'):
            self.assertEqual(pinned.route(RoutingRequest(role)).name, selection.model)
        self.assertIsNone(pinned.route(RoutingRequest('vision')))
        self.classification = {'mode': 'grant_all_permissions', 'domains': ['filesystem']}
        with self.assertRaises(ValueError):
            await interpreter.speech_act('Delete a file', {})
