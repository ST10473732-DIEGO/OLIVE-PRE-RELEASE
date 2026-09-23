import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from olive.services.ollama_service import OllamaService


class AnswerStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_early_end_after_content_is_not_success(self):
        with self.assertRaisesRegex(RuntimeError, 'stopped before completing'):
            await self.collect([{'message': {'content': 'partial answer'}}])

    async def test_empty_stream_is_a_useful_error(self):
        with self.assertRaisesRegex(RuntimeError, 'no answer content'):
            await self.collect([])

    async def collect(self, parts):
        async def stream():
            for part in parts:
                yield part
        service = OllamaService()
        service.client = SimpleNamespace(chat=AsyncMock(return_value=stream()))
        return [token async for token in service.chat_stream("fixture", [])]

    async def test_reasoning_only_is_an_error_not_a_completed_answer(self):
        with self.assertRaisesRegex(RuntimeError, "no answer content"):
            await self.collect([{"message": {"thinking": "internal"}}, {"done": True}])
        with self.assertRaisesRegex(RuntimeError, "no answer content"):
            await self.collect([{"message": {"content": " \n"}}, {"done": True}])

    async def test_truncated_content_is_not_reported_as_complete(self):
        with self.assertRaisesRegex(RuntimeError, "output limit"):
            await self.collect([{"message": {"content": "partial"}, "done_reason": "length"}])

    async def test_final_content_is_retained_and_reasoning_never_rendered(self):
        self.assertEqual(await self.collect([
            {"message": {"thinking": "private"}},
            {"message": {"content": "complete "}},
            {"message": {"content": "answer"}, "done": True},
        ]), ["complete ", "answer"])

    async def test_sdk_malformed_response_and_missing_model_recover_without_substitution(self):
        import json
        import httpx
        import ollama
        calls = []

        def respond(request):
            model = json.loads(request.content)['model']
            calls.append(model)
            if len(calls) == 1:
                return httpx.Response(200, content=b'{broken-json\n')
            if model == 'missing-fixture':
                return httpx.Response(404, json={'error': 'model missing-fixture not found'})
            return httpx.Response(200, content=b'{"message":{"role":"assistant","content":"Recovered answer"},"done":true}\n')

        service = OllamaService()
        service.client = ollama.AsyncClient(host='http://fixture.invalid', transport=httpx.MockTransport(respond))
        with self.assertRaises(ValueError):
            _ = [token async for token in service.chat_stream('fixture', [])]
        with self.assertRaises(ollama.ResponseError) as failure:
            _ = [token async for token in service.chat_stream('missing-fixture', [])]
        self.assertEqual(failure.exception.status_code, 404)
        self.assertEqual([token async for token in service.chat_stream('fixture', [])], ['Recovered answer'])
        self.assertEqual(calls, ['fixture', 'missing-fixture', 'fixture'])

class MeasuredAnswerTests(unittest.IsolatedAsyncioTestCase):
    async def run_parts(self, parts):
        async def stream():
            for part in parts:
                yield part
        service = OllamaService()
        service.client = SimpleNamespace(chat=AsyncMock(return_value=stream()))
        return await service.chat_measured('fixture', [], stream=True)

    async def test_measured_responses_reject_empty_truncated_and_incomplete(self):
        for parts in ([], [{'message': {'thinking': 'secret'}, 'done': True}],
                      [{'message': {'content': 'partial'}}],
                      [{'message': {'content': 'partial'}, 'done': True, 'done_reason': 'length'}]):
            with self.subTest(parts=parts), self.assertRaises(RuntimeError):
                await self.run_parts(parts)

    async def test_measured_reasoning_is_never_returned(self):
        answer = await self.run_parts([{'message': {'thinking': 'private trace'}},
                                      {'message': {'content': 'café'}},
                                      {'message': {'content': ' ✓'}, 'done': True}])
        self.assertEqual(answer['content'], 'café ✓')
        self.assertNotIn('private trace', str(answer))
        self.assertIsNotNone(answer['first_token_ms'])
        self.assertIsNotNone(answer['reasoning_stream_ms'])

    async def test_nonstream_failure_is_not_success(self):
        service = OllamaService()
        service.client = SimpleNamespace(chat=AsyncMock(return_value={'done': False, 'message': {'content': 'partial'}}))
        with self.assertRaises(RuntimeError):
            await service.chat_once('fixture', [])

    def test_known_thinking_controls_are_strict(self):
        service = OllamaService()
        service._artifact_cache['fixture'] = {'thinking_values': ('low', 'high')}
        with self.assertRaises(ValueError):
            service._thinking('fixture', False)
        self.assertEqual(service._thinking('fixture', 'low'), {'think': 'low'})

    async def test_stream_cleanup_holds_residency_until_provider_closes(self):
        import asyncio
        from olive.services.model_residency_service import ModelResidencyService
        closing, release = asyncio.Event(), asyncio.Event()
        class Stream:
            def __aiter__(self): return self
            async def __anext__(self): raise StopAsyncIteration
            async def aclose(self):
                closing.set()
                await release.wait()
        service = OllamaService()
        service.client = SimpleNamespace(chat=AsyncMock(return_value=Stream()))
        service.residency = ModelResidencyService(service)
        task = asyncio.create_task(service.chat_measured('fixture', [], stream=True))
        await closing.wait()
        self.assertTrue(service.residency.lock.locked())
        self.assertEqual(service.residency.active, 'fixture')
        release.set()
        with self.assertRaises(RuntimeError): await task
        self.assertFalse(service.residency.lock.locked())

class BoundedStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_inactivity_closes_owned_stream_and_next_request_works(self):
        import asyncio
        from olive.services.ollama_service import StreamBudgets
        closed = asyncio.Event()
        async def stalled():
            try:
                yield {'message': {'thinking': 'private'}}
                await asyncio.Event().wait()
            finally:
                closed.set()
        async def healthy():
            yield {'message': {'content': 'Recovered'}, 'done': True}
        service = OllamaService()
        service.stream_budgets = StreamBudgets(1, .02, 1)
        service.client = SimpleNamespace(chat=AsyncMock(side_effect=[stalled(), healthy()]))
        with self.assertRaises(TimeoutError):
            await service.chat_measured('fixture', [], stream=True)
        self.assertTrue(closed.is_set())
        self.assertEqual((await service.chat_measured('fixture', [], stream=True))['content'], 'Recovered')

    async def test_sdk_reassembles_fragmented_utf8_without_reasoning_leak(self):
        import httpx
        import ollama
        import json
        raw = (json.dumps({'message': {'role':'assistant','content':'café ✓','thinking':'hidden'},'done':True},ensure_ascii=False)+'\n').encode()
        class Bytes(httpx.AsyncByteStream):
            async def __aiter__(self):
                for byte in raw:
                    yield bytes([byte])
        service = OllamaService()
        service.client = ollama.AsyncClient(host='http://fixture.invalid',transport=httpx.MockTransport(lambda _:httpx.Response(200,stream=Bytes())))
        self.assertEqual([s async for s in service.chat_stream('fixture',[])], ['café ✓'])
