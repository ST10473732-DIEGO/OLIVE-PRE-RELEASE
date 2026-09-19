import tempfile
import unittest
from pathlib import Path

from olive.storage.rag_store import RAGStore, cosine_similarity


class RAGStoreTests(unittest.TestCase):
    def test_lexical_search(self):
        # Cleanup is part of the assertion on Windows: an open SQLite handle makes
        # TemporaryDirectory.__exit__ fail with PermissionError.
        with tempfile.TemporaryDirectory() as tmp:
            store = RAGStore(Path(tmp) / "rag.sqlite3")
            store.upsert_document("doc1", "chat1", "guide.pdf", "pdf", 1, None)
            store.replace_chunks(
                "doc1",
                [
                    {
                        "chat_id": "chat1",
                        "document_name": "guide.pdf",
                        "chunk_index": 0,
                        "page_number": 1,
                        "content": "Collision avoidance systems improve mine vehicle safety.",
                    },
                    {
                        "chat_id": "chat1",
                        "document_name": "guide.pdf",
                        "chunk_index": 1,
                        "page_number": 1,
                        "content": "Unrelated accounting text.",
                    },
                ],
            )
            results = store.lexical_search("chat1", "mine vehicle collision safety", 5)
            self.assertTrue(results)
            self.assertIn("Collision avoidance", results[0][0].content)
            self.assertEqual(results[0][0].document_id, "doc1")
            self.assertEqual(results[0][0].source_type, "pdf")

    def test_database_can_be_removed_after_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rag.sqlite3"
            store = RAGStore(path)
            store.upsert_document("doc1", "chat1", "guide.pdf", "pdf", 1, None)
            path.unlink()
            self.assertFalse(path.exists())

    def test_cosine_similarity(self):
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0)
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_atomic_document_replacement_creates_parent_and_replaces_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RAGStore(Path(tmp) / "rag.sqlite3")
            first = [{"chat_id": "chat1", "document_name": "notes.txt", "chunk_index": 0,
                      "page_number": None, "content": "old content"}]
            store.replace_document("doc1", "chat1", "notes.txt", "txt", 1, None, first)
            replacement = [{"chat_id": "chat1", "document_name": "notes.txt", "chunk_index": 0,
                            "page_number": None, "content": "replacement content"}]
            store.replace_document("doc1", "chat1", "notes.txt", "txt", 1, None, replacement)
            chunks = store.all_chunks_for_chat("chat1")
            self.assertEqual([chunk.content for chunk in chunks], ["replacement content"])
            self.assertTrue(store.integrity_check()["ok"])


if __name__ == "__main__":
    unittest.main()
