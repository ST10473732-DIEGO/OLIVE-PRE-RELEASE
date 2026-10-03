"""Vectors carry the embedding model that made them; incompatible vectors are never compared,
and existing (untagged) indexes are upgraded in place without touching a single vector."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from olive.services.rag_service import RAGService
from olive.storage.rag_store import RAGStore


def chunk(index, content, embedding=None, model=None):
    row = {'chat_id': 'chat', 'document_name': 'notes.txt', 'chunk_index': index, 'page_number': None, 'content': content}
    if embedding is not None:
        row['embedding'] = embedding
    if model is not None:
        row['embedding_model'] = model
    return row


class Ollama:
    def __init__(self, vector=(1.0, 0.0)):
        self.vector = list(vector)
        self.embedded = []

    async def is_model_available(self, model):
        return True

    async def embed(self, model, texts):
        self.embedded.append((model, list(texts)))
        return [list(self.vector) for _ in texts]


class EmbeddingModelTagTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'rag.sqlite3'

    def tearDown(self):
        self.temp.cleanup()

    def legacy_database(self):
        """A schema-2 index as OLIVE wrote it before this change: vectors without a model."""
        with sqlite3.connect(self.path) as conn:
            conn.executescript('''
                CREATE TABLE documents (id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
                    page_count INTEGER, stored_path TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT NOT NULL, document_id TEXT NOT NULL,
                    document_name TEXT NOT NULL, chunk_index INTEGER NOT NULL, page_number INTEGER, content TEXT NOT NULL,
                    embedding_json TEXT, origin_type TEXT DEFAULT 'native_text', ocr_confidence REAL,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE);
                CREATE TABLE schema_info (component TEXT PRIMARY KEY, version INTEGER NOT NULL);
                INSERT INTO schema_info VALUES ('rag', 2);
                INSERT INTO documents(id, chat_id, name, kind) VALUES ('doc', 'chat', 'notes.txt', 'text');
                INSERT INTO chunks(chat_id, document_id, document_name, chunk_index, content, embedding_json)
                    VALUES ('chat', 'doc', 'notes.txt', 0, 'legacy wording', '[1.0, 0.0]');''')

    def test_existing_index_is_upgraded_without_rewriting_vectors(self):
        self.legacy_database()
        before = sqlite3.connect(self.path).execute('SELECT id, content, embedding_json FROM chunks').fetchall()
        store = RAGStore(self.path)
        self.assertEqual(store.schema_version(), 3)
        after = sqlite3.connect(self.path).execute('SELECT id, content, embedding_json, embedding_model FROM chunks').fetchall()
        self.assertEqual([row[:3] for row in after], before)
        self.assertEqual(after[0][3], None)  # Untagged legacy vector, left as it was.
        counts = store.aggregate_counts('chat', model='qwen3-embedding:0.6b')
        self.assertEqual((counts['untagged_embeddings'], counts['other_model_embeddings']), (1, 0))
        # Legacy vectors remain usable (dimension is still checked) and are never overwritten.
        self.assertEqual([c.content for c in store.iter_embedded_chunks('chat', model='qwen3-embedding:0.6b')], ['legacy wording'])
        self.assertEqual(store.chunks_without_embeddings(model='qwen3-embedding:0.6b'), [])
        store.update_embeddings({after[0][0]: [0.0, 1.0]}, model='qwen3-embedding:0.6b')
        self.assertEqual(sqlite3.connect(self.path).execute('SELECT embedding_json FROM chunks').fetchone()[0], '[1.0, 0.0]')

    async def test_vectors_from_another_model_are_never_compared_and_need_reembedding(self):
        store = RAGStore(self.path)
        store.upsert_document('doc', 'chat', 'notes.txt', 'text', None, None)
        store.replace_chunks('doc', [chunk(0, 'alpha wording', [1.0, 0.0], 'model-a'),
                                     chunk(1, 'beta wording', [1.0, 0.0], 'model-b'),
                                     chunk(2, 'gamma wording')])
        self.assertEqual([c.content for c in store.iter_embedded_chunks('chat', model='model-a')], ['alpha wording'])
        self.assertTrue(store.has_embedded_chunks('chat', model='model-a'))
        self.assertFalse(store.has_embedded_chunks('chat', model='model-c'))
        results = await RAGService(store, Ollama(), 'model-a').retrieve('chat', 'unrelated query', limit=3)
        self.assertEqual([r.content for r in results], ['alpha wording'])  # beta's vector is incompatible.
        counts = store.aggregate_counts('chat', model='model-a')
        self.assertEqual((counts['missing_embeddings'], counts['other_model_embeddings']), (1, 1))
        # The person-started index upgrade re-embeds the missing and the other-model vectors.
        ollama = Ollama((0.0, 1.0))
        done, total = await RAGService(store, ollama, 'model-a').reembed_missing()
        self.assertEqual((done, total), (2, 2))
        self.assertEqual(sorted(ollama.embedded[0][1]), ['beta wording', 'gamma wording'])
        rows = {c.content: (c.embedding_model, c.embedding) for c in store.all_chunks_for_chat('chat')}
        self.assertEqual(rows['alpha wording'], ('model-a', [1.0, 0.0]))
        self.assertEqual(rows['beta wording'], ('model-a', [0.0, 1.0]))
        self.assertEqual(rows['gamma wording'], ('model-a', [0.0, 1.0]))

    async def test_new_index_tags_every_vector_with_its_model(self):
        from olive.models import DocumentRef
        from olive.services.document_service import ExtractedDocument
        store = RAGStore(self.path)
        service = RAGService(store, Ollama(), 'qwen3-embedding:0.6b')
        document = ExtractedDocument(ref=DocumentRef('doc', 'notes.txt'), pages=[], chunks=[chunk(0, 'tagged wording')])
        await service.index(document)
        stored = store.all_chunks_for_chat('chat')
        self.assertEqual([(c.content, c.embedding_model) for c in stored], [('tagged wording', 'qwen3-embedding:0.6b')])
        self.assertEqual(json.loads(sqlite3.connect(self.path).execute('SELECT embedding_json FROM chunks').fetchone()[0]),
                         [1.0, 0.0])


if __name__ == '__main__':
    unittest.main()
