import unittest

from olive.models import Chat, DocumentRef
from olive.services.diagnostics_service import DiagnosticsService


class FakeOllama:
    async def ping(self): return True
class FakeRegistry:
    models = {"chat": object(), "embed": object()}
    def get(self, name): return type("M", (), {"supports_embeddings": name == "embed"})()
class FakeRAG: embedding_model = "embed"
class FakeMemory:
    repository = type("Repo", (), {"schema_version": lambda self: 1})()
    def list_all(self): return [1, 2]
class FakeStore:
    def aggregate_counts(self, chat_id, model=None): return {"documents": 1, "chunks": 4, "missing_embeddings": 1, "untagged_embeddings": 0, "other_model_embeddings": 2}
    def schema_version(self): return 2
    def integrity_check(self): return {"ok": True}
FakeRAG.store = FakeStore()
class FakeJobs:
    def list_all(self): return [type("J", (), {"state": "queued"})(), type("J", (), {"state": "failed"})()]
class FakeOCR: available = False


class DiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_collects_safe_local_status(self):
        chat = Chat(model="chat", documents=[DocumentRef("d", "guide.pdf")])
        result = await DiagnosticsService(FakeOllama(), FakeRegistry(), FakeRAG(), FakeMemory(),
                                          FakeJobs(), FakeOCR()).collect(chat)
        self.assertTrue(result["ollama_connected"])
        self.assertTrue(result["semantic_rag_enabled"])
        self.assertEqual(result["document_count"], 1)
        self.assertNotIn("password", result)
        self.assertEqual(result["rag_schema_version"], 2)
        self.assertEqual(result["chunks_needing_reembedding"], 2)
        self.assertEqual(result["queued_indexing_jobs"], 1)
        self.assertEqual(result["failed_indexing_jobs"], 1)
        self.assertEqual(result["indexed_chunk_count"], 4)


if __name__ == "__main__": unittest.main()
