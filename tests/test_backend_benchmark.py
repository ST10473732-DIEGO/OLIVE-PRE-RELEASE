import unittest
from olive.evaluation.backend_benchmark import load_cases, grade_json, distribution

class BackendBenchmarkTests(unittest.TestCase):
    def test_fixtures_are_disjoint_versioned_and_cover_contracts(self):
        development, held = load_cases(), load_cases('held_out')
        self.assertEqual(len(development) + len(held), 48)
        self.assertFalse({c['id'] for c in development} & {c['id'] for c in held})
        self.assertEqual(len({c['id'] for c in development + held}), 48)
        self.assertTrue({'java','csharp','python','typescript','injection','lifecycle','vision'} <= {c['category'] for c in development + held})

    def test_strict_json_rejects_duplicate_keys_boolean_numbers_and_extra_fields(self):
        for value in ('{"n":1,"n":2}', '{"n":true}', '{"n":2,"extra":0}', '```json\n{"n":2}\n```', '{"n":NaN}'):
            self.assertEqual(grade_json(value, {'n':2}), (False, False))
        self.assertEqual(grade_json('{"n":2}', {'n':2}), (True, True))
        self.assertEqual(grade_json('{"n":3}', {'n':2}), (True, False))

    def test_small_samples_report_ranges_not_p95(self):
        self.assertEqual(distribution([1, 2, 9]), {'n':3, 'median':2, 'min':1, 'max':9})
