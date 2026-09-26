"""Preloading a chat model: same context as the real request; never delays or evicts active work."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from olive.agent.model_router import ModelRouter, RoutingRequest
from olive.application.chat_controller import ChatController
from olive.models import Chat
from olive.services.model_residency_service import ModelResidencyService
from olive.services.ollama_service import OllamaService


def service(loaded=()):
    ollama = OllamaService()
    ollama.context_length = AsyncMock(return_value=131072)
    ollama.loaded_models = AsyncMock(return_value=[{"name": name} for name in loaded])
    ollama.client = SimpleNamespace(generate=AsyncMock())
    ollama.residency = ModelResidencyService(ollama)
    return ollama


class ModelWarmTests(unittest.IsolatedAsyncioTestCase):
    async def test_loads_with_the_context_a_chat_request_uses(self):
        ollama = service()
        self.assertTrue(await ollama.warm("gpt-oss:20b"))
        call = ollama.client.generate.await_args.kwargs
        request_options = await ollama._options("gpt-oss:20b", {"num_ctx": await ollama.effective_context_length("gpt-oss:20b")})
        self.assertEqual((call["model"], call["prompt"], call["options"]["num_ctx"]),
                         ("gpt-oss:20b", "", request_options["num_ctx"]))
        self.assertEqual(ollama.residency.current, "gpt-oss:20b")

    async def test_skips_when_resident_or_inference_is_busy(self):
        ollama = service(loaded=["gpt-oss:20b"])
        self.assertFalse(await ollama.warm("gpt-oss:20b"))
        ollama = service()
        async with ollama.residency.lease("qwen3:8b"):
            self.assertFalse(await ollama.warm("gpt-oss:20b"))
        ollama.client.generate.assert_not_awaited()

    async def test_controller_skips_remote_generating_and_media_conversations(self):
        chat = Chat(model="gpt-oss:20b")
        ollama = SimpleNamespace(warm=AsyncMock(return_value=True))
        controller = ChatController.__new__(ChatController)
        controller.s = SimpleNamespace(chats={chat.id: chat}, ollama=ollama)
        controller.generations, controller.targets = {}, {}
        self.assertEqual(await controller.warm(chat.id), {"warmed": True})
        controller.targets[chat.id] = {"device": "remote"}
        self.assertEqual(await controller.warm(chat.id), {"warmed": False})
        controller.targets.clear(); controller.generations[chat.id] = asyncio.current_task()
        self.assertEqual(await controller.warm(chat.id), {"warmed": False})
        self.assertEqual(await controller.warm("missing"), {"warmed": False})
        self.assertEqual(ollama.warm.await_count, 1)

    async def test_a_smaller_request_reuses_the_resident_context_instead_of_reloading(self):
        ollama = service()
        async with ollama.residency.lease("gpt-oss:20b"):
            self.assertEqual((await ollama._options("gpt-oss:20b", {"num_ctx": 8192}))["num_ctx"], 8192)
            self.assertEqual((await ollama._options("gpt-oss:20b", {"num_ctx": 4096}))["num_ctx"], 8192)
        # Another model starts from its own request, not the previous model's context.
        self.assertEqual((await ollama._options("qwen3:8b", {"num_ctx": 4096}))["num_ctx"], 4096)


class ResidentRoutingTests(unittest.TestCase):
    def setUp(self):
        def model(name, role):
            return SimpleNamespace(name=name, role=role, installed=True, size=100, context_length=32768,
                                   supports_embeddings=False, supports_vision=False)
        self.models = {m.name: m for m in (model("qwen3:8b", "fast"), model("gpt-oss:20b", "reasoning"),
                                            model("qwen3-coder:30b", "coding"))}
        self.residency = SimpleNamespace(current="gpt-oss:20b")
        self.router = ModelRouter(SimpleNamespace(models=self.models, get=self.models.get), residency=self.residency)

    def test_opted_in_requests_keep_the_loaded_candidate(self):
        self.assertEqual(self.router.route(RoutingRequest("fast", prefer_loaded=True)).name, "gpt-oss:20b")
        self.assertEqual(self.router.decisions[-1]["reason"], "already loaded; avoids a model switch")

    def test_other_requests_status_and_non_candidates_keep_the_policy_choice(self):
        self.assertEqual(self.router.route(RoutingRequest("fast")).name, "qwen3:8b")
        self.assertEqual(self.router.route(RoutingRequest("fast", prefer_loaded=True), record=False).name, "qwen3:8b")
        self.residency.current = "qwen3-coder:30b"  # not a fast candidate
        self.assertEqual(self.router.route(RoutingRequest("fast", prefer_loaded=True)).name, "qwen3:8b")

    def test_an_explicit_override_wins(self):
        router = ModelRouter(SimpleNamespace(models=self.models, get=self.models.get),
                             lambda: {"overrides": {"fast": "qwen3:8b"}}, residency=self.residency)
        self.assertEqual(router.route(RoutingRequest("fast", prefer_loaded=True)).name, "qwen3:8b")


if __name__ == "__main__":
    unittest.main()


class ConversationListTests(unittest.TestCase):
    def test_the_list_carries_the_day_and_one_line_of_the_latest_message(self):
        from olive.application.chat_controller import last_line
        from olive.bridge.chat_routes import search
        chat = Chat(title="Plan")
        chat.add_message("user", "What does my week look like?")
        chat.add_message("assistant", "Here is your week:\n\n- Today: standup at 09:30")
        self.assertEqual(last_line(chat), "Here is your week: - Today: standup at 09:30")
        chat.add_message("assistant", "word " * 40)
        self.assertTrue(last_line(chat).endswith("…") and len(last_line(chat)) <= 90)
        self.assertEqual(last_line(Chat()), "")
        record = search(SimpleNamespace(chats={chat.id: chat}), "")[0]
        self.assertEqual((record["updated_at"], record["last"]), (chat.updated_at, last_line(chat)))
