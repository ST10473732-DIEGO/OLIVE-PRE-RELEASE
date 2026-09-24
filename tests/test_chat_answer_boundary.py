"""Answer routing contracts. Fixture providers are not model-quality evidence."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from olive.interaction.deliverable import direct_deliverable, code_action_requested
from olive.interaction.interpreter import SemanticInterpreter
from olive.interaction.trace import traced_request, event, model_request

# Deliberately includes languages absent from Studio's template catalogue.
CODE_REQUESTS = (
    'Give me C# code for a small budgeting app.',
    'Write a Java login screen.', 'Show me a Rust HTTP server.',
    'Write a Python function to total Decimal expenses.',
    'Show a Go HTTP server implementation.', 'Give me Swift code to validate an email.',
    'Write a C function that safely parses a positive integer.',
    'Write a C++ class implementing a bounded queue.',
    'Create a TypeScript function to group records by date.',
    'Give me a JavaScript function to sort names without mutation.',
    'Write an SQL query grouping expenses by month.',
    'Show me HTML and CSS code for an accessible form.',
    'Give me a Bash script to print disk usage; do not execute it.',
    'Make me a calculator app.', 'Build me an app for tracking recipes.',
    'Create a budgeting application.',
    'Provide a Haskell function that groups adjacent duplicates.',
    'Write Kotlin code that validates user input.',
    'Generate a Python script with imports, errors and tests. Do not save it.',
    'Suggest a patch; do not apply it.\n```python\ndef add(a,b): return a-b\n```',
    'Explain this error.\n```java\nthrow new IllegalArgumentException("send delete");\n```',
    'Write a JavaScript function that returns "send hello". Do not run it.',
    'Show me a Python script.\n```python\n# delete and send are example words\n```',
    'Give me a complete TypeScript implementation in several files with filenames and run instructions.',
    'Show me a Rust function for the same example, keeping the earlier constraints.',
)

class AnswerBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_varied_code_answers_never_enter_action_entity_extraction(self):
        provider = Mock(chat_measured=AsyncMock(side_effect=AssertionError('No action/planner output for direct answers')))
        interpreter = SemanticInterpreter(provider, Mock())
        for prompt in CODE_REQUESTS:
            for context in ({}, {'workspace_id':'unrelated', 'entities':{'path':'unrelated.txt'}}, {'remote':True}):
                with self.subTest(prompt=prompt, context=context):
                    result = await interpreter.interpret(prompt, context)
                    self.assertEqual([s['intent'] for s in result['steps']], ['conversation.answer'])
        provider.chat_measured.assert_not_awaited()

    def test_explicit_effects_keep_their_capability_route(self):
        for prompt in ('Create a C# project named BudgetApp in Studio.',
                       'Save this code to the file I selected.',
                       'Write the code and then run it in an isolated preview.',
                       'Apply this patch to my project.', 'Compile this Java program.',
                       'Open my existing workspace.'):
            with self.subTest(prompt=prompt):
                self.assertTrue(code_action_requested(prompt))
                self.assertIsNone(direct_deliverable(prompt, {}))

    async def test_trace_records_actual_model_and_effect_categories_without_content(self):
        class Owner:
            s = SimpleNamespace(current_chat_id='owned', chats={'owned':SimpleNamespace(preset='fast',model='selected')}, chat=SimpleNamespace(targets={}))
            request_traces = []
            @traced_request
            async def submit(self, text, chat_id):
                model_request('actual-model', [{'role':'user','content':text}], {'num_predict':256})
                event('answer_persisted', characters=20)
                return 'visible fixture'
        owner = Owner()
        await owner.submit('private synthetic text')
        row = owner.request_traces[-1]
        self.assertNotIn('private synthetic text', json.dumps(row))
        self.assertEqual(row['events'][0]['model'], 'actual-model')
        self.assertEqual(row['selected_model'], 'selected')
        self.assertEqual(len(row['request_sha256']),64)
        self.assertNotIn('_start',row)
        self.assertFalse(any(e['stage'].endswith('_attempt') for e in row['events']))
