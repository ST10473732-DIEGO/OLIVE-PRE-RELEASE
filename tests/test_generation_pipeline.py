import unittest

from olive.models import Chat
from olive.services.generation_pipeline import GenerationPipeline


class FakeOllama:
    async def context_length(self, model):
        return 8192


class FakeRAG:
    async def retrieve(self, *args, **kwargs):
        return []

    def build_context(self, results):
        return ""


class FakeMemory:
    def search(self, query, limit=4):
        from olive.memory import Memory
        return [(Memory("User prefers concise answers", "preference"), 1.0)]


class GenerationPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_orders_context_and_deduplicates_current_user_message(self):
        chat = Chat(model="local")
        chat.add_message("user", "question")
        prepared = await GenerationPipeline(FakeOllama(), FakeRAG(), memory=FakeMemory()).prepare(
            chat, "question"
        )
        self.assertIn("Relevant user-approved", prepared.messages[0]["content"])
        users = [m for m in prepared.messages if m["role"] == "user"]
        self.assertEqual(len(users), 1)
        self.assertEqual(prepared.context.context_window, 8192)

    async def test_pipeline_does_not_apply_legacy_fixed_history_slice(self):
        chat = Chat(model="local")
        chat.params["history_messages"] = 1
        chat.add_message("user", "first")
        chat.add_message("assistant", "second")
        prepared = await GenerationPipeline(FakeOllama(), FakeRAG()).prepare(chat, "third")
        contents = [message["content"] for message in prepared.messages]
        self.assertIn("first", contents)
        self.assertIn("second", contents)


if __name__ == "__main__":
    unittest.main()
