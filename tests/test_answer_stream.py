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
