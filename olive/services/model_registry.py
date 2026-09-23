from __future__ import annotations

from dataclasses import dataclass

from .ollama_service import ModelInfo


@dataclass(slots=True)
class ModelCapability:
    name: str
    installed: bool
    capabilities: tuple[str, ...]
    context_length: int
    role: str
    family: str | None = None
    size: int = 0
    digest: str = ""
    quantization: str | None = None
    backend: str = "ollama"
    template_sha256: str = ""
    thinking_values: tuple[bool | str, ...] = ()
    thinking_metadata_verified: bool = False

    @property
    def supports_vision(self) -> bool:
        return "vision" in self.capabilities

    @property
    def supports_embeddings(self) -> bool:
        return "embedding" in self.capabilities


class ModelCapabilityRegistry:
    def __init__(self, ollama):
        self.ollama = ollama
        self.models: dict[str, ModelCapability] = {}

    async def refresh(self) -> list[ModelCapability]:
        installed = await self.ollama.list_models()
        result = []
        for info in installed:
            capabilities = await self.ollama.model_capabilities(info.name)
            if not capabilities:
                capabilities = _fallback_capabilities(info)
            model = ModelCapability(
                name=info.name,
                installed=True,
                capabilities=capabilities,
                context_length=await self.ollama.context_length(info.name),
                role=_infer_role(info, capabilities),
                family=info.family,
                size=info.size or 0,
                digest=info.digest,
                quantization=info.quantization,
                **(self.ollama.artifact_metadata(info.name) if hasattr(self.ollama, "artifact_metadata") else {}),
            )
            self.models[model.name] = model
            result.append(model)
        self.models = {model.name: model for model in result}
        return result

    def get(self, name: str) -> ModelCapability | None:
        return self.models.get(name)

    def select_embedding_model(self, configured: str | None = None) -> str | None:
        if configured:
            model = self.models.get(configured)
            if model and model.installed and model.supports_embeddings:
                return model.name
        candidates = sorted(
            (model.name for model in self.models.values() if model.installed and model.supports_embeddings),
            key=str.lower,
        )
        return candidates[0] if candidates else None


def _fallback_capabilities(info: ModelInfo) -> tuple[str, ...]:
    capabilities = []
    if info.is_vision:
        capabilities.append("vision")
    if info.is_embedding:
        capabilities.append("embedding")
    if not capabilities:
        capabilities.append("completion")
    return tuple(capabilities)


def _infer_role(info: ModelInfo, capabilities: tuple[str, ...]) -> str:
    if "embedding" in capabilities or info.is_embedding:
        return "embeddings"
    if "vision" in capabilities or info.is_vision:
        return "vision"
    text = f"{info.name} {info.family or ''}".lower()
    if any(word in text for word in ("code", "coder", "starcoder", "deepseek-coder", "devstral")):
        return "coding"
    if any(word in text for word in ("reason", "r1", "qwq", "gpt-oss")):
        return "reasoning"
    if info.name.lower().startswith("qwen3:8b"):
        return "fast"
    return "general"
