import unittest

from olive.services.rag_service import RAGResult
from olive.services.retrieval_evaluation import EvaluationCase, evaluate_retrieval


def result(document, chunk):
    return RAGResult(document, f"{document}.txt", None, chunk, "text", "content", 1.0)


class RetrievalEvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_metrics_have_expected_values(self):
        corpus = {"alpha": [result("irrelevant", 0), result("guide", 2)],
                  "beta": [result("notes", 1)]}
        async def retrieve(query, k): return corpus[query][:k]
        cases = [EvaluationCase("alpha", frozenset({("guide", 2)})),
                 EvaluationCase("beta", frozenset({("notes", 1)}))]
        metrics = await evaluate_retrieval(cases, retrieve, k=2)
        self.assertEqual(metrics.recall_at_k, 1.0)
        self.assertEqual(metrics.precision_at_k, 0.5)
        self.assertEqual(metrics.mean_reciprocal_rank, 0.75)
        self.assertEqual(metrics.hit_rate, 1.0)

    async def test_empty_suite_is_safe(self):
        async def retrieve(query, k): return []
        self.assertEqual((await evaluate_retrieval([], retrieve)).cases, 0)


if __name__ == "__main__": unittest.main()
