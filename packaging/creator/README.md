# OLIVE Creator runtimes

Creator (REIMAGINE, VIDEO, image to video, long-form VIDEO) needs a ComfyUI engine with
PyTorch and CUDA. First-run setup never runs `pip`. Instead, release engineering builds each
engine **once**, as a checksum-pinned archive, and the wizard downloads, verifies and unpacks it
with the same installer that installs Ollama.

```
definitions/<id>.json ──┐                                   ┌─> <id>.tar.zst (+ .sha256)
pins/<engine>.txt ── lock_creator.py ──> locks/<id>.txt ──> build_creator_runtime.py ─┤
packaging/backend/python-runtime.json (CPython pin) ────────┘                         └─> <id>.manifest-entry.json
```

| Input | Pinned by |
| --- | --- |
| CPython 3.14.8 | `packaging/backend/python-runtime.json` (python-build-standalone 20261001, SHA-256), the same interpreter as the backend |
| ComfyUI | git commit in the definition (`v0.35.0` = `40c4fcdf…`), fetched by hash and checked |
| Custom nodes | git commit (video only: ComfyUI-GGUF-Loader `ba92ceb8…`) |
| Wheels | `locks/<id>.txt`: `uv pip compile` of `pins/*.txt`, binary wheels only, index SHA-256 hashes. The pins are the exact distributions of the reference machine's validated image and video environments (torch 2.14.0, CUDA 13.0 wheels) |

Image and video stay **separate** runtimes (`runtime/comfy`, `runtime/video-comfy`), as on the
reference machine: the video engine needs extra packages (`gguf`, `protobuf`) and a custom node
the image engine must never load.

## Build (release CI only)

```sh
python packaging/creator/lock_creator.py                      # refresh locks; review the diff
python packaging/creator/build_creator_runtime.py packaging/creator/definitions/creator-image-comfyui-0.35.0-linux-x86_64.json
```

The archive is deterministic (sorted members, uid/gid 0, `SOURCE_DATE_EPOCH` mtimes) and holds
`ComfyUI/`, `python/`, `OLIVE-RUNTIME.json` (definition, source commit, lock and interpreter
digests) and `THIRD_PARTY-creator.txt`. It contains no models. The release CI job
`creator` builds it on demand (manual input; several GB) and keeps it as a private artefact.

## From archive to the wizard

1. CI builds the archive; `<id>.manifest-entry.json` gives its SHA-256, size, installed size,
   executables and runtime registration.
2. The owner decides where it is hosted (an HTTPS release host) and whether OLIVE may ship the
   NVIDIA wheels inside it (see below).
3. Release engineering fills the manifest entry (`comfyui-0.35.0-image-linux` /
   `comfyui-0.35.0-video-linux`): URL, host list, SHA-256, size, `engineering_reviewed: true`,
   `enabled: true`.
4. The owner adds a release approval (`packaging/release/release_gate.py --record …`).

Until all four happen, Creator engines stay "not yet available in this build". People with
their own ComfyUI choose it under Runtimes, exactly as before.

## Open decisions

- **NVIDIA wheels.** `nvidia-*` CUDA/cuDNN/NCCL wheels are under NVIDIA's proprietary terms.
  Either OLIVE redistributes them inside its archive (owner/legal decision), or the archive
  leaves them out and the wizard installs them directly from PyPI as pinned `python-wheels`
  (each user downloads from NVIDIA's PyPI uploads). The builder supports the first today.
- **Windows.** PyTorch's CUDA wheels for Windows come from `download.pytorch.org`, not PyPI;
  a Windows definition and lock must be generated and built on Windows CI.
- **macOS.** Not attempted: Creator on macOS is NOT YET VALIDATED.
- **Interpreter.** The reference environments run system CPython 3.14.7; the archive uses
  3.14.8. A real build must pass a REIMAGINE/VIDEO acceptance run before it is enabled.

Tests build and install a fixture archive (fake interpreter, fake ComfyUI, one local wheel):
`tests/test_creator_runtime.py`.
