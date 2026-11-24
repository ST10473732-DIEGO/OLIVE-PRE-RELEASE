"""Serialize local inference and retain one actively managed model between tasks."""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
import time
from .model_policy import validated_policy


class ModelResidencyService:
    MAX_WAITING = 4
    def __init__(self, ollama, settings=lambda: {}):
        self.ollama, self.settings = ollama, settings
        self.lock = asyncio.Lock()
        self.current = None
        self.active = None
        self.recent = {}
        self.loaded = []
        self.switches = 0
        self.error = ""
        self.waiting = 0
        self.external_guard = None
        self.providers = {}

    def register_provider(self, model, start, stop):
        if model in self.providers:
            raise ValueError('Model provider already registered')
        self.providers[model] = (start, stop)

    def policy(self):
        value = self.settings()
        if sys.platform == 'darwin' and os.environ.get('OLIVE_MACOS_RETAIN_TWO') == '1':
            # Keep the normal model warm between text-only switches; media
            # explicitly evacuates every managed model before using Metal.
            value = {**value, 'keep_alive': 1800}
        return validated_policy(value)

    async def refresh(self):
        self.loaded = await self.ollama.loaded_models()
        return self.snapshot()

    @asynccontextmanager
    async def lease(self, model):
        if self.waiting >= self.MAX_WAITING:
            raise RuntimeError("The local model queue is full. Wait for an active request to finish.")
        self.waiting += 1
        try:
            await self.lock.acquire()
        finally:
            self.waiting -= 1
        try:
            if self.external_guard:
                await self.external_guard()
            if self.current and self.current != model:
                # macOS-only opt-in: Ollama can retain at most two text models
                # (its own memory manager evicts least-recently-used models).
                # Never retain MLX or another provider across a switch.
                retain_text = (sys.platform == 'darwin'
                               and os.environ.get('OLIVE_MACOS_RETAIN_TWO') == '1'
                               and self.current not in self.providers
                               and model not in self.providers)
                if not retain_text:
                    try:
                        if self.current in self.providers:
                            await self.providers[self.current][1]()
                        else:
                            await self.ollama.unload_model(self.current)
                    except Exception as error:
                        if getattr(error, "status_code", None) != 404:
                            raise
                self.switches += 1
                self.current = None
            self.error = ""
            if model in self.providers:
                await self.providers[model][0]()
            self.active = model
            self.current = model
            self.recent[model] = time.time()
            yield self.policy()["keep_alive"]
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.error = type(error).__name__
            if getattr(error, "status_code", None) == 404:
                self.current = None
            raise
        finally:
            self.active = None
            self.lock.release()

    def snapshot(self):
        return {"active": self.active, "managed_model": self.current, "loaded": self.loaded,
                "waiting": self.waiting, "switches": self.switches, "recent_models": list(self.recent)[-20:],
                "vram_budget_gb": self.policy()["vram_gb"], "error": self.error,
                "strategy": "one managed inference request at a time; reuse consecutive models"}
