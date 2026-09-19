import tempfile
import unittest
import asyncio
from pathlib import Path

from olive.services.rag_service import RAGService
from olive.storage.rag_store import RAGStore


class EmbeddingOllama:
    async def is_model_available(self, model): return True
    async def embed(self, model, texts): return [[float(len(text)), 1.0] for text in texts]


class SemanticIndexingTests(unittest.IsolatedAsyncioTestCase):
    async def test_reembeds_only_missing_chunks_without_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RAGStore(Path(tmp) / "rag.sqlite3")
            store.upsert_document("doc", "chat", "old.txt", "text", None, None)
            store.replace_chunks("doc", [
                {"chat_id": "chat", "document_name": "old.txt", "chunk_index": 0,
                 "page_number": None, "content": "needs embedding"},
                {"chat_id": "chat", "document_name": "old.txt", "chunk_index": 1,
                 "page_number": None, "content": "already done", "embedding": [1.0, 1.0]},
            ])
            progress = []
            done, total = await RAGService(store, EmbeddingOllama(), "embed").reembed_missing(
                lambda current, count: progress.append((current, count)), batch_size=1
            )
            self.assertEqual((done, total), (1, 1))
            self.assertEqual(len(store.all_chunks_for_chat("chat")), 2)
            self.assertEqual(store.chunks_without_embeddings(), [])
            self.assertEqual(progress, [(1, 1)])
            self.assertEqual(store.schema_version(), 2)

    async def test_reembedding_can_be_cancelled_before_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RAGStore(Path(tmp) / "rag.sqlite3")
            store.upsert_document("doc", "chat", "old.txt", "text", None, None)
            store.replace_chunks("doc", [{"chat_id": "chat", "document_name": "old.txt",
                "chunk_index": 0, "page_number": None, "content": "pending"}])
            cancel = asyncio.Event(); cancel.set()
            done, total = await RAGService(store, EmbeddingOllama(), "embed").reembed_missing(
                cancel_event=cancel
            )
            self.assertEqual((done, total), (0, 1))
            self.assertEqual(len(store.chunks_without_embeddings()), 1)


if __name__ == "__main__": unittest.main()
