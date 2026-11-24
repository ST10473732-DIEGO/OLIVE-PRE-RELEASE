"""Public product presets; provider identity and execution authority stay separate."""
from copy import deepcopy

from .model_policy import macos_model_profile

# Release presets: these match the approved 1.0 runtime manifest (olive/runtime_manifest)
# on every platform. The Mac Preview profile below is layered on top only in the packaged
# native macOS app.
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

# Mac Studio Preview model profile (M1 Max, 32 GB): the models qualified on that Mac, each
# pinned to its installed digest. Applied only when the packaged native macOS app sets
# OLIVE_MACOS_MODEL_PROFILE=1 (desktop/electron/main/index.ts); the release presets above
# are what every other platform and the release manifest use.
MACOS_PRESET_PROFILE = {
    "fast": {"model": "qwen3.5:4b-q4_K_M",
             "pinned_digest": "d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04",
             "description": "Low-latency private local AI, optimized for responsive answers and code."},
    "normal": {"pinned_digest": "f38aa0c53da5f8c49d08c43a99df24ff53167fe68e24664a7777288e7656fdfe",
               "params": {"temperature": .35, "max_tokens": 4096},
               "description": "Reliable everyday private local reasoning."},
    "max": {"model": "gpt-oss:20b",
            "pinned_digest": "f38aa0c53da5f8c49d08c43a99df24ff53167fe68e24664a7777288e7656fdfe",
            "description": "High-effort private reasoning and coding on the M1 Max; this is a Mac Preview candidate."},
    "deep": {"pinned_digest": "f38aa0c53da5f8c49d08c43a99df24ff53167fe68e24664a7777288e7656fdfe"},
}
RELEASE_THINKING = {"fast": False, "max": False, "uncensored": False, "normal": "low", "deep": "low"}
MACOS_THINKING = {**RELEASE_THINKING, "max": "high", "deep": "medium"}


def profile_presets(macos):
    presets = deepcopy(PRESETS)
    if macos:
        for key, values in MACOS_PRESET_PROFILE.items():
            presets[key].update(deepcopy(values))
    return presets


MACOS_PROFILE = macos_model_profile()
if MACOS_PROFILE:
    # In place, so every module that imported PRESETS sees the same effective values.
    for _key, _values in profile_presets(True).items():
        PRESETS[_key].clear()
        PRESETS[_key].update(_values)
THINKING = MACOS_THINKING if MACOS_PROFILE else RELEASE_THINKING

# Rollback: the MAX mapping before the 2026-09-25 promotion (see
# docs/archive/agent/OLIVE_UNIFIED_AGENT_FINAL_CLOSEOUT.md). Restoring it is a one-line revert.
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
            thinking=THINKING.get(key),
            digest=getattr(info, "digest", ""),
            capabilities=list(model.capabilities) if model else [],
            status="Ready" if ready else "Needs setup",
            available=ready,
            resource_policy="One managed local model at a time; no hosted fallback",
        )

        if key == "now":
            # NOW's readiness is NowService's verdict. `status` stays the shared
            # "Ready"/"Needs setup" vocabulary every Ollama preset uses; NOW's
            # descriptive wording is carried separately as `detail`.
            now = self.s.now.status()
            result.update(
                available=now["available"],
                status="Ready" if now["available"] else "Needs setup",
                detail=now["status"],
                inference_status=now["inference_status"],
                retrieval_status=now["retrieval_status"],
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
