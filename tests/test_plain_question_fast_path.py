"""General-knowledge questions skip the request classifier; anything else keeps it."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from olive.interaction.deliverable import Deliverable, direct_deliverable
from olive.interaction.interpreter import SemanticInterpreter

PLAIN = (
    "Why is the sky blue?",
    "What is quantum entanglement?",
    "What's the difference between weather and climate",  # "weather" is blocked: see below
    "Who was Nelson Mandela?",
    "Explain photosynthesis",
    "Tell me about the Roman Empire",
    "Define entropy.",
    "Describe how volcanoes form",
    "Can you explain why tides happen?",
    "Is a tomato a fruit?",
    "Where did the Vikings settle?",
)

NOT_PLAIN = (
    # The person's own data, records and devices.
    "What is on my calendar?", "What emails did I get?", "Who was in the meeting?",
    "What are my notes about tides?", "What is in the attached file?",
    # Current or changing information that research may need.
    "What is the latest iPhone?", "What's the weather like?", "Who was the winner yesterday?",
    "What is the population of Japan?", "What happened in 2024?",
    # Follow-ups that depend on earlier turns or tasks.
    "Why did it fail?", "What does that mean?", "Explain this.",
    # Actions and applications, including inside a question.
    "Can you open Safari?", "What is Spotify playing?", "Which file should I delete?",
    "What is a good script to rename photos?", "How is OLIVE configured?",
    # Compound or embedded content.
    "What is entropy? Then open Notes.", "What is entropy and then email it to Sam?",
    'What does "open Discord" mean?', "What is https://example.com?",
    # Not a question.
    "Open Discord.", "Delete the old drafts", "Thanks",
)


class PlainQuestionTests(unittest.IsolatedAsyncioTestCase):
    def test_general_questions_are_answered_without_classification(self):
        for text in PLAIN:
            with self.subTest(text=text):
                result = direct_deliverable(text, {})
                if "weather" in text:
                    self.assertIsNone(result)
                else:
                    # "Explain ..." already used the existing explanation shortcut.
                    self.assertIn(result, {Deliverable.ANSWER, Deliverable.EXPLANATION})

    def test_personal_current_contextual_and_action_requests_keep_classification(self):
        for text in NOT_PLAIN:
            with self.subTest(text=text):
                self.assertNotEqual(direct_deliverable(text, {}), Deliverable.ANSWER)

    def test_any_selection_pending_work_or_attachment_keeps_classification(self):
        for context in ({"entities": {"path": "/tmp/a.txt"}}, {"pending_draft": {"id": "d"}},
                        {"native_proposals": [{"id": "p"}]}, {"workspace_id": "w"},
                        {"clarification": {"question": "Which?"}}, {"active_task": {"state": "running"}},
                        {"browser_application": "Safari"}, {"media_application": "Music"},
                        {"research_session_id": "r"}, {"attached_documents": [{"attachment_id": "a"}]}):
            with self.subTest(context=context):
                self.assertIsNone(direct_deliverable("Why is the sky blue?", context))
        # Empty values are not context.
        self.assertEqual(direct_deliverable("Why is the sky blue?", {"entities": {}, "attached_documents": []}),
                         Deliverable.ANSWER)

    async def test_interpreter_makes_no_model_call_for_a_plain_question(self):
        provider = Mock(chat_measured=AsyncMock(side_effect=AssertionError("no classification expected")))
        interpreter = SemanticInterpreter(provider, Mock())
        interpreter.speech_act = AsyncMock(side_effect=AssertionError("no speech act expected"))
        result = await interpreter.interpret("Why is the sky blue?", {"entities": {}, "attached_documents": []})
        self.assertEqual([s["intent"] for s in result["steps"]], ["conversation.answer"])
        self.assertEqual(interpreter.metrics[-1]["model_calls"], 0)

    async def test_interpreter_still_classifies_a_personal_question(self):
        router = Mock()
        router.route.return_value = SimpleNamespace(name="fixture", role="fast")
        interpreter = SemanticInterpreter(Mock(), router)
        interpreter.speech_act = AsyncMock(return_value={"mode": "clarify", "domains": []})
        await interpreter.interpret("What is on my calendar?", {})
        interpreter.speech_act.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
