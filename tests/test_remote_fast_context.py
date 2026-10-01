"""Remote FAST context budget: an empty phone chat gets the same budget as desktop FAST.

Regression: olive-chat/1 FAST reserved its full 4,096-token answer cap inside
FAST's 4,096-token role window, so even "hi" in a new chat was refused with
`input_too_large`. Desktop Chat caps the answer reserve at half the window.

The production preset catalog, desktop GenerationPipeline, RemoteChatRuntime,
RemoteChatService and Connect Direct/World transports run here; only Ollama is
faked, and its window lookup is the production rule (advertised context capped
by the default role policy). No model runs and no private content is used.
"""
import asyncio
import threading
import time
import unittest
import uuid
from types import SimpleNamespace

from olive.connect import chat_protocol as cp
from olive.connect.contracts import ConnectError
from olive.models import Chat, Message
from olive.services.context_service import ContextService
from olive.services.generation_pipeline import GenerationPipeline
from olive.services.model_policy import REQUEST_ROLE
from olive.services.model_residency_service import ModelResidencyService
from olive.services.ollama_service import OllamaService
from olive.services.presets import PRESETS, PresetCatalog
from olive.services.remote_chat_runtime import RemoteChatRuntime
from olive.services.remote_inference_runtime import RemoteInferenceRuntime
from olive.services.uncensored_router import UncensoredRouter
from tests.test_connect_network import until
from tests.test_connect_world import WorldIntegrationBase
from tests.test_remote_chat_runtime import Recorder, job

ADVERTISED = 40960   # qwen3:8b's advertised context; the FAST role policy caps it to 4,096.


def reply(text):
    prefix = 'Reply with exactly: '
    return text[len(prefix):] if text.startswith(prefix) else 'ok'


class RoleOllama:
    """Ollama at its edge. The window lookup is OllamaService's own, with the default policy."""
    host = 'http://127.0.0.1:11434'
    effective_context_length = OllamaService.effective_context_length

    def __init__(self, advertised=ADVERTISED):
        self.advertised, self.calls = advertised, []
        self.residency = ModelResidencyService(self)

    async def context_length(self, model):
        return self.advertised

    async def is_model_available(self, model):
        return True

    def chat_stream(self, model, messages, options=None, think=None, **_):
        self.calls.append(dict(model=model, messages=messages, options=dict(options or {}), role=REQUEST_ROLE.get()))
        async def stream():
            yield reply(messages[-1]['content'])
        return stream()


class Model:
    def __init__(self, name):
        self.name, self.installed, self.capabilities = name, True, ['completion']
    supports_embeddings = supports_vision = False


def services(ollama=None):
    names = [PRESETS[k]['model'] for k in ('fast', 'normal', 'max', 'deep', 'now')]
    registry = SimpleNamespace(get={n: Model(n) for n in names}.get)
    infos = [SimpleNamespace(name=n, digest=PRESETS['max']['pinned_digest'] if n == PRESETS['max']['model'] else 'd')
             for n in names]
    s = SimpleNamespace(model_registry=registry, model_infos=infos, ollama=ollama or RoleOllama(),
                        now=SimpleNamespace(status=lambda: dict(available=False, status='', inference_status='',
                                                                retrieval_status='')))
    s.uncensored_router = UncensoredRouter(registry)
    s.presets = PresetCatalog(s)
    return s


class RemoteFastContextTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.s = services()
        self.runtime = RemoteChatRuntime(self.s)

    async def desktop(self, text, history=()):
        """Desktop FAST in a new chat: the real preset selection and Chat pipeline."""
        chat = Chat()
        chat.messages = [Message(role=r, content=c) for r, c in history]
        self.s.presets.apply(chat, 'fast')
        token = REQUEST_ROLE.set('general')
        try:
            self.s.presets.require(chat)   # Sets the FAST role, as ChatService does.
            stream, prepared = await GenerationPipeline(self.s.ollama, rag=None).stream(chat, text)
            return ''.join([part async for part in stream]), prepared, self.s.ollama.calls[-1]
        finally:
            REQUEST_ROLE.reset(token)

    async def remote(self, text, mode='fast', history=(), conversation=None):
        sink = Recorder()
        work = job(mode, text, conversation=conversation or str(uuid.uuid4()))
        work.arguments['messages'] = [dict(role=r, content=c) for r, c in history] + [dict(role='user', content=text)]
        await self.runtime.run(work, sink)
        return sink.out, self.s.ollama.calls[-1]

    async def test_desktop_fast_new_chat_succeeds(self):
        text, prepared, call = await self.desktop('Reply with exactly: fast-desktop-ok')
        self.assertEqual(text, 'fast-desktop-ok')
        self.assertEqual(call['model'], 'qwen3:8b')
        self.assertEqual((call['options']['num_ctx'], call['options']['num_predict']), (4096, 2048))

    async def test_remote_fast_new_chat_hi_succeeds_with_the_desktop_budget(self):
        _, prepared, desktop = await self.desktop('hi')
        text, call = await self.remote('hi')
        self.assertEqual(text, 'ok')
        self.assertEqual((call['model'], call['role']), (desktop['model'], 'fast'))
        self.assertEqual(call['options']['num_predict'], prepared.context.response_reserve)
        self.assertEqual(call['options']['num_predict'], 2048)
        token = REQUEST_ROLE.set('fast')
        try:
            self.assertEqual(await self.s.ollama.effective_context_length(call['model']), desktop['options']['num_ctx'])
        finally:
            REQUEST_ROLE.reset(token)

    async def test_fast_selects_the_same_model_locally_and_remotely(self):
        _, _, desktop = await self.desktop('hi')
        _, remote = await self.remote('hi')
        self.assertEqual(desktop['model'], remote['model'])
        self.assertEqual(remote['model'], self.s.presets.get('fast')['model'])
        self.assertEqual(remote['model'], PRESETS['fast']['model'])

    async def test_new_remote_chat_carries_no_stale_history_or_hidden_context(self):
        long_ago = [('user', 'earlier question ' * 20), ('assistant', 'earlier answer ' * 20)] * 3
        await self.remote('follow-up', history=long_ago, conversation=str(uuid.uuid4()))
        _, call = await self.remote('hi', conversation=str(uuid.uuid4()))
        self.assertEqual([m['role'] for m in call['messages']], ['system', 'user'])
        self.assertEqual(call['messages'][-1]['content'], 'hi')

    async def test_context_metadata_is_coherent_after_a_model_refresh(self):
        for advertised in (ADVERTISED, 2048, ADVERTISED):   # e.g. re-pulled with a different window
            self.s.ollama.advertised = advertised
            _, prepared, desktop = await self.desktop('hi')
            _, remote = await self.remote('hi')
            self.assertEqual(remote['options']['num_predict'], prepared.context.response_reserve, advertised)
            self.assertEqual(desktop['options']['num_ctx'], min(advertised, 4096))

    async def test_genuinely_over_limit_fast_request_is_still_refused(self):
        huge = 'synthetic words ' * 625                        # ~10,000 bytes, ~2,500 tokens: wire-valid
        calls = len(self.s.ollama.calls)
        with self.assertRaises(ConnectError) as caught:
            await self.remote(huge)
        self.assertEqual(str(caught.exception), 'input_too_large')
        self.assertEqual(len(self.s.ollama.calls), calls, 'refused before the provider')
        with self.assertRaises(ValueError):                    # Desktop FAST refuses the same request.
            await self.desktop(huge)

    async def test_long_fast_history_keeps_the_newest_whole_turns(self):
        history = [(('user', 'assistant')[i % 2], f'turn {i} ' + 'filler ' * 110) for i in range(10)]
        _, call = await self.remote('hi', history=history)
        sent = call['messages'][1:]
        self.assertLess(len(sent), len(history) + 1, 'older turns were omitted')
        self.assertEqual(sent[0]['role'], 'user')
        self.assertEqual(sent[-1]['content'], 'hi')
        self.assertEqual(sent[:-1], [dict(role=r, content=c) for r, c in history[-(len(sent) - 1):]])

    async def test_normal_max_and_v1_budgets_are_unchanged(self):
        for mode in ('normal', 'max'):
            _, call = await self.remote('hi', mode=mode)
            self.assertEqual(call['options']['num_predict'], 4096, mode)
        v1 = RemoteInferenceRuntime(self.s.presets, self.s.ollama)
        for requested in (2048, 16):                           # olive-inference/1 never gets more than it asked for
            parts = [p async for p in v1.stream(dict(preset='fast', messages=[dict(role='user', content='hi')],
                                                     max_tokens=requested))]
            self.assertEqual((parts, self.s.ollama.calls[-1]['options']['num_predict']), (['ok'], requested))


