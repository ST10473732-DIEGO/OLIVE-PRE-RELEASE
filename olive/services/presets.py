"""Public product presets; provider identity and execution authority stay separate."""
from copy import deepcopy

PRESETS = {
    "fast": {"name": "OLIVE FAST", "model": "qwen3:8b", "pipeline": "chat", "role": "fast",
             "params": {"temperature": .3, "max_tokens": 4096}, "description": "Quick answers and code, with lower resource use."},
    "normal": {"name": "OLIVE NORMAL", "model": "gpt-oss:20b", "pipeline": "chat", "role": "general",
               "params": {"temperature": .4, "max_tokens": 4096}, "description": "Everyday answers and reasoning."},
    "max": {"name": "OLIVE MAX", "model": "orcarouter/Qwen3.8-27B-Uncensored:q3_K_M", "pipeline": "chat", "role": "coding",
            "pinned_digest": "4da593b4aaed076b41e22b07f680075ff3856c46802f64866c353ac2b1a4fbcd",
            "params": {"temperature": .2, "max_tokens": 8192},
            "description": "Heavy answers and code; passed the declared local MAX and Remote AI gates."},
    "uncensored": {"name": "OLIVE UNCENSORED", "model": "", "pipeline": "chat", "role": "general",
                   "params": {"temperature": .35, "max_tokens": 8192},
                   "description": "Automatic local routing across installed reduced-refusal models based on the request."},
    "now": {"name": "OLIVE NOW", "model": "qwen3.5:9b", "pipeline": "live", "role": "general",
            "params": {"temperature": .2, "max_tokens": 4096},
            "description": "Live public information synthesized locally with source provenance."},
    "deep": {"name": "OLIVE DEEP", "model": "gpt-oss:20b", "pipeline": "documents", "role": "reasoning",
             "params": {"temperature": .2, "max_tokens": 8192, "rag_top_k": 8},
             "description": "Native document text, bounded retrieval and citations. Image reading depends on available vision/OCR."},
    "reimagine": {"name": "OLIVE REIMAGINE", "model": "", "pipeline": "media", "role": "media",
                  "params": {}, "description": "Generate and edit images locally, directly in Chat."},
    "audio": {"name": "OLIVE AUDIO", "model": "", "pipeline": "media", "role": "media",
              "params": {}, "description": "Generate local speech and audio directly in Chat."},
    "video": {"name": "OLIVE VIDEO", "model": "", "pipeline": "media", "role": "media",
              "params": {}, "description": "Generate local video directly in Chat."},
}
MEDIA_PRESETS = ("reimagine", "audio", "video")

# Rollback: the MAX mapping before the 2026-09-25 promotion (see
# docs/OLIVE_UNIFIED_AGENT_FINAL_CLOSEOUT.md). Restoring it is a one-line revert.
PREVIOUS_MAX = {"model": "qwen3-coder:30b", "pinned_digest": ""}


class PresetCatalog:
    def __init__(self, services):
        self.s = services

    def get(self, key):
        if key not in PRESETS:
            raise ValueError("Unknown OLIVE preset")

        result = deepcopy(PRESETS[key])

        if key in MEDIA_PRESETS:
            chat_media = getattr(self.s, "chat_media", None)
            state = chat_media.status(key) if chat_media else {
                "available": False, "status": "Needs setup", "runtime": "Local media engine", "capabilities": []}
            result.update(id=key, digest="", thinking=None, status=state["status"], available=state["available"],
                          runtime=state["runtime"], capabilities=state["capabilities"],
                          resource_policy="One heavy local engine on the GPU at a time; This device only; no hosted fallback")
            return result

        if key == "uncensored":
            available = self.s.uncensored_router.available_models()
            model = self.s.model_registry.get(available[0]) if available else None
            info = next(
                (m for m in self.s.model_infos if available and m.name == available[0]),
                None,
            )
            ready = bool(available)
            result["model"] = available[0] if available else ""
        else:
            model = self.s.model_registry.get(result["model"])
            info = next(
                (m for m in self.s.model_infos if m.name == result["model"]),
                None,
            )
            ready = bool(model and model.installed and not model.supports_embeddings)

        pinned = result.pop("pinned_digest", "")
        if pinned and getattr(info, "digest", "") != pinned:
            ready = False

        result.update(
            id=key,
            runtime="Ollama",
            thinking=False if key in {"fast", "max", "uncensored"} else "low" if key in {"normal", "deep"} else None,
            digest=getattr(info, "digest", ""),
            capabilities=list(model.capabilities) if model else [],
            status="Ready" if ready else "Needs setup",
            available=ready,
            resource_policy="One managed local model at a time; no hosted fallback",
        )

        if key == "now":
            result.update(self.s.now.status())

        return result

    def list(self):
        return [self.get(key) for key in PRESETS]

    def apply(self, chat, key):
        selected = self.get(key)
        # Selecting an unavailable capability remains inspectable. Sending must
        # explain setup instead of silently substituting ordinary chat.
        chat.preset = key
        chat.model = "" if key == "uncensored" else selected["model"]
        chat.params.update(selected["params"])
        return selected

    def require(self, chat):
        if chat.preset in MEDIA_PRESETS:
            # Media presets never fall back to text inference; ChatMediaService handles them.
            raise ValueError("OLIVE media presets generate media and do not use text inference.")
        if not chat.preset:
            return  # Legacy explicit provider selection is preserved in place.
        if chat.preset == "now":
            self.s.now.require()
        selected = self.get(chat.preset)
        if not selected["available"]:
            raise ValueError("This OLIVE preset's local model is unavailable. Wait for Models to finish checking, or inspect Advanced Settings.")
        if chat.preset != "uncensored":
            chat.model = selected["model"]
        from .model_policy import REQUEST_ROLE
        REQUEST_ROLE.set(selected["role"])
