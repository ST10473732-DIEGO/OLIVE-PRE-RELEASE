import unittest

from olive.services.grounding_service import GroundingService
from olive.services.rag_service import RAGResult


class GroundingTests(unittest.TestCase):
    def test_strong_and_weak_estimates_are_deterministic(self):
        source = RAGResult("d", "guide.pdf", 2, 0, "pdf",
                           "Hydraulic pump pressure must remain below 200 bar.", 1.0)
        strong = GroundingService().analyze("The hydraulic pump pressure must remain below 200 bar.", [source])
        weak = GroundingService().analyze("Quarterly revenue increased dramatically.", [source])
        self.assertEqual(strong.status, "strong")
        self.assertEqual(weak.status, "weak")
        self.assertEqual(strong.supporting_sources[0]["page_number"], 2)

    def test_without_sources_is_unavailable(self):
        self.assertEqual(GroundingService().analyze("answer", []).status, "unavailable")


if __name__ == "__main__": unittest.main()
