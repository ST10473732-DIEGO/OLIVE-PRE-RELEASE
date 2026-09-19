import unittest

from olive.services.model_registry import ModelCapabilityRegistry
from olive.services.ollama_service import ModelInfo, _context_length_from_metadata


class FakeOllama:
    async def list_models(self):
        return [ModelInfo("vision-model", family="family"), ModelInfo("code-model")]

    async def model_capabilities(self, name):
        return ("vision",) if name == "vision-model" else ("completion",)

    async def context_length(self, name):
        return 8192 if name == "vision-model" else 16384


class ModelRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def test_router_does_not_discard_required_context_on_fallback(self):
        from olive.agent.model_router import ModelRouter, RoutingRequest
        registry = ModelCapabilityRegistry(FakeOllama())
        await registry.refresh()
        self.assertIsNone(ModelRouter(registry).route(RoutingRequest("coding", context_required=100000)))

    async def test_registry_uses_provider_metadata(self):
        registry = ModelCapabilityRegistry(FakeOllama())
        models = await registry.refresh()
        self.assertEqual(models[0].role, "vision")
        self.assertTrue(models[0].supports_vision)
        self.assertEqual(models[0].context_length, 8192)
        self.assertEqual(models[1].role, "coding")

    def test_context_length_metadata_supports_family_prefixed_key(self):
        self.assertEqual(_context_length_from_metadata({"llama.context_length": 131072}), 131072)
        self.assertIsNone(_context_length_from_metadata({"other": "value"}))

    async def test_selects_configured_embedding_then_deterministic_fallback(self):
        registry = ModelCapabilityRegistry(FakeOllama())
        await registry.refresh()
        self.assertIsNone(registry.select_embedding_model("vision-model"))
        registry.models["embed-b"] = type("Cap", (), {"name": "embed-b", "installed": True,
            "supports_embeddings": True})()
        registry.models["embed-a"] = type("Cap", (), {"name": "embed-a", "installed": True,
            "supports_embeddings": True})()
        self.assertEqual(registry.select_embedding_model(), "embed-a")
        self.assertEqual(registry.select_embedding_model("embed-b"), "embed-b")


if __name__ == "__main__":
    unittest.main()
