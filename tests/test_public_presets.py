import tempfile
import unittest
from pathlib import Path
from olive.application.service_container import ServiceContainer
from olive.agent.confirmation_service import ConfirmationResponse
from olive.models import Chat, Message
from olive.services.model_registry import ModelCapability
from olive.services.presets import PRESETS


class PublicPresetTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        async def deny(_): return ConfirmationResponse(False)
        self.s = ServiceContainer(lambda *a: None, deny, Path(self.temp.name), migrate=False)
        for name in {p['model'] for p in PRESETS.values()} - {''}:
            self.s.model_registry.models[name] = ModelCapability(name, True, ('completion',), 32768, 'general')

    async def asyncTearDown(self):
        await self.s.shutdown()
        self.temp.cleanup()

    def test_nine_names_preserve_provider_and_new_chat_normal(self):
        rows = self.s.presets.list()
        self.assertEqual([p['name'] for p in rows], ['OLIVE FAST', 'OLIVE NORMAL', 'OLIVE MAX', 'OLIVE UNCENSORED', 'OLIVE NOW',
                                                     'OLIVE DEEP', 'OLIVE REIMAGINE', 'OLIVE AUDIO', 'OLIVE VIDEO'])
        chat = self.s.chat.new()
        self.assertEqual((chat['preset'], chat['model']), ('normal', 'gpt-oss:20b'))
        media = {p['id']: p for p in rows[-3:]}
        for key in ('reimagine', 'audio', 'video'):
            # No engine is discovered in an isolated profile: honest setup, no capability claims.
            self.assertFalse(media[key]['available'])
            self.assertTrue(media[key]['status'].startswith('Needs setup'), media[key]['status'])
            self.assertEqual(media[key]['capabilities'], [])
            self.assertEqual(media[key]['model'], '')

    async def test_unconfigured_media_cannot_fall_back_to_chat(self):
        chat_id = self.s.current_chat_id
        from unittest.mock import AsyncMock
        self.s.ollama.chat_stream = AsyncMock(side_effect=AssertionError('text inference must not run'))
        for preset, message in [('reimagine', 'REIMAGINE needs setup'), ('video', 'VIDEO needs setup'), ('audio', 'AUDIO needs setup')]:
            self.s.chat.update(chat_id, preset=preset)
            with self.assertRaisesRegex(ValueError, message):
                await self.s.chat.send(chat_id, 'Say: generate something')
            self.assertEqual(self.s.chats[chat_id].messages[-1].content, 'Say: generate something')
            self.assertFalse(self.s.chat.generations)
        self.assertFalse(self.s.run_service.sessions)
        self.assertFalse(self.s.agent_task_repo.load_all())
        self.assertFalse(any(m.role == 'assistant' for m in self.s.chats[chat_id].messages))

    def test_legacy_provider_and_incomplete_state_roundtrip(self):
        chat = Chat.from_dict({'id': 'legacy', 'model': 'custom-local:latest', 'messages': [{'role': 'assistant', 'content': 'partial', 'completion_state': 'incomplete'}]})
        self.s.presets.require(chat)
        self.assertEqual(chat.model, 'custom-local:latest')
        self.assertEqual(Chat.from_dict(chat.to_dict()).messages[0].completion_state, 'incomplete')
        self.assertEqual(Message.from_dict({'content': 'old'}).completion_state, 'complete')

    def test_profile_and_contacts_storage_stay_internal(self):
        names = [d.name for d in self.s.tool_registry.definitions()]
        self.assertFalse(any(n.startswith(('profile.', 'contacts.')) for n in names))
        self.assertIsNotNone(self.s.tool_registry.get('contacts.get'))
        self.assertTrue(self.s.personal.records.profile()['timezone'])
        self.assertEqual(self.s.settings['preferred_name'], '')  # Unset until first-run setup asks.

    async def test_deep_requires_actual_vision_and_preserves_native_results(self):
        chat = self.s.chats[self.s.current_chat_id]
        pipeline = self.s.chat_service.pipeline.deep
        self.assertEqual(await pipeline.supplement(chat, 'Explain this paragraph', [], []), [])
        with self.assertRaisesRegex(ValueError, 'vision-capable'):
            await pipeline.supplement(chat, 'Read the attached image', ['synthetic'], [])
        from unittest.mock import AsyncMock
        self.s.model_registry.models['qwen3-vl:8b'] = ModelCapability('qwen3-vl:8b', True, ('vision',), 8192, 'vision')
        self.s.ollama.chat_measured = AsyncMock(return_value={'content': 'SAVE', 'done_reason': 'stop'})
        self.s.chat.images[chat.id] = [('button.png', 'synthetic')]
        results = await pipeline.supplement(chat, 'Read the image', ['synthetic'], [])
        self.assertEqual(results[0].document_name, 'button.png')
        self.assertEqual(results[0].origin_type, 'vision_interpretation:qwen3-vl:8b')
        self.assertEqual(self.s.ollama.chat_measured.await_args.args[0], 'qwen3-vl:8b')
