"""macOS-only speculative Ollama retention gates; no GPU or private profile."""
import os
import sys
import unittest
from unittest.mock import patch, AsyncMock
from olive.services.model_residency_service import ModelResidencyService


class MacOllamaRetentionTests(unittest.IsolatedAsyncioTestCase):
    async def test_reuses_two_text_models_only_under_macos_optin(self):
        engine = type("FakeOllama", (), {})()
        engine.unload_model = AsyncMock()
        settings = lambda: {}
        service = ModelResidencyService(engine, settings)
        with patch.dict(os.environ, {"OLIVE_MACOS_RETAIN_TWO": "1"}), patch.object(sys, "platform", "darwin"):
            async with service.lease("gpt-oss:20b") as keep:
                self.assertEqual(keep, 1800)
            async with service.lease("qwen3.5:4b-q4_K_M") as keep:
                self.assertEqual(keep, 1800)
            engine.unload_model.assert_not_awaited()
            self.assertEqual(service.switches, 1)

    async def test_previous_linux_one_model_policy_unmodified(self):
        engine = type("FakeOllama", (), {})()
        engine.unload_model = AsyncMock()
        service = ModelResidencyService(engine)
        with patch.dict(os.environ, {"OLIVE_MACOS_RETAIN_TWO": "1"}), patch.object(sys, "platform", "linux"):
            async with service.lease("gpt-oss:20b"):
                pass
            async with service.lease("qwen3.5:4b-q4_K_M"):
                pass
            engine.unload_model.assert_awaited_once_with("gpt-oss:20b")

    async def test_mlx_provider_never_retained_on_transition(self):
        engine = type("FakeOllama", (), {})()
        engine.unload_model = AsyncMock()
        stop = AsyncMock()
        start = AsyncMock()
        service = ModelResidencyService(engine)
        service.register_provider("mlx-experiment", start, stop)
        with patch.dict(os.environ, {"OLIVE_MACOS_RETAIN_TWO": "1"}), patch.object(sys, "platform", "darwin"):
            async with service.lease("mlx-experiment"):
                pass
            async with service.lease("gpt-oss:20b"):
                pass
            stop.assert_awaited_once()
