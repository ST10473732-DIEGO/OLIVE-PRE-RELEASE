"""Destination evaluation accepts harmless prerequisites, never extra applications/actions."""

import unittest
from scripts.natural_language_evaluation import destination_case_order


class DestinationEvaluationTests(unittest.TestCase):
    def test_navigation_allows_only_known_provider_activation(self):
        expected = ["application.navigate"]
        steps = [{"entities": {"application": "Discord"}}]
        order = ["application.launch", "application.navigate"]
        self.assertEqual(destination_case_order(order, expected, steps, "Discord"), expected)
        self.assertEqual(destination_case_order(order, expected, steps, "Chrome"), order)
        extra = [*order, "communication.send"]
        self.assertNotEqual(destination_case_order(extra, expected, steps, "Discord"), expected)
        self.assertEqual(destination_case_order(order, order, steps, "Discord"), order)
