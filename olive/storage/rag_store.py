from __future__ import annotations

import json
import math
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Iterable

from ..config import RAG_DB_FILE


@dataclass(slots=True)
class StoredChunk:
    id: int
    chat_id: str
    document_id: str
    document_name: str
    chunk_index: int
    page_number: int | None
    content: str
    source_type: str = "text"
    origin_type: str = "native_text"
    ocr_confidence: float | None = None
    embedding: list[float] | None = None


class RAGStore:
    def __init__(self, path: Path = RAG_DB_FILE):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialise()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialise(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    page_count INTEGER,
                    stored_path TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    document_name TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    page_number INTEGER,
                    content TEXT NOT NULL,
                    embedding_json TEXT,
                    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_chunks_chat ON chunks(chat_id);
                CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
                CREATE TABLE IF NOT EXISTS schema_info (
                    component TEXT PRIMARY KEY,
                    version INTEGER NOT NULL
                );
                INSERT INTO schema_info(component, version) VALUES ('rag', 1)
                ON CONFLICT(component) DO NOTHING;
                """
            )
            self._ensure_column(conn, "chunks", "origin_type", "TEXT DEFAULT 'native_text'")
            self._ensure_column(conn, "chunks", "ocr_confidence", "REAL")
            conn.execute("UPDATE schema_info SET version=2 WHERE component='rag' AND version < 2")
            # FTS5 is available in standard CPython builds on modern Windows. Keep a graceful
            # fallback if a custom SQLite build lacks it.
            try:
                conn.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(content, chunk_id UNINDEXED, chat_id UNINDEXED, document_id UNINDEXED)"
                )
            except sqlite3.OperationalError:
                pass

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def upsert_document(
        self,
        document_id: str,
        chat_id: str,
        name: str,
        kind: str,
        page_count: int | None,
        stored_path: str | None,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO documents(id, chat_id, name, kind, page_count, stored_path)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    chat_id=excluded.chat_id,
                    name=excluded.name,
                    kind=excluded.kind,
                    page_count=excluded.page_count,
                    stored_path=excluded.stored_path
                """,
                (document_id, chat_id, name, kind, page_count, stored_path),
            )

    def replace_chunks(self, document_id: str, chunks: Iterable[dict]) -> None:
        rows = list(chunks)
        with self._lock, self._connect() as conn:
            old_ids = [r[0] for r in conn.execute("SELECT id FROM chunks WHERE document_id=?", (document_id,)).fetchall()]
            if old_ids:
                try:
                    placeholders = ",".join("?" for _ in old_ids)
                    conn.execute(f"DELETE FROM chunks_fts WHERE chunk_id IN ({placeholders})", old_ids)
                except sqlite3.OperationalError:
                    pass
            conn.execute("DELETE FROM chunks WHERE document_id=?", (document_id,))

            for row in rows:
                cur = conn.execute(
                    """
                    INSERT INTO chunks(chat_id, document_id, document_name, chunk_index, page_number, content,
                                       embedding_json, origin_type, ocr_confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["chat_id"],
                        document_id,
                        row["document_name"],
                        row["chunk_index"],
                        row.get("page_number"),
                        row["content"],
                        json.dumps(row.get("embedding")) if row.get("embedding") else None,
                        row.get("origin_type", "native_text"), row.get("ocr_confidence"),
                    ),
                )
                try:
                    conn.execute(
                        "INSERT INTO chunks_fts(content, chunk_id, chat_id, document_id) VALUES (?, ?, ?, ?)",
                        (row["content"], cur.lastrowid, row["chat_id"], document_id),
                    )
                except sqlite3.OperationalError:
                    pass

    def replace_document(self,document_id:str,chat_id:str,name:str,kind:str,page_count:int|None,stored_path:str|None,chunks:Iterable[dict]) -> None:
        """Atomically replace document metadata and chunks so a partial index is never visible."""
        rows=list(chunks)
        with self._lock,self._connect() as conn:
            conn.execute("""INSERT INTO documents(id,chat_id,name,kind,page_count,stored_path) VALUES(?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET chat_id=excluded.chat_id,name=excluded.name,kind=excluded.kind,page_count=excluded.page_count,stored_path=excluded.stored_path""",
                (document_id,chat_id,name,kind,page_count,stored_path))
            old_ids=[row[0] for row in conn.execute("SELECT id FROM chunks WHERE document_id=?",(document_id,)).fetchall()]
            if old_ids:
                try:conn.execute(f"DELETE FROM chunks_fts WHERE chunk_id IN ({','.join('?' for _ in old_ids)})",old_ids)
                except sqlite3.OperationalError:pass
            conn.execute("DELETE FROM chunks WHERE document_id=?",(document_id,))
            for row in rows:
                cur=conn.execute("""INSERT INTO chunks(chat_id,document_id,document_name,chunk_index,page_number,content,embedding_json,origin_type,ocr_confidence)
                    VALUES(?,?,?,?,?,?,?,?,?)""",(row["chat_id"],document_id,row["document_name"],row["chunk_index"],row.get("page_number"),row["content"],
                    json.dumps(row.get("embedding")) if row.get("embedding") else None,row.get("origin_type","native_text"),row.get("ocr_confidence")))
                try:conn.execute("INSERT INTO chunks_fts(content,chunk_id,chat_id,document_id) VALUES(?,?,?,?)",(row["content"],cur.lastrowid,row["chat_id"],document_id))
                except sqlite3.OperationalError:pass

    def delete_document(self, document_id: str) -> None:
        with self._lock, self._connect() as conn:
            ids = [r[0] for r in conn.execute("SELECT id FROM chunks WHERE document_id=?", (document_id,)).fetchall()]
            if ids:
                try:
                    placeholders = ",".join("?" for _ in ids)
                    conn.execute(f"DELETE FROM chunks_fts WHERE chunk_id IN ({placeholders})", ids)
                except sqlite3.OperationalError:
                    pass
            conn.execute("DELETE FROM documents WHERE id=?", (document_id,))

    def _row_to_chunk(self, row: sqlite3.Row) -> StoredChunk:
        embedding = None
        raw = row["embedding_json"]
        if raw:
            try:
                embedding = json.loads(raw)
            except json.JSONDecodeError:
                pass
        return StoredChunk(
            id=row["id"],
            chat_id=row["chat_id"],
            document_id=row["document_id"],
            document_name=row["document_name"],
            chunk_index=row["chunk_index"],
            page_number=row["page_number"],
            content=row["content"],
            source_type=row["source_type"] if "source_type" in row.keys() else "text",
            origin_type=row["origin_type"] if "origin_type" in row.keys() else "native_text",
            ocr_confidence=row["ocr_confidence"] if "ocr_confidence" in row.keys() else None,
            embedding=embedding,
        )

    def all_chunks_for_chat(self, chat_id: str, with_embeddings_only: bool = False) -> list[StoredChunk]:
        query = "SELECT c.*, d.kind AS source_type FROM chunks c JOIN documents d ON d.id=c.document_id WHERE c.chat_id=?"
        if with_embeddings_only:
            query += " AND c.embedding_json IS NOT NULL"
        with self._lock, self._connect() as conn:
            return [self._row_to_chunk(row) for row in conn.execute(query, (chat_id,)).fetchall()]

    def document_excerpt(self, chat_id: str, document_id: str, limit: int = 6) -> list[StoredChunk]:
        query = ("SELECT c.*, d.kind AS source_type FROM chunks c JOIN documents d ON d.id=c.document_id "
                 "WHERE c.chat_id=? AND c.document_id=? ORDER BY c.chunk_index,c.id LIMIT ?")
        with self._lock, self._connect() as conn:
            return [self._row_to_chunk(row) for row in conn.execute(query, (chat_id, document_id, max(1, min(limit, 12))))]

    def iter_embedded_chunks(self, chat_id: str, batch_size: int = 500):
        query = ("SELECT c.*, d.kind AS source_type FROM chunks c JOIN documents d ON d.id=c.document_id "
                 "WHERE c.chat_id=? AND c.embedding_json IS NOT NULL ORDER BY c.id")
        with self._lock, self._connect() as conn:
            cursor = conn.execute(query, (chat_id,))
            while rows := cursor.fetchmany(max(1, batch_size)):
                for row in rows:
                    yield self._row_to_chunk(row)

    def has_embedded_chunks(self, chat_id: str) -> bool:
        with self._lock, self._connect() as conn:
            return conn.execute(
                "SELECT 1 FROM chunks WHERE chat_id=? AND embedding_json IS NOT NULL LIMIT 1", (chat_id,)
            ).fetchone() is not None

    def chunks_without_embeddings(self, chat_id: str | None = None) -> list[StoredChunk]:
        query = (
            "SELECT c.*, d.kind AS source_type FROM chunks c "
            "JOIN documents d ON d.id=c.document_id WHERE c.embedding_json IS NULL"
        )
        params: tuple[str, ...] = ()
        if chat_id is not None:
            query += " AND c.chat_id=?"
            params = (chat_id,)
        query += " ORDER BY c.document_id, c.chunk_index"
        with self._lock, self._connect() as conn:
            return [self._row_to_chunk(row) for row in conn.execute(query, params).fetchall()]

    def update_embeddings(self, embeddings: dict[int, list[float]]) -> None:
        if not embeddings:
            return
        with self._lock, self._connect() as conn:
            conn.executemany(
                "UPDATE chunks SET embedding_json=? WHERE id=? AND embedding_json IS NULL",
                [(json.dumps(vector), chunk_id) for chunk_id, vector in embeddings.items()],
            )

    def document_stats(self, chat_id: str) -> list[dict]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT d.id, d.name, d.kind, COUNT(c.id) AS chunk_count,
                       SUM(CASE WHEN c.embedding_json IS NOT NULL THEN 1 ELSE 0 END) AS embedded_count
                FROM documents d LEFT JOIN chunks c ON c.document_id=d.id
                WHERE d.chat_id=? GROUP BY d.id, d.name, d.kind ORDER BY d.name, d.id
                """,
                (chat_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def schema_version(self) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT version FROM schema_info WHERE component='rag'").fetchone()
            return int(row[0]) if row else 0

    def integrity_check(self) -> dict[str, object]:
        with self._lock, self._connect() as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
            return {"ok": result == "ok" and not foreign_keys, "integrity": result,
                    "foreign_key_violations": len(foreign_keys)}

    def aggregate_counts(self, chat_id: str | None = None) -> dict[str, int]:
        where = " WHERE chat_id=?" if chat_id else ""
        params = (chat_id,) if chat_id else ()
        with self._lock, self._connect() as conn:
            documents = conn.execute(f"SELECT COUNT(*) FROM documents{where}", params).fetchone()[0]
            chunks = conn.execute(f"SELECT COUNT(*) FROM chunks{where}", params).fetchone()[0]
            missing_query = f"SELECT COUNT(*) FROM chunks{where}" + (" AND" if where else " WHERE") + " embedding_json IS NULL"
            missing = conn.execute(missing_query, params).fetchone()[0]
            return {"documents": int(documents), "chunks": int(chunks), "missing_embeddings": int(missing)}

    def document_ids(self) -> list[str]:
        with self._lock, self._connect() as conn:
            return [str(row[0]) for row in conn.execute("SELECT id FROM documents ORDER BY id")]

    def lexical_search(self, chat_id: str, query: str, limit: int = 12, document_ids=None) -> list[tuple[StoredChunk, float]]:
        if document_ids is not None and not document_ids:
            return []
        selected = list(dict.fromkeys(document_ids or []))[:100]
        scope = " AND c.document_id IN (" + ",".join("?" for _ in selected) + ")" if selected else ""
        tokens = [t for t in _tokenise_query(query) if len(t) > 1][:20]
        if not tokens:
            return []
        fts_query = " OR ".join(f'"{t}"' for t in tokens)
        with self._lock, self._connect() as conn:
            try:
                rows = conn.execute(
                    f"""
                    SELECT c.*, d.kind AS source_type, bm25(chunks_fts) AS rank
                    FROM chunks_fts
                    JOIN chunks c ON c.id = chunks_fts.chunk_id
                    JOIN documents d ON d.id = c.document_id
                    WHERE chunks_fts MATCH ? AND chunks_fts.chat_id = ? {scope}
                    ORDER BY rank ASC
                    LIMIT ?
                    """,
                    (fts_query, chat_id, *selected, limit),
                ).fetchall()
                # bm25 lower is better; convert to a positive bounded-ish score.
                return [(self._row_to_chunk(r), 1.0 / (1.0 + abs(float(r["rank"])))) for r in rows]
            except sqlite3.OperationalError:
                # Fallback substring scan for custom SQLite builds without FTS5.
                rows = conn.execute(
                    "SELECT c.*, d.kind AS source_type FROM chunks c JOIN documents d ON d.id=c.document_id WHERE c.chat_id=?" + scope,
                    (chat_id, *selected),
                ).fetchall()
                scored = []
                qset = set(tokens)
                for row in rows:
                    words = set(_tokenise_query(row["content"]))
                    score = len(qset & words) / max(len(qset), 1)
                    if score > 0:
                        scored.append((self._row_to_chunk(row), score))
                scored.sort(key=lambda x: x[1], reverse=True)
                return scored[:limit]


def _tokenise_query(text: str) -> list[str]:
    token = []
    out = []
    for ch in text.lower():
        if ch.isalnum() or ch in {"_", "-"}:
            token.append(ch)
        elif token:
            out.append("".join(token))
            token = []
    if token:
        out.append("".join(token))
    return out


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)
