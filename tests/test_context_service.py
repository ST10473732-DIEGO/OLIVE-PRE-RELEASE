import unittest

from olive.models import Message
from olive.services.context_service import ContextService, estimate_tokens


class ContextServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_keeps_history_when_it_fits(self):
        history = [Message("user", "hello"), Message("assistant", "hi")]
        plan = await ContextService().plan(history, context_window=4096, response_reserve=512)
        self.assertEqual(plan.history, history)
        self.assertEqual(plan.older_messages_summarized, 0)
        self.assertFalse(plan.over_budget)

    async def test_summarizes_old_messages_and_keeps_recent_turns(self):
        history = [Message("user" if i % 2 == 0 else "assistant", "x" * 800) for i in range(12)]
        seen = []

        async def summarize(messages):
            seen.extend(messages)
            return "Important earlier facts"

        plan = await ContextService(minimum_recent_messages=4).plan(
            history,
            context_window=2048,
            response_reserve=512,
            summarizer=summarize,
        )
        self.assertGreater(len(seen), 0)
        self.assertEqual(plan.history, history[-4:])
        self.assertIn("Important earlier facts", plan.summary)

    async def test_recent_messages_are_never_silently_removed(self):
        history = [Message("user", "x" * 10000), Message("assistant", "y" * 10000)]
        plan = await ContextService().plan(history, context_window=1024, response_reserve=256)
        self.assertEqual(plan.history, history)
        self.assertTrue(plan.over_budget)

    def test_token_estimate_is_deterministic(self):
        self.assertEqual(estimate_tokens("12345"), 2)


if __name__ == "__main__":
    unittest.main()
