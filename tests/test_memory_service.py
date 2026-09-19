import tempfile
import unittest
from pathlib import Path

from olive.services.memory_service import MemoryService
from olive.storage.memory_repository import MemoryRepository


class MemoryServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = MemoryRepository(Path(self.temp.name) / "memories.json")
        self.service = MemoryService(self.repo)

    def tearDown(self):
        self.temp.cleanup()

    def test_add_persist_search_update_and_delete(self):
        memory = self.service.add("User prefers concise Python answers", "preference", "chat-1", 4)
        loaded = self.repo.load_all()[memory.id]
        self.assertEqual(loaded.source_chat_id, "chat-1")
        self.assertEqual(self.service.search("Python preference")[0][0].id, memory.id)
        updated = self.service.update(memory.id, content="User prefers tested Python answers")
        self.assertIn("tested", updated.content)
        self.assertTrue(self.service.delete(memory.id))
        self.assertEqual(self.service.list_all(), [])

    def test_exact_normalized_duplicates_are_not_added(self):
        first = self.service.add("Project uses Ollama.")
        second = self.service.add(" project uses ollama ")
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(self.service.list_all()), 1)

    def test_irrelevant_memories_are_not_returned(self):
        self.service.add("The project uses SQLite")
        self.assertEqual(self.service.search("gardening tomatoes"), [])


if __name__ == "__main__":
    unittest.main()
