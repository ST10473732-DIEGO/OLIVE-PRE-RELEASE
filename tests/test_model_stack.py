import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from olive.agent.model_router import ModelRouter, RoutingRequest
from olive.services.model_policy import validated_policy, REQUEST_ROLE
from olive.services.model_residency_service import ModelResidencyService
from olive.services.model_benchmark_service import ModelBenchmarkService
from olive.services.ollama_service import OllamaService
from olive.evaluation.model_fixtures import GENERAL, CODING


def model(name, role="general", vision=False):
    return SimpleNamespace(name=name, role=role, installed=True, size=100,
                           context_length=32768, supports_embeddings=False, supports_vision=vision)


class ModelStackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "benchmarks.json"
        self.models = {name: model(name, role) for name, role in [
            ("qwen3:8b", "fast"), ("gpt-oss:20b", "reasoning"),
            ("qwen3-coder:30b", "coding"), ("devstral:24b", "coding")]}
        self.registry = SimpleNamespace(models=self.models, get=self.models.get)

    def test_candidate_roles_and_manual_override(self):
        router = ModelRouter(self.registry)
        self.assertEqual(router.route(RoutingRequest("fast")).name, "qwen3:8b")
        self.assertEqual(router.route(RoutingRequest("reasoning")).name, "gpt-oss:20b")
        router.settings = lambda: {"overrides": {"coding": "devstral:24b"}}
        self.assertEqual(router.route(RoutingRequest("coding")).name, "devstral:24b")

    def test_missing_override_falls_back_without_image_downgrade(self):
        router = ModelRouter(self.registry, lambda: {"overrides": {"coding": "absent"}})
        self.assertEqual(router.route(RoutingRequest("coding")).name, "qwen3-coder:30b")
        self.assertIsNone(router.route(RoutingRequest("vision")))
        self.models["qwen3-vl:8b"] = model("qwen3-vl:8b", "vision", True)
        self.assertEqual(router.route(RoutingRequest("vision")).name, "qwen3-vl:8b")

    def test_measured_coding_quality_and_speed_can_choose_different_models(self):
        def summary(name, role):
            return {"quality": 1 if name == "devstral:24b" else .8, "latency_ms": 9000 if name == "devstral:24b" else 1000}
        router = ModelRouter(self.registry, lambda: {"mode": "Quality"}, SimpleNamespace(summary=summary))
        self.assertEqual(router.route(RoutingRequest("coding")).name, "devstral:24b")
        router.settings = lambda: {"mode": "Performance"}
        self.assertEqual(router.route(RoutingRequest("coding")).name, "qwen3-coder:30b")

    def test_context_policy_validates_bounds(self):
        self.assertEqual(validated_policy()["contexts"]["fast"], 4096)
        self.assertEqual(validated_policy({"contexts": {"coding": 8192}})["contexts"]["coding"], 8192)
        for value in [{"contexts": {"coding": 999999}}, {"overrides": {"unknown": "model"}}, {"vram_gb": 0}]:
            with self.assertRaises(ValueError):
                validated_policy(value)

    async def test_residency_reuses_consecutive_models_and_serializes_switch(self):
        ollama = SimpleNamespace(unload_model=AsyncMock())
        service = ModelResidencyService(ollama)
        async with service.lease("small"):
            self.assertEqual(service.active, "small")
        async with service.lease("small"):
            self.assertEqual(service.switches, 0)
        async with service.lease("large"):
            self.assertEqual(service.active, "large")
        ollama.unload_model.assert_awaited_once_with("small")

    async def test_missing_model_does_not_poison_next_installed_request(self):
        from ollama import ResponseError
        provider = SimpleNamespace(unload_model=AsyncMock())
        service = ModelResidencyService(provider)
        with self.assertRaises(ResponseError):
            async with service.lease("missing"):
                raise ResponseError("model not found", status_code=404)
        self.assertIsNone(service.current)
        self.assertIsNone(service.active)
        self.assertFalse(service.lock.locked())
        async with service.lease("installed"):
            self.assertEqual(service.error, "")
        provider.unload_model.assert_not_awaited()

    async def test_previously_managed_model_already_absent_does_not_block_switch(self):
        from ollama import ResponseError
        provider = SimpleNamespace(unload_model=AsyncMock(side_effect=ResponseError("not found", status_code=404)))
        service = ModelResidencyService(provider)
        service.current = "previous"
        async with service.lease("installed"):
            self.assertEqual(service.active, "installed")
        self.assertEqual(service.current, "installed")

    async def test_cancelled_waiter_does_not_release_active_lease(self):
        service = ModelResidencyService(SimpleNamespace(unload_model=AsyncMock()))
        async with service.lease("active"):
            async def waiter():
                async with service.lease("other"):
                    self.fail("Cancelled waiter acquired lease")
            task = asyncio.create_task(waiter())
            await asyncio.sleep(0)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(service.lock.locked())
        self.assertFalse(service.lock.locked())

    async def test_effective_context_caps_advertised_metadata(self):
        service = OllamaService()
        service.context_length = AsyncMock(return_value=131072)
        service.residency = ModelResidencyService(service)
        token = REQUEST_ROLE.set("fast")
        try:
            self.assertEqual(await service.effective_context_length("qwen3:8b"), 4096)
            self.assertEqual((await service._options("qwen3:8b", {"num_ctx": 100000}))["num_ctx"], 4096)
        finally:
            REQUEST_ROLE.reset(token)

    async def test_benchmark_persists_quality_without_prompt_contents(self):
        answers = {prompt: expected for _, prompt, expected in [*GENERAL, *CODING]}
        async def respond(name, messages, **kwargs):
            if kwargs.get("tools"):
                return {"tool_calls": [{"function": {"name": "inspect_window", "arguments": {"application": "Notepad"}}}],
                        "load_duration": 0, "eval_count": 1, "eval_duration": 1000000}
            return {"content": json.dumps(answers[messages[0]["content"]]), "load_duration": 2000000,
                    "eval_count": 10, "eval_duration": 1000000000, "first_token_ms": 3}
        service = ModelBenchmarkService(SimpleNamespace(chat_measured=respond), self.registry, self.path)
        records = await service.run(["devstral:24b"])
        self.assertTrue(all(record["success"] for record in records))
        restored = ModelBenchmarkService(None, self.registry, self.path)
        self.assertEqual(restored.summary("devstral:24b", "coding")["quality"], 1)
        self.assertNotIn("prompt", self.path.read_text())

    async def test_invalid_output_is_measured_as_failure(self):
        service = ModelBenchmarkService(SimpleNamespace(chat_measured=AsyncMock(return_value={"content": "not json"})), self.registry, self.path)
        records = await service.run(["qwen3:8b"])
        self.assertTrue(all(not record["success"] and record["error"] in {"JSONDecodeError", "KeyError"} for record in records))

    async def test_uninstalled_benchmark_never_invokes_model(self):
        ollama = SimpleNamespace(chat_measured=AsyncMock())
        service = ModelBenchmarkService(ollama, self.registry, self.path)
        with self.assertRaises(ValueError):
            await service.run(["not-installed"])
        ollama.chat_measured.assert_not_awaited()

class BoundedQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_queue_rejects_without_stealing_active_slot(self):
        service = ModelResidencyService(SimpleNamespace(unload_model=AsyncMock()))
        service.waiting = service.MAX_WAITING
        with self.assertRaisesRegex(RuntimeError, 'queue is full'):
            async with service.lease('fixture'):
                self.fail('Queue admission must fail')
        self.assertFalse(service.lock.locked())
        self.assertIsNone(service.current)
