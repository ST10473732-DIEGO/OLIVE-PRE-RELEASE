import json
import unittest

from olive.interaction.intent import entity_schema, parse


class ProjectLanguageTests(unittest.TestCase):
    def proposal(self, language):
        return json.dumps({'confidence': 1, 'clarification': '', 'steps': [
            {'intent': 'project.create', 'entities': {'project': 'Fixture', 'language': language}, 'references': {}}]})

    def test_model_schema_excludes_explanatory_prose(self):
        self.assertEqual(entity_schema('language')['enum'], ['python', 'csharp', 'javascript', 'java', 'unsupported'])

    def test_invalid_language_fails_before_any_execution(self):
        for value in ('Python (default because none was requested)', 'Rust', 'Python; run a command'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse(self.proposal(value))

    def test_legacy_language_aliases_normalize_without_changing_intent(self):
        for value, expected in [('Python', 'python'), ('C#', 'csharp'), ('js', 'javascript'), ('unsupported', 'unsupported')]:
            step = parse(self.proposal(value))['steps'][0]
            self.assertEqual(step['intent'], 'project.create')
            self.assertEqual(step['entities']['language'], expected)
