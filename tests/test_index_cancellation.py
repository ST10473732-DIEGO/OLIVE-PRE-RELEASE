import unittest

from olive.models import DocumentRef
from olive.services.document_service import ExtractedDocument
from olive.services.rag_service import RAGService
from olive.utils.chunking import TextPage


class Store:
    replaced = False
    def upsert_document(self, **kwargs): pass
    def replace_chunks(self, *args): self.replaced = True
class Ollama:
    async def is_model_available(self, model): return True
    async def embed(self, model, texts): return [[1.0] for _ in texts]


class IndexCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_before_embedding_preserves_existing_index(self):
        store = Store()
        document = ExtractedDocument(DocumentRef("doc", "file.txt"), [TextPage("text")], [
            {"chat_id": "chat", "document_name": "file.txt", "chunk_index": 0,
             "page_number": None, "content": "new content"}
        ])
        with self.assertRaises(InterruptedError):
            await RAGService(store, Ollama(), "embed").index(document, should_continue=lambda: False)
        self.assertFalse(store.replaced)


if __name__ == "__main__": unittest.main()
