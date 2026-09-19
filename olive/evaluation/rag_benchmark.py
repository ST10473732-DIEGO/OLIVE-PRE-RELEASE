from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ..services.rag_service import RAGResult
from ..services.retrieval_evaluation import EvaluationCase, evaluate_retrieval

BENCHMARK_VERSION = "1.0"
FIXTURE = Path(__file__).with_name("fixtures") / "rag_benchmark_v1.json"


def load_fixture(path: Path = FIXTURE) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("version") != BENCHMARK_VERSION: raise ValueError("Unsupported benchmark version")
    return value


def _tokens(value: str) -> set[str]:
    return {word.strip(".,():`").lower() for word in value.split() if len(word.strip(".,():`")) > 2}


async def run_benchmark() -> dict:
    fixture = load_fixture()
    docs = fixture["chunks"]
    cases = [EvaluationCase(case["query"], frozenset(tuple(x) for x in case["relevant"]))
             for case in fixture["queries"]]
    output = {}
    for mode in ("lexical", "semantic", "hybrid"):
        async def retrieve(query, k, current_mode=mode):
            q = _tokens(query)
            ranked = []
            for chunk in docs:
                words = _tokens(chunk["content"])
                lexical = len(q & words) / max(1, len(q))
                aliases = set(chunk.get("concepts", []))
                semantic = len(q & (words | aliases)) / max(1, len(q))
                score = lexical if current_mode == "lexical" else semantic if current_mode == "semantic" else .4*lexical+.6*semantic
                ranked.append((score, chunk))
            ranked.sort(key=lambda item: (-item[0], item[1]["document_id"], item[1]["chunk_index"]))
            return [RAGResult(c["document_id"], c["filename"], c.get("page"), c["chunk_index"],
                              c["type"], c["content"], score) for score, c in ranked[:k]]
        output[mode] = {}
        for k in (1, 3, 5):
            metrics = await evaluate_retrieval(cases, retrieve, k)
            output[mode][f"k{k}"] = {"recall": round(metrics.recall_at_k, 4),
                "precision": round(metrics.precision_at_k, 4), "mrr": round(metrics.mean_reciprocal_rank, 4),
                "hit_rate": round(metrics.hit_rate, 4)}
    return {"benchmark_version": BENCHMARK_VERSION, "cases": len(cases), "metrics": output}


def main() -> None:
    print(json.dumps(asyncio.run(run_benchmark()), indent=2))


if __name__ == "__main__": main()
