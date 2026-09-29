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
    "deep": {"name": "OLIVE DEEP", "model": "gpt-oss:20b", "pipeline": "documents", "role": "reasoning",
             "params": {"temperature": .2, "max_tokens": 8192, "rag_top_k": 8},
             "description": "Native document text, bounded retrieval and citations. Image reading depends on available vision/OCR."},
    "reimagine": {"name": "OLIVE REIMAGINE", "model": "", "pipeline": "media", "role": "media",
                  "params": {}, "description": "Local image generation and editing. Needs a configured media engine."},
}

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
            runtime="Ollama" if key != "reimagine" else "Not configured",
            thinking=False if key in {"fast", "max", "uncensored"} else "low" if key in {"normal", "deep"} else None,
            digest=getattr(info, "digest", ""),
            capabilities=list(model.capabilities) if model else [],
            status="Ready" if ready else "Needs setup",
            available=ready,
            resource_policy="One managed local model at a time; no hosted fallback",
        )

        if key == "reimagine":
            media = getattr(self.s, "media", None)
            generation = media.status()["image_generation"] if media else "Needs setup"
            result.update(
                runtime="Pillow; optional local ComfyUI",
                capabilities=["image-resize", "image-crop"],
                status="Image edits ready; generation " + generation.lower(),
                description="Open Media tools for local raster editing or a configured generation workflow.",
            )

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
        if chat.preset=='reimagine':
            raise ValueError('Open REIMAGINE Media tools to create an image artifact. Text inference cannot generate an image; a local generation engine may need setup.')
        if not chat.preset:
            return  # Legacy explicit provider selection is preserved in place.
        selected = self.get(chat.preset)
        if not selected["available"]:
            raise ValueError("OLIVE REIMAGINE needs a configured local media engine; no image was generated." if chat.preset == "reimagine" else "This OLIVE preset's local model is unavailable. Wait for Models to finish checking, or inspect Advanced Settings.")
        if chat.preset != "uncensored":
            chat.model = selected["model"]
        from .model_policy import REQUEST_ROLE
        REQUEST_ROLE.set(selected["role"])
