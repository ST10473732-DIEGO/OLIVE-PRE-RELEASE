from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, TYPE_CHECKING
import asyncio
import logging
import heapq

from ..models import DocumentRef
from ..storage.rag_store import RAGStore, StoredChunk, cosine_similarity
from .document_service import ExtractedDocument

if TYPE_CHECKING:
    from .ollama_service import OllamaService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RAGResult:
    document_id: str
    document_name: str
    page_number: int | None
    chunk_index: int
    source_type: str
    content: str
    score: float
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    rank: int = 0
    origin_type: str = "native_text"
    ocr_confidence: float | None = None

    @property
    def source_label(self) -> str:
        if self.page_number is not None:
            return f"{self.document_name} — page {self.page_number}"
        return self.document_name

    def source_dict(self) -> dict:
        return {
            "document_id": self.document_id, "filename": self.document_name,
            "page_number": self.page_number, "chunk_index": self.chunk_index,
            "source_type": self.source_type, "label": self.source_label,
            "origin_type": self.origin_type, "ocr_confidence": self.ocr_confidence,
            "rank": self.rank, "score": self.score,
        }


class RAGService:
    def __init__(self, store: RAGStore, ollama: "OllamaService", embedding_model: str,
                 semantic_weight: float = 0.65, lexical_weight: float = 0.35,
                 minimum_score: float = 0.08):
        self.store = store
        self.ollama = ollama
        self.embedding_model = embedding_model
        self.semantic_weight = max(0.0, semantic_weight)
        self.lexical_weight = max(0.0, lexical_weight)
        self.minimum_score = max(0.0, minimum_score)
        self.last_diagnostics: dict = {}

    async def index(self, document: ExtractedDocument, progress: Callable[[int, int], None] | None = None,
                    should_continue: Callable[[], bool] | None = None, batch_size: int = 24) -> DocumentRef:
        ref = document.ref
        rows = [dict(c) for c in document.chunks]
        embedded = False
        try:
            if rows and await self.ollama.is_model_available(self.embedding_model):
                vectors = []
                for start in range(0, len(rows), batch_size):
                    if should_continue and not should_continue():
                        raise InterruptedError("Indexing paused or cancelled")
                    batch = rows[start:start + batch_size]
                    vectors.extend(await self.ollama.embed(self.embedding_model, [r["content"] for r in batch]))
                    if progress:
                        progress(min(start + len(batch), len(rows)), len(rows))
                    await asyncio.sleep(0)
                if len(vectors) == len(rows):
                    for row, vector in zip(rows, vectors):
                        row["embedding"] = vector
                        row["embedding_model"] = self.embedding_model
                    embedded = True
        except InterruptedError:
            raise
        except Exception:
            logger.warning("Semantic indexing unavailable; using lexical retrieval", exc_info=True)
            # Lexical RAG remains fully functional even if embedding inference fails.
            embedded = False
        self.store.replace_document(ref.id,document.chunks[0]["chat_id"] if document.chunks else "",ref.name,ref.kind,ref.page_count,ref.stored_path,rows)
        ref.indexed = True
        ref.embedding_indexed = embedded
        ref.chunk_count = len(rows)
        return ref

    async def retrieve(self, chat_id: str, query: str, limit: int = 6) -> list[RAGResult]:
        lexical = self.store.lexical_search(chat_id, query, limit=max(limit * 2, 10))
        combined: dict[int, tuple[StoredChunk, float]] = {}
        lexical_scores: dict[int, float] = {}
        semantic_scores: dict[int, float] = {}

        for rank, (chunk, score) in enumerate(lexical):
            # Rank-based lexical contribution is more stable across SQLite bm25 scales.
            lexical_score = 0.8 / (1 + rank) + 0.2 * score
            lexical_scores[chunk.id] = lexical_score
            combined[chunk.id] = (chunk, self.lexical_weight * lexical_score)

        query_vector: list[float] | None = None
        try:
            # Only vectors this embedding model made (or untagged legacy ones) are comparable.
            has_vectors = self.store.has_embedded_chunks(chat_id, model=self.embedding_model)
            if has_vectors and await self.ollama.is_model_available(self.embedding_model):
                vectors = await self.ollama.embed(self.embedding_model, [query])
                query_vector = vectors[0] if vectors else None
                if query_vector:
                    candidate_limit = max(limit * 3, 18)
                    heap: list[tuple[float, int, StoredChunk]] = []
                    for chunk in self.store.iter_embedded_chunks(chat_id, model=self.embedding_model):
                        score = cosine_similarity(query_vector, chunk.embedding or [])
                        item = (score, chunk.id, chunk)
                        if len(heap) < candidate_limit:
                            heapq.heappush(heap, item)
                        elif item[:2] > heap[0][:2]:
                            heapq.heapreplace(heap, item)
                    semantic = [(chunk, score) for score, _, chunk in sorted(heap, reverse=True)]
                    for rank, (chunk, score) in enumerate(semantic):
                        if score <= 0:
                            continue
                        existing = combined.get(chunk.id)
                        contribution = self.semantic_weight * (0.9 * score + 0.1 / (1 + rank))
                        semantic_scores[chunk.id] = score
                        if existing:
                            combined[chunk.id] = (chunk, existing[1] + contribution)
                        else:
                            combined[chunk.id] = (chunk, contribution)
        except Exception:
            logger.warning("Semantic retrieval unavailable; using lexical results", exc_info=True)

        candidates = sorted(
            (item for item in combined.values() if item[1] >= self.minimum_score),
            key=lambda item: (-item[1], item[0].document_name.lower(), item[0].page_number or 0,
                              item[0].chunk_index, item[0].id),
        )
        ranked: list[tuple[StoredChunk, float]] = []
        for candidate in candidates:
            if any(_near_duplicate(candidate[0].content, kept[0].content) for kept in ranked):
                continue
            ranked.append(candidate)
            if len(ranked) >= limit:
                break
        results = [
            RAGResult(
                document_id=chunk.document_id,
                document_name=chunk.document_name,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                source_type=chunk.source_type,
                content=chunk.content,
                score=score,
                lexical_score=lexical_scores.get(chunk.id, 0.0),
                semantic_score=semantic_scores.get(chunk.id, 0.0),
                rank=rank,
                origin_type=chunk.origin_type,
                ocr_confidence=chunk.ocr_confidence,
            )
            for rank, (chunk, score) in enumerate(ranked, 1)
        ]
        self.last_diagnostics = {
            "query_terms": len(query.split()), "lexical_candidates": len(lexical),
            "semantic_enabled": query_vector is not None, "combined_candidates": len(combined),
            "returned": len(results),
        }
        return results

    async def reembed_missing(self, progress: Callable[[int, int], None] | None = None,
                              cancel_event: asyncio.Event | None = None, batch_size: int = 24) -> tuple[int, int]:
        # The person-started index upgrade also re-embeds vectors another model made.
        chunks = self.store.chunks_without_embeddings(model=self.embedding_model or None)
        total = len(chunks)
        completed = 0
        if not chunks or not self.embedding_model:
            return completed, total
        try:
            available = await self.ollama.is_model_available(self.embedding_model)
        except ConnectionError:
            available = False
        if not available:
            return completed, total
        for start in range(0, total, batch_size):
            if cancel_event and cancel_event.is_set():
                break
            batch = chunks[start:start + batch_size]
            vectors = await self.ollama.embed(self.embedding_model, [chunk.content for chunk in batch])
            if len(vectors) != len(batch):
                raise RuntimeError("Embedding model returned an unexpected vector count")
            self.store.update_embeddings({chunk.id: vector for chunk, vector in zip(batch, vectors)},
                                         model=self.embedding_model)
            completed += len(batch)
            if progress:
                progress(completed, total)
            await asyncio.sleep(0)
        return completed, total

    async def retrieve_document(self, chat_id, document_id, query, limit=6):
        limit = max(1, min(limit, 12))
        results = [r for r in await self.retrieve(chat_id, query, limit=limit)
                   if r.document_id == document_id]
        if results:
            return results
        chunks = self.store.document_excerpt(chat_id, document_id, limit)
        return [RAGResult(c.document_id, c.document_name, c.page_number, c.chunk_index,
                          c.source_type, c.content[:4000], 0, rank=index,
                          origin_type=c.origin_type, ocr_confidence=c.ocr_confidence)
                for index, c in enumerate(chunks, 1)]

    def delete_document(self, document_id: str) -> None:
        self.store.delete_document(document_id)

    @staticmethod
    def build_context(results: Iterable[RAGResult]) -> str:
        blocks = []
        for result in results:
            blocks.append(f"[Source: {result.source_label}]\n{result.content}")
        return "\n\n---\n\n".join(blocks)


def _near_duplicate(left: str, right: str, threshold: float = 0.88) -> bool:
    left_words = set(left.lower().split())
    right_words = set(right.lower().split())
    if not left_words or not right_words:
        return left.strip() == right.strip()
    return len(left_words & right_words) / len(left_words | right_words) >= threshold
