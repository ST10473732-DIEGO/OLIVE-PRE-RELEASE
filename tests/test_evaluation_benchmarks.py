import json
import unittest
from pathlib import Path
from olive.evaluation.rag_benchmark import load_fixture, run_benchmark
from olive.services.grounding_service import GroundingService

class Source:
    def __init__(self, content): self.content = content
    def source_dict(self): return {"filename":"fixture.txt"}

class BenchmarkTests(unittest.IsolatedAsyncioTestCase):
    async def test_versioned_rag_benchmark_reports_all_modes_and_k_values(self):
        self.assertGreaterEqual(len(load_fixture()["queries"]), 6)
        result = await run_benchmark()
        self.assertEqual(set(result["metrics"]), {"lexical", "semantic", "hybrid"})
        self.assertEqual(set(result["metrics"]["hybrid"]), {"k1", "k3", "k5"})
        self.assertGreaterEqual(result["metrics"]["hybrid"]["k3"]["hit_rate"], .8)

    async def test_grounding_fixture_classifications(self):
        path = Path(__file__).parents[1] / "olive/evaluation/fixtures/grounding_v1.json"
        fixture = json.loads(path.read_text(encoding="utf-8"))
        service = GroundingService()
        for case in fixture["cases"]:
            result = service.analyze(case["answer"], [Source(x) for x in case["sources"]])
            self.assertEqual(result.status, case["expected"], case["answer"])

if __name__ == "__main__": unittest.main()
