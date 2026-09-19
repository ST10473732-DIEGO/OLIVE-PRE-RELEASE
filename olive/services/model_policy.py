"""Validated local role preferences and conservative context budgets."""

from contextvars import ContextVar

REQUEST_ROLE = ContextVar("olive_model_role", default="general")
ROLES = ("fast", "general", "reasoning", "coding", "vision", "embedding")
CANDIDATES = {
    "fast": ("qwen3:8b", "gpt-oss:20b"),
    "general": ("gpt-oss:20b", "qwen3:8b"),
    "reasoning": ("gpt-oss:20b", "qwen3:8b"),
    "coding": ("qwen3-coder:30b", "devstral:24b", "gpt-oss:20b"),
    "vision": ("qwen3-vl:8b",),
    "embedding": ("qwen3-embedding:0.6b",),
}
CONTEXTS = {"fast": 4096, "general": 8192, "reasoning": 12288, "coding": 16384,
            "vision": 8192, "embedding": 2048}


def validated_policy(value=None):
    value = {} if value is None else value
    if not isinstance(value, dict) or set(value) - {"mode", "overrides", "contexts", "vram_gb", "keep_alive"}:
        raise ValueError("Unknown model policy setting")
    mode = value.get("mode", "Balanced")
    if mode not in ("Automatic", "Performance", "Balanced", "Quality"):
        raise ValueError("Unknown model selection mode")
    overrides = value.get("overrides", {})
    contexts = value.get("contexts", {})
    if not isinstance(overrides, dict) or set(overrides) - set(ROLES) or any(
        not isinstance(name, str) or len(name) > 160 for name in overrides.values()
    ):
        raise ValueError("Invalid model role override")
    if not isinstance(contexts, dict) or set(contexts) - set(ROLES) or any(
        type(size) is not int or not 1024 <= size <= 65536 for size in contexts.values()
    ):
        raise ValueError("Context overrides must be between 1024 and 65536 tokens")
    vram, keep_alive = value.get("vram_gb", 16), value.get("keep_alive", 300)
    if type(vram) is not int or not 2 <= vram <= 96:
        raise ValueError("Invalid VRAM budget")
    if type(keep_alive) is not int or not 0 <= keep_alive <= 1800:
        raise ValueError("Invalid model keep-alive")
    return {"mode": mode, "overrides": dict(overrides), "contexts": {**CONTEXTS, **contexts},
            "vram_gb": vram, "keep_alive": keep_alive}
