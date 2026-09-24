import unittest
from olive.evaluation.answer_gate import score, CASES, CANDIDATES


class AnswerGateTests(unittest.TestCase):
    def test_format_requires_exact_keys_types_and_no_fences(self):
        self.assertTrue(score('format','{"language":"Spanish","count":3}'))
        for answer in ('{"language":"Spanish","count":"3"}',
                       '```json\n{"language":"Spanish","count":3}\n```',
                       '{"language":"Spanish","count":3,"extra":0}'):
            self.assertFalse(score('format',answer))

    def test_followup_retains_language_and_line_constraints(self):
        self.assertTrue(score('followup','La bomba se llama Cedar.\nEse es su nombre.'))
        self.assertFalse(score('followup','The pump is Cedar.\nThat is its name.'))
        self.assertFalse(score('followup','La bomba se llama Cedar.'))

    def test_finite_role_gate_has_only_authorized_candidates(self):
        self.assertEqual(len(CANDIDATES),2)
        self.assertEqual(len(CASES),7)
        self.assertEqual(len({name for name, _ in CASES}),len(CASES))
