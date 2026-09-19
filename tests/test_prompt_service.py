import unittest

from olive.memory import Memory
from olive.services.prompt_service import PromptBuilder


class PromptBuilderTests(unittest.TestCase):
    def test_system_memory_and_user_are_separate_messages(self):
        messages = PromptBuilder().build(
            system_prompt="system",
            notes="notes",
            summary="summary",
            memories=[Memory("preference", "preference")],
            rag_results=[],
            history=[],
            user_text="hello",
        )
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("preference", messages[0]["content"])
        self.assertEqual(messages[-1], {"role": "user", "content": "hello"})


if __name__ == "__main__":
    unittest.main()
