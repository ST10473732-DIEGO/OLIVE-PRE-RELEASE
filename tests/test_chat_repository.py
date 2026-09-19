import tempfile
import unittest
from pathlib import Path

from olive.models import Chat
from olive.storage.chat_repository import ChatRepository


class ChatRepositoryTests(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = ChatRepository(Path(tmp) / "chats.json")
            chat = Chat(title="Test", model="local-model")
            chat.add_message("user", "hello")
            chat.project_id = "project-1"
            chat.add_message("assistant", "hi", sources=[{"filename": "guide.pdf", "page_number": 2}],
                             memory_ids=["memory-1"])
            chat.summary = "Earlier context"
            chat.summary_message_count = 1
            repo.save_all([chat])
            loaded = repo.load_all()
            self.assertEqual(loaded[chat.id].title, "Test")
            self.assertEqual(loaded[chat.id].messages[-1].content, "hi")
            self.assertEqual(loaded[chat.id].summary_message_count, 1)
            self.assertEqual(loaded[chat.id].messages[-1].sources[0]["page_number"], 2)
            self.assertEqual(loaded[chat.id].messages[-1].memory_ids, ["memory-1"])
            self.assertEqual(loaded[chat.id].project_id, "project-1")


if __name__ == "__main__":
    unittest.main()
