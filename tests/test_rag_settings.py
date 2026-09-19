import unittest
from olive.services.rag_settings import DEFAULTS, validate_rag_settings

class RAGSettingsTests(unittest.TestCase):
    def test_valid_and_invalid_values(self):
        self.assertEqual(validate_rag_settings(6, .35, .65, .08)["top_k"], 6)
        for args in [(0,.5,.5,.1), (3,0,0,.1), (3,1.2,.5,.1), (3,.5,.5,2)]:
            with self.assertRaises(ValueError): validate_rag_settings(*args)
        self.assertEqual(DEFAULTS["top_k"], 6)

if __name__ == "__main__": unittest.main()
