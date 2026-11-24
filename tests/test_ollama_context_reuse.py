"""Each model keeps its loaded context, so switching models does not force reloads.

No Ollama server, GPU or private profile: the residency policy and advertised context
lengths are stubbed.
"""
import unittest
from unittest.mock import AsyncMock

from olive.services.model_policy import CONTEXTS, REQUEST_ROLE
from olive.services.ollama_service import OllamaService


class _Residency:
    def policy(self):
        return {"contexts": dict(CONTEXTS)}


def service(advertised=131072):
    ollama = OllamaService(host="http://127.0.0.1:9")
    ollama.residency = _Residency()
    ollama.context_length = AsyncMock(return_value=advertised)
    return ollama


async def options(ollama, model, role, requested=None):
    token = REQUEST_ROLE.set(role)
    try:
        return (await ollama._options(model, {} if requested is None else {"num_ctx": requested}))["num_ctx"]
    finally:
        REQUEST_ROLE.reset(token)


class OllamaContextReuseTests(unittest.IsolatedAsyncioTestCase):
    async def test_classification_reuses_the_loaded_chat_context(self):
        ollama = service()
        await options(ollama, "gpt-oss:20b", "general")  # macOS prewarm / chat answer
        self.assertEqual(await options(ollama, "gpt-oss:20b", "fast", 4096), CONTEXTS["general"])

    async def test_each_model_keeps_its_own_context_after_a_switch(self):
        ollama = service()
        await options(ollama, "gpt-oss:20b", "general")
        await options(ollama, "qwen3.5:9b", "general")   # e.g. a NOW request in between
        # Back to GPT-OSS with a 4096-token classification: no reload to a smaller context.
        self.assertEqual(await options(ollama, "gpt-oss:20b", "fast", 4096), CONTEXTS["general"])
        self.assertEqual(set(ollama._loaded_context), {"gpt-oss:20b", "qwen3.5:9b"})

    async def test_held_larger_context_is_reused_not_lowered(self):
        ollama = service()
        await options(ollama, "gpt-oss:20b", "reasoning")
        self.assertEqual(await options(ollama, "gpt-oss:20b", "fast", 4096), CONTEXTS["reasoning"])

    async def test_a_new_model_still_uses_its_role_budget(self):
        ollama = service()
        await options(ollama, "gpt-oss:20b", "general")
        # Another model's held context never leaks into an unrelated model.
        self.assertEqual(await options(ollama, "qwen3.5:4b-q4_K_M", "fast", 100000), CONTEXTS["fast"])

    async def test_advertised_model_limit_still_caps_the_context(self):
        ollama = service(advertised=4096)
        self.assertEqual(await options(ollama, "small-model", "general"), 4096)

    async def test_without_residency_options_pass_through(self):
        ollama = OllamaService(host="http://127.0.0.1:9")
        self.assertEqual(await ollama._options("gpt-oss:20b", {"num_ctx": 4096}), {"num_ctx": 4096})


if __name__ == "__main__":
    unittest.main()
