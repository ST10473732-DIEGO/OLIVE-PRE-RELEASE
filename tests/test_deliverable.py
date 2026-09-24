import unittest
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from olive.interaction.deliverable import Deliverable, direct_deliverable
from olive.interaction.interpreter import SemanticInterpreter


class DeliverableTests(unittest.IsolatedAsyncioTestCase):
    async def test_coarse_code_action_needs_an_explicit_effect_target(self):
        provider = Mock(chat_measured=AsyncMock(side_effect=AssertionError('No action entity extraction')))
        interpreter = SemanticInterpreter(provider, Mock())
        interpreter.speech_act = AsyncMock(side_effect=[
            {'mode': 'action', 'domains': ['code']},
            {'mode': 'answer', 'domains': ['conversation']}])
        interpreted = await interpreter.interpret("I'd like a calculator implementation.", {})
        self.assertEqual(interpreted['steps'][0]['intent'], 'conversation.answer')
        interpreter.speech_act.assert_awaited_once()
        provider.chat_measured.assert_not_awaited()

    async def test_selected_mail_summary_keeps_read_only_context_resolution(self):
        result = {'confidence': 1, 'clarification': '', 'steps': [
            {'intent': 'mail.summarize', 'entities': {}, 'references': {'mail_id': 'mail_id'}}]}
        provider = Mock(chat_measured=AsyncMock(return_value={'content': json.dumps(result)}))
        router = Mock()
        router.route.return_value = SimpleNamespace(name='fixture', role='fast')
        interpreter = SemanticInterpreter(provider, router)
        interpreter.speech_act = AsyncMock(return_value={'mode': 'answer', 'domains': ['conversation']})
        interpreted = await interpreter.interpret('Summarise that email.', {'entities': {'mail_id': 'a' * 32}})
        self.assertEqual(interpreted['steps'][0]['intent'], 'mail.summarize')
        # Context permits resolution only: the answer schema cannot send mail.
        offered = str(provider.chat_measured.call_args.kwargs['format'])
        self.assertNotIn('mail.send', offered)
        provider.chat_measured.reset_mock()
        interpreted = await interpreter.interpret('Summarise this text.', {})
        self.assertEqual(interpreted['steps'][0]['intent'], 'conversation.answer')
        provider.chat_measured.assert_not_awaited()

    async def test_diagnostic_question_without_a_target_stays_in_chat(self):
        result = {'confidence': 1, 'clarification': '', 'steps': [
            {'intent': 'code.inspect', 'entities': {}, 'references': {}}]}
        provider = Mock(chat_measured=AsyncMock(return_value={'content': json.dumps(result)}))
        router = Mock()
        router.route.return_value = SimpleNamespace(name='fixture', role='fast')
        interpreter = SemanticInterpreter(provider, router)
        interpreter.speech_act = AsyncMock(return_value={'mode': 'answer', 'domains': ['code']})
        interpreted = await interpreter.interpret('Why is my code failing?', {})
        self.assertEqual(interpreted['steps'][0]['intent'], 'conversation.answer')
        interpreted = await interpreter.interpret('Why is my code failing?', {'workspace_id': 'selected'})
        self.assertEqual(interpreted['steps'][0]['intent'], 'code.inspect')

    async def test_code_and_explanation_skip_classifier_and_action_interpreter(self):
        provider = Mock(chat_measured=AsyncMock(side_effect=AssertionError("No classifier needed")))
        interpreter = SemanticInterpreter(provider, Mock())
        for request in (
            "Give me code for a simple calculator app.",
            "Could you show me a Python script for sorting names?",
            "Please generate a simple function for adding numbers.",
            "Explain how to open Discord.",
            "Write an email saying hello.",
            "Show me a script",
            "Explain this instruction: Open Discord.",
        ):
            with self.subTest(request=request):
                result = await interpreter.interpret(request, {"workspace_id": "previous"})
                self.assertEqual(result["steps"][0]["intent"], "conversation.answer")
        provider.chat_measured.assert_not_awaited()

    def test_actions_and_contextual_followups_require_semantic_resolution(self):
        for request in (
            "Create a calculator project in Studio, save it, and run it.",
            "Open Discord.", "Send this email.", "Run this script.",
            "Create it in Studio", "Actually save that to my project",
            "Give me code and run it", "Show me a script; execute it",
            "Generate a script in my workspace", "Stop that task",
            "What is my schedule?", "Explain my latest email",
            "Explain how to open Discord. Open Discord.",
        ):
            with self.subTest(request=request):
                self.assertIsNone(direct_deliverable(request, {}))

    def test_selected_document_and_pending_draft_keep_context_resolution(self):
        self.assertIsNone(direct_deliverable("Explain this code", {"entities": {"path": "selected.py"}}))
        self.assertIsNone(direct_deliverable("Write an email saying hello", {"pending_draft": {"id": "existing"}}))
        self.assertEqual(direct_deliverable("Show me a script", {}), Deliverable.CODE)
