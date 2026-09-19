import tempfile
import unittest
from pathlib import Path

from olive.services.memory_service import MemoryService
from olive.services.memory_suggestion_service import MemorySuggestionService
from olive.storage.memory_repository import MemoryRepository


class MemorySuggestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        memory = MemoryService(MemoryRepository(Path(self.temp.name) / "memory.json"))
        self.memory = memory
        self.service = MemorySuggestionService(memory)

    def tearDown(self): self.temp.cleanup()

    def test_requires_approval_before_persistence(self):
        suggestions = self.service.suggest("I prefer concise technical answers", "chat", 2)
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(self.memory.list_all(), [])
        saved = self.service.approve(suggestions[0])
        self.assertEqual(self.memory.list_all()[0].id, saved.id)

    def test_rejects_secrets_and_one_off_questions(self):
        self.assertEqual(self.service.suggest("Remember that my API key is secret-value", "chat", 1), [])
        self.assertEqual(self.service.suggest("What is the capital of France?", "chat", 1), [])

    def test_deduplicates_existing_memory(self):
        text = "Our project uses Ollama for local inference"
        self.memory.add(text, "project")
        self.assertEqual(self.service.suggest(text, "chat", 3), [])


if __name__ == "__main__": unittest.main()
