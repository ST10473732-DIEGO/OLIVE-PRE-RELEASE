from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator

import ollama

from ..config import EMBEDDING_NAME_HINTS, OLLAMA_HOST, VISION_NAME_HINTS


@dataclass(slots=True)
class ModelInfo:
    name: str
    size: int | None = None
    family: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    capabilities: tuple[str, ...] = ()
    digest: str = ""

    @property
    def is_embedding(self) -> bool:
        n = self.name.lower()
        return any(h in n for h in EMBEDDING_NAME_HINTS) or "embedding" in self.capabilities

    @property
    def is_vision(self) -> bool:
        n = self.name.lower()
        return "vision" in self.capabilities or any(h in n for h in VISION_NAME_HINTS)


class OllamaService:
    def __init__(self, host: str = OLLAMA_HOST):
        self.host = host
        self.client = ollama.AsyncClient(host=host)
        self._capability_cache: dict[str, tuple[str, ...]] = {}
        self._context_length_cache: dict[str, int] = {}
        self.residency = None
        self.metrics = None

    async def loaded_models(self):
        response = await self.client.ps()
        values = response.get("models", []) if isinstance(response, dict) else response.models
        return [{"name": _field(value, "model", ""), "size": _field(value, "size", 0),
                 "size_vram": _field(value, "size_vram", 0)} for value in values]

    async def unload_model(self, model):
        await self.client.generate(model=model, prompt="", keep_alive=0)

    async def effective_context_length(self, model):
        advertised = await self.context_length(model)
        if self.residency is None:
            return advertised
        from .model_policy import REQUEST_ROLE
        return min(advertised, self.residency.policy()["contexts"][REQUEST_ROLE.get()])

    @asynccontextmanager
    async def _lease(self, model):
        if self.residency is None:
            yield None
        else:
            async with self.residency.lease(model) as keep_alive:
                yield keep_alive

    async def _options(self, model, options):
        result = dict(options or {})
        if self.residency is not None:
            budget = await self.effective_context_length(model)
            result["num_ctx"] = min(int(result.get("num_ctx", budget)), budget)
        return result

    async def ping(self) -> bool:
        try:
            await self.client.list()
            return True
        except Exception:
            return False

    async def list_models(self) -> list[ModelInfo]:
        response = await self.client.list()
        models = getattr(response, "models", None)
        if models is None and isinstance(response, dict):
            models = response.get("models", [])
        result: list[ModelInfo] = []
        for model in models or []:
            name = getattr(model, "model", None) or (model.get("model") if isinstance(model, dict) else None)
            if not name:
                continue
            size = getattr(model, "size", None) if not isinstance(model, dict) else model.get("size")
            details = getattr(model, "details", None) if not isinstance(model, dict) else model.get("details")
            family = parameter_size = quantization = None
            if details:
                if isinstance(details, dict):
                    family = details.get("family")
                    parameter_size = details.get("parameter_size")
                    quantization = details.get("quantization_level")
                else:
                    family = getattr(details, "family", None)
                    parameter_size = getattr(details, "parameter_size", None)
                    quantization = getattr(details, "quantization_level", None)
            result.append(
                ModelInfo(
                    name=name,
                    size=int(size) if isinstance(size, (int, float)) else None,
                    family=family,
                    parameter_size=parameter_size,
                    quantization=quantization,
                    capabilities=self._capability_cache.get(name, ()),
                    digest=str(model.get("digest", "") if isinstance(model, dict) else getattr(model, "digest", "")),
                )
            )
        return result

    async def model_capabilities(self, model: str) -> tuple[str, ...]:
        if model in self._capability_cache:
            return self._capability_cache[model]
        capabilities: tuple[str, ...] = ()
        try:
            response = await self.client.show(model)
            raw = getattr(response, "capabilities", None)
            if raw is None and isinstance(response, dict):
                raw = response.get("capabilities", [])
            capabilities = tuple(str(x).lower() for x in (raw or []))
            model_info = getattr(response, "model_info", None)
            if model_info is None and isinstance(response, dict):
                model_info = response.get("model_info", {})
            context_length = _context_length_from_metadata(model_info or {})
            if context_length:
                self._context_length_cache[model] = context_length
        except Exception:
            # Some remote/cloud model metadata can be incomplete. Name hints are the safe fallback.
            if any(h in model.lower() for h in VISION_NAME_HINTS):
                capabilities = ("vision",)
        self._capability_cache[model] = capabilities
        return capabilities

    async def context_length(self, model: str) -> int:
        if model not in self._context_length_cache:
            await self.model_capabilities(model)
        return self._context_length_cache.get(model, 32768)

    async def is_vision_model(self, model: str) -> bool:
        capabilities = await self.model_capabilities(model)
        if capabilities:
            return "vision" in capabilities
        return any(h in model.lower() for h in VISION_NAME_HINTS)

    async def is_model_available(self, model: str) -> bool:
        names = {m.name for m in await self.list_models()}
        return model in names

    async def pull(self, model: str) -> None:
        await self.client.pull(model)
        self._capability_cache.pop(model, None)
        self._context_length_cache.pop(model, None)

    async def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
        tools: list[Any] | None = None,
        think: bool | str | None = None,
    ) -> AsyncIterator[str]:
        started, first, success = time.perf_counter(), None, False
        has_content = False
        completed = False
        finish_reason = ""
        async with self._lease(model) as keep_alive:
            try:
                stream = await self.client.chat(model=model, messages=messages, stream=True,
                    options=await self._options(model, options), tools=tools or [], keep_alive=keep_alive,
                    **({"think": think} if think is not None else {}))
                try:
                    async for part in stream:
                        completed = completed or _field(part, "done", False) is True
                        finish_reason = _field(part, "done_reason", "") or finish_reason
                        content = _field(_field(part, "message", {}), "content", "") or ""
                        if content:
                            has_content = has_content or bool(content.strip())
                            first = first or time.perf_counter()
                            yield content
                    if not has_content:
                        raise RuntimeError("The model returned no answer content. Retry the request or select another installed model.")
                    if finish_reason == "length":
                        raise RuntimeError("The response reached the model output limit. The partial answer is retained; ask to continue or retry with a larger response budget.")
                    if not completed:
                        raise RuntimeError("The model stopped before completing its response. The partial answer is retained; retry when the local model is ready.")
                    success = True
                finally:
                    if hasattr(stream, "aclose"):
                        await stream.aclose()
            finally:
                if self.metrics:
                    from .model_policy import REQUEST_ROLE
                    self.metrics.record(model, REQUEST_ROLE.get(), started, success, first)

    async def chat_once(
        self,
        model: str,
        messages: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
        format: str | dict | None = None,
        think: str | bool | None = None,
    ) -> str:
        response = await self.chat_measured(model, messages, options=options, format=format, think=think)
        return response["content"]

    async def chat_measured(self, model, messages, options=None, format=None, tools=None, think=None, stream=False):
        started, success = time.perf_counter(), False
        async with self._lease(model) as keep_alive:
            try:
                kwargs = {"model": model, "messages": messages, "options": await self._options(model, options),
                          "keep_alive": keep_alive}
                if format is not None:
                    kwargs["format"] = format
                if tools is not None:
                    kwargs["tools"] = tools
                if think is not None:
                    kwargs["think"] = think
                first = None
                thinking_characters = 0
                if stream:
                    parts = await self.client.chat(**kwargs, stream=True)
                    content, calls, response = [], [], {}
                    try:
                        async for part in parts:
                            response = part
                            message = _field(part, "message", {})
                            text = _field(message, "content", "") or ""
                            thinking_characters += len(_field(message, "thinking", "") or "")
                            if text:
                                first = first or time.perf_counter()
                                content.append(text)
                            calls.extend(_field(message, "tool_calls", []) or [])
                    finally:
                        if hasattr(parts, "aclose"):
                            await parts.aclose()
                    message = {"content": "".join(content), "tool_calls": calls}
                else:
                    response = await self.client.chat(**kwargs)
                    message = _field(response, "message", {})
                    thinking_characters = len(_field(message, "thinking", "") or "")
                success = True
                return {"content": _field(message, "content", "") or "",
                        "thinking_characters": thinking_characters,
                        "done_reason": _field(response, "done_reason", ""),
                        "first_token_ms": (first - started) * 1000 if first else None,
                        "tool_calls": [item.model_dump() if hasattr(item, "model_dump") else item
                                       for item in (_field(message, "tool_calls", []) or [])],
                        "duration_ms": (time.perf_counter() - started) * 1000,
                        **{key: _field(response, key, 0) for key in
                           ("load_duration", "eval_count", "eval_duration", "prompt_eval_count", "prompt_eval_duration")}}
            finally:
                if self.metrics:
                    from .model_policy import REQUEST_ROLE
                    self.metrics.record(model, REQUEST_ROLE.get(), started, success)

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        async with self._lease(model) as keep_alive:
            response = await self.client.embed(model=model, input=texts, keep_alive=keep_alive)
        embeddings = getattr(response, "embeddings", None)
        if embeddings is None and isinstance(response, dict):
            embeddings = response.get("embeddings")
        return [list(map(float, vector)) for vector in (embeddings or [])]

    async def embed_batched(self, model: str, texts: list[str], batch_size: int = 24) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            out.extend(await self.embed(model, texts[start : start + batch_size]))
            await asyncio.sleep(0)
        return out


def _field(value, name, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def choose_default_chat_model(models: list[ModelInfo]) -> str:
    candidates = [m for m in models if not m.is_embedding]
    if not candidates:
        return models[0].name if models else ""

    priority = (
        "gpt-oss",
        "qwen3",
        "gemma3",
        "llama",
        "mistral",
        "mixtral",
        "deepseek",
        "phi",
    )
    lowered = [(m, m.name.lower()) for m in candidates]
    for token in priority:
        for model, name in lowered:
            if token in name and not model.is_vision:
                return model.name
    for model in candidates:
        if not model.is_vision:
            return model.name
    return candidates[0].name


def _context_length_from_metadata(metadata: Any) -> int | None:
    if hasattr(metadata, "items"):
        items = metadata.items()
    else:
        return None
    for key, value in items:
        if str(key).lower().endswith("context_length"):
            try:
                parsed = int(value)
                if parsed > 0:
                    return parsed
            except (TypeError, ValueError):
                continue
    return None
