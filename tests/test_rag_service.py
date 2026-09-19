import tempfile
import unittest
from pathlib import Path

from olive.services.rag_service import RAGService
from olive.storage.rag_store import RAGStore


class DummyOllama:
    def __init__(self, available=False):
        self.available = available

    async def is_model_available(self, model):
        return self.available

    async def embed(self, model, texts):
        return [[1.0, 0.0] for _ in texts]


class RAGServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_document_fallback_is_bounded_and_chat_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RAGStore(Path(tmp) / "rag.sqlite3")
            for doc, chat in (("selected", "chat"), ("private", "other")):
                store.upsert_document(doc, chat, doc + ".pdf", "pdf", 20, None)
                store.replace_chunks(doc, [{"chat_id": chat, "document_name": doc + ".pdf",
                    "chunk_index": index, "page_number": index + 1, "content": "violet " * 1000}
                    for index in range(20)])
            service = RAGService(store, DummyOllama(), "missing")
            results = await service.retrieve_document("chat", "selected", "Summarize it", limit=3)
            self.assertEqual(len(results), 3)
            self.assertTrue(all(r.document_id == "selected" and len(r.content) <= 4000 for r in results))
            self.assertEqual(results[0].page_number, 1)
            self.assertEqual(await service.retrieve_document("chat", "private", "Summarize it"), [])

    async def test_lexical_retrieval_preserves_metadata_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RAGStore(Path(tmp) / "rag.sqlite3")
            store.upsert_document("doc", "chat", "manual.pdf", "pdf", 12, None)
            base = "hydraulic pump pressure troubleshooting procedure"
            store.replace_chunks("doc", [
                {"chat_id": "chat", "document_name": "manual.pdf", "chunk_index": 3,
                 "page_number": 8, "content": base},
                {"chat_id": "chat", "document_name": "manual.pdf", "chunk_index": 4,
                 "page_number": 9, "content": base + " "},
            ])
            service = RAGService(store, DummyOllama(), "missing-embed")
            results = await service.retrieve("chat", "hydraulic pump pressure", limit=5)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].document_id, "doc")
            self.assertEqual(results[0].chunk_index, 3)
            self.assertEqual(results[0].source_type, "pdf")
            self.assertEqual(results[0].source_label, "manual.pdf — page 8")
            self.assertNotIn("embedding", results[0].source_dict())
            self.assertGreater(results[0].score, 0)

    async def test_semantic_results_can_recover_lexically_unmatched_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RAGStore(Path(tmp) / "rag.sqlite3")
            store.upsert_document("doc", "chat", "notes.txt", "text", None, None)
            store.replace_chunks("doc", [{"chat_id": "chat", "document_name": "notes.txt",
                "chunk_index": 0, "page_number": None, "content": "completely different wording",
                "embedding": [1.0, 0.0]}])
            results = await RAGService(store, DummyOllama(True), "embed").retrieve(
                "chat", "unmatched query", limit=2
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].document_name, "notes.txt")

    async def test_fixture_corpus_ranks_query_relevant_document_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RAGStore(Path(tmp) / "rag.sqlite3")
            fixtures = [("safety", "Safety.pdf", "collision avoidance braking systems"),
                        ("finance", "Budget.txt", "quarterly accounting revenue")]
            for doc_id, name, content in fixtures:
                store.upsert_document(doc_id, "chat", name, "pdf" if name.endswith("pdf") else "text", 1, None)
                store.replace_chunks(doc_id, [{"chat_id": "chat", "document_name": name,
                    "chunk_index": 0, "page_number": 1 if name.endswith("pdf") else None,
                    "content": content}])
            service = RAGService(store, DummyOllama(), "missing", semantic_weight=0.6,
                                 lexical_weight=0.4, minimum_score=0.01)
            results = await service.retrieve("chat", "collision braking safety", 2)
            self.assertEqual(results[0].document_id, "safety")
            self.assertEqual(service.last_diagnostics["returned"], 1)


if __name__ == "__main__":
    unittest.main()
