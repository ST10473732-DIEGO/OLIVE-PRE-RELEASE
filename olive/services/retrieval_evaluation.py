from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    query: str
    relevant: frozenset[tuple[str, int]]


@dataclass(frozen=True, slots=True)
class RetrievalMetrics:
    recall_at_k: float
    precision_at_k: float
    mean_reciprocal_rank: float
    hit_rate: float
    cases: int


async def evaluate_retrieval(cases: list[EvaluationCase], retrieve: Callable[[str, int], Awaitable[list]],
                             k: int = 5) -> RetrievalMetrics:
    if not cases:
        return RetrievalMetrics(0.0, 0.0, 0.0, 0.0, 0)
    recall = precision = reciprocal = hits = 0.0
    for case in cases:
        results = await retrieve(case.query, k)
        found = [(result.document_id, result.chunk_index) for result in results[:k]]
        relevant_found = [item for item in found if item in case.relevant]
        recall += len(set(relevant_found)) / max(1, len(case.relevant))
        precision += len(relevant_found) / max(1, k)
        first = next((rank for rank, item in enumerate(found, 1) if item in case.relevant), None)
        reciprocal += 1.0 / first if first else 0.0
        hits += 1.0 if relevant_found else 0.0
    count = len(cases)
    return RetrievalMetrics(recall / count, precision / count, reciprocal / count, hits / count, count)
