import unittest
from olive.research.orchestrator import in_requested_scope, requested_hosts


class RequestedSourceTests(unittest.TestCase):
    def test_explicit_url_scopes_candidates_without_lookalike_domains(self):
        question = 'Use https://docs.example.com/api to answer this question.'
        self.assertTrue(in_requested_scope('https://docs.example.com/other', question))
        self.assertFalse(in_requested_scope('https://docs.example.com.attacker.test/api', question))
        self.assertFalse(in_requested_scope('https://related-product.test/api', question))

    def test_multiple_explicit_sources_and_open_research(self):
        question = 'Compare https://alpha.example/api and https://beta.example/api.'
        self.assertEqual(requested_hosts(question), {'alpha.example', 'beta.example'})
        self.assertTrue(in_requested_scope('https://beta.example/api', question))
        self.assertTrue(in_requested_scope('https://public.example/page', 'Research this topic'))