class RemoteFastOverConnectTests(WorldIntegrationBase):
    """olive-chat/1 FAST through the real Connect TLS session, Direct and forced World."""
    def attach(self):
        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self.loop.run_forever, name='test-fast-loop', daemon=True)
        self.loop_thread.start()
        self.s = services()
        self.chat = self.desk.attach_chat(RemoteChatRuntime(self.s, self.loop), self.loop)

    def setUp(self):
        super().setUp()
        self.desk.set_permission(self.phone.local_id, 'models.remote', 'allow')

    def tearDown(self):
        asyncio.run_coroutine_threadsafe(self.chat.shutdown(), self.loop).result(10)
        super().tearDown()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.loop_thread.join(5)
        self.loop.close()

    def call(self, channel, op, args):
        raw = cp.request(self.phone.local_id, self.desk.local_id, op, args, now=int(time.time()))
        return cp.unpack(channel.chat_request(raw))[0]

    def fast(self, channel, text):
        args = dict(job_id=str(uuid.uuid4()), conversation_id=str(uuid.uuid4()), mode='fast', voice=None,
                    messages=[dict(role='user', content=text)], attachments=[])
        args['input_fingerprint'] = cp.start_fingerprint(args)
        before = len(self.s.ollama.calls)
        value = self.call(channel, 'start', args)
        self.assertIsNone(value['error'], value)
        after, out, deadline = 0, '', time.monotonic() + 15
        while time.monotonic() < deadline:
            result = self.call(channel, 'poll', dict(job_id=args['job_id'], after=after))['result']
            out += result['text']; after += len(result['text'].encode())
            if result['state'] in cp.TERMINAL and after >= result['total']:
                self.assertEqual(len(self.s.ollama.calls), before + 1, 'exactly one model run per request')
                return result, out
            time.sleep(.05)
        raise AssertionError('FAST did not finish')

    def assert_fast(self, result, text, expected):
        self.assertEqual((result['state'], result.get('error'), text), ('completed', None, expected), result)
        call = self.s.ollama.calls[-1]
        self.assertEqual((call['model'], call['role'], call['options']['num_predict']), ('qwen3:8b', 'fast', 2048))

    def test_fast_new_chat_over_direct(self):
        channel = self.direct()
        self.assertEqual(channel.path, 'direct')
        self.assert_fast(*self.fast(channel, 'hi'), 'ok')
        self.assert_fast(*self.fast(channel, 'Reply with exactly: fast-direct-ok'), 'fast-direct-ok')

    def test_fast_new_chat_over_forced_world(self):
        channel = self.world_connect(self.provisioned())
        self.assertEqual(channel.path, 'world')
        until(lambda: self.nd.status(self.phone.local_id)['connection'] == 'world')
        self.assert_fast(*self.fast(channel, 'hi'), 'ok')
        self.assert_fast(*self.fast(channel, 'Reply with exactly: fast-world-ok'), 'fast-world-ok')
        relay_view = b''.join(p for _, p in self.seen)
        self.assertNotIn(b'fast-world-ok', relay_view)


if __name__ == '__main__':
    unittest.main()
