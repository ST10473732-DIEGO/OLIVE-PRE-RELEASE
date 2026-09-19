import tempfile
import unittest
from pathlib import Path

from olive.models import Chat
from olive.storage.rag_store import RAGStore


class MigrationTests(unittest.TestCase):
    def test_rag_schema_initialization_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rag.sqlite3"
            first = RAGStore(path)
            first.upsert_document("doc", "chat", "old.txt", "text", None, None)
            second = RAGStore(path)
            self.assertEqual(second.schema_version(), 2)
            self.assertEqual(second.document_stats("chat")[0]["name"], "old.txt")
            self.assertTrue(second.integrity_check()["ok"])

    def test_v21_chat_without_new_metadata_loads_unchanged(self):
        chat = Chat.from_dict({"id": "old", "title": "Existing", "messages": [
            {"role": "assistant", "content": "kept"}
        ], "documents": [{"id": "doc", "name": "old.txt", "indexed": True}]})
        self.assertEqual(chat.messages[0].content, "kept")
        self.assertEqual(chat.messages[0].sources, [])
        self.assertEqual(chat.documents[0].chunk_count, 0)


if __name__ == "__main__": unittest.main()
