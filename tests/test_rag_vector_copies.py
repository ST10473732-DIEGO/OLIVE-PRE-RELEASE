"""float32 vector copies: same ranking as the JSON path, compatible with earlier builds."""
import json
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path

from olive.storage.rag_store import RAGStore, cosine_similarity

DIM = 32


def vector(rng):
    return [rng.uniform(-1, 1) for _ in range(DIM)]


def rows(rng, count, model="embed"):
    return [{"chat_id": "chat", "document_name": "Doc", "chunk_index": i, "page_number": i,
             "content": f"chunk {i}", "embedding": vector(rng), "embedding_model": model} for i in range(count)]


def reference(store, query, limit, model="embed"):
    """The previous search: cosine over every stored JSON vector, ties by higher id."""
    scored = sorted(((cosine_similarity(query, c.embedding or []), c.id)
                     for c in store.iter_embedded_chunks("chat", model=model)), reverse=True)
    return [chunk_id for _, chunk_id in scored[:limit]]


class VectorCopyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "rag.sqlite3"
        self.rng = random.Random(4)

    def tearDown(self):
        self.temp.cleanup()

    def sql(self, statement, params=()):
        with sqlite3.connect(self.path) as conn:
            return conn.execute(statement, params).fetchall()

    def test_new_rows_store_a_copy_and_rank_like_the_json_path(self):
        store = RAGStore(self.path)
        store.replace_document("d1", "chat", "Doc", "pdf", 1, None, rows(self.rng, 300))
        self.assertEqual(self.sql("SELECT COUNT(*) FROM chunks WHERE embedding_f32 IS NULL"), [(0,)])
        self.assertEqual(store.schema_version(), 4)
        for _ in range(5):
            query = vector(self.rng)
            found = store.semantic_candidates("chat", query, 18, model="embed")
            self.assertEqual([c.id for c, _ in found], reference(store, query, 18))
            for chunk, score in found:
                self.assertAlmostEqual(score, cosine_similarity(query, chunk.embedding), places=5)
                self.assertEqual(chunk.content, f"chunk {chunk.chunk_index}")

    def test_earlier_index_is_converted_on_first_open(self):
        store = RAGStore(self.path)
        store.replace_document("d1", "chat", "Doc", "pdf", 1, None, rows(self.rng, 50))
        self.sql("UPDATE chunks SET embedding_f32=NULL, embedding_norm=NULL")  # as written by v10 or earlier
        query = vector(self.rng)
        # Before conversion, the JSON fallback already gives the same answer.
        self.assertEqual([c.id for c, _ in store.semantic_candidates("chat", query, 10, model="embed")],
                         reference(store, query, 10))
        reopened = RAGStore(self.path)
        self.assertEqual(self.sql("SELECT COUNT(*) FROM chunks WHERE embedding_f32 IS NULL"), [(0,)])
        self.assertEqual([c.id for c, _ in reopened.semantic_candidates("chat", query, 10, model="embed")],
                         reference(reopened, query, 10))

    def test_a_vector_rewritten_by_an_earlier_build_never_uses_a_stale_copy(self):
        store = RAGStore(self.path)
        store.replace_document("d1", "chat", "Doc", "pdf", 1, None, rows(self.rng, 20))
        target = self.sql("SELECT id FROM chunks ORDER BY id LIMIT 1")[0][0]
        query = vector(self.rng)
        # An earlier build updates only embedding_json (its update_embeddings statement).
        self.sql("UPDATE chunks SET embedding_json=?, embedding_model='embed' WHERE id=?", (json.dumps(query), target))
        self.assertEqual(self.sql("SELECT embedding_f32 FROM chunks WHERE id=?", (target,)), [(None,)])
        best, score = store.semantic_candidates("chat", query, 1, model="embed")[0]
        self.assertEqual(best.id, target)
        self.assertAlmostEqual(score, 1.0, places=5)
        # This build's own update keeps the copy in step.
        store.update_embeddings({target: vector(self.rng)}, model="other")
        store.update_embeddings({target: query}, model="embed")
        self.assertEqual(self.sql("SELECT embedding_f32 IS NOT NULL FROM chunks WHERE id=?", (target,)), [(1,)])

    def test_other_models_bad_rows_and_dimension_mismatches_are_skipped(self):
        store = RAGStore(self.path)
        store.replace_document("d1", "chat", "Doc", "pdf", 1, None,
                               rows(self.rng, 10) + rows(self.rng, 5, model="other"))
        self.sql("INSERT INTO chunks(chat_id, document_id, document_name, chunk_index, content, embedding_json) "
                 "VALUES ('chat', 'd1', 'Doc', 99, 'broken', '{not json')")
        self.sql("INSERT INTO chunks(chat_id, document_id, document_name, chunk_index, content, embedding_json) "
                 "VALUES ('chat', 'd1', 'Doc', 98, 'short', '[1.0, 2.0]')")
        RAGStore(self.path)  # Backfill must tolerate the broken row.
        found = store.semantic_candidates("chat", vector(self.rng), 50, model="embed")
        self.assertEqual(len(found), 10)
        self.assertTrue(all(c.embedding_model == "embed" for c, _ in found))
        self.assertEqual(store.semantic_candidates("chat", [], 5), [])
        self.assertEqual(store.semantic_candidates("chat", [0.0] * DIM, 5), [])
        self.assertEqual(store.semantic_candidates("other-chat", vector(self.rng), 5), [])


if __name__ == "__main__":
    unittest.main()
