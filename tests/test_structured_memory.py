import tempfile
import unittest
from pathlib import Path

from olive.services.memory_service import MemoryService
from olive.services.memory_suggestion_service import MemorySuggestionService
from olive.storage.memory_repository import MemoryRepository


class FakeOllama:
    def __init__(self, response): self.response = response
    async def chat_once(self, *args, **kwargs): return self.response


class StructuredMemoryTests(unittest.IsolatedAsyncioTestCase):
    def service(self, response):
        self.temp = tempfile.TemporaryDirectory()
        memory = MemoryService(MemoryRepository(Path(self.temp.name) / "memory.json"))
        return memory, MemorySuggestionService(memory, FakeOllama(response))

    async def test_valid_proposal_requires_review_and_preserves_source_id(self):
        memory, service = self.service(
            '{"memory":"User prefers Python examples","category":"preference",'
            '"confidence":0.9,"reason":"Stable coding preference"}'
        )
        proposals = await service.propose_structured("I prefer Python examples", "local", "chat", "msg", 2)
        self.assertEqual(proposals[0].source_message_id, "msg")
        self.assertEqual(memory.list_all(), [])
        service.approve(proposals[0])
        self.assertEqual(memory.list_all()[0].source_message_id, "msg")
        self.temp.cleanup()

    async def test_invalid_secret_temporary_and_malformed_proposals_are_rejected(self):
        for raw in ["not json", '{"memory":"API key is abc","category":"fact","confidence":0.9,"reason":"x"}',
                    '{"memory":"Meeting tomorrow","category":"fact","confidence":0.9,"reason":"x"}']:
            _, service = self.service(raw)
            self.assertEqual(await service.propose_structured("durable project info", "local", "c", "m", 0), [])
            self.temp.cleanup()


if __name__ == "__main__": unittest.main()
