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
  Either OLIVE redistributes them inside its archive (Option A), or the archive leaves them out
  and setup fetches the exact pinned wheels from PyPI (Option B). See
  [NVIDIA wheels: Option A and Option B](#nvidia-wheels-option-a-and-option-b). The builder
  supports Option A today. Neither is enabled without an owner release approval.
- **Windows.** PyTorch's CUDA wheels for Windows come from `download.pytorch.org`, not PyPI;
  a Windows definition and lock must be generated and built on Windows CI.
- **macOS.** Not attempted: Creator on macOS is NOT YET VALIDATED.
- **Interpreter.** The reference environments run system CPython 3.14.7; the archive uses
  3.14.8. A real build must pass a REIMAGINE/VIDEO acceptance run before it is enabled.

Tests build and install a fixture archive (fake interpreter, fake ComfyUI, one local wheel):
`tests/test_creator_runtime.py`.

## NVIDIA wheels: Option A and Option B

This section compares the two options technically. It is not a legal assessment. Which
option is permitted is the owner's (and counsel's) decision.

Image runtime lock (`creator-image-comfyui-0.35.0-linux-x86_64`), resolved against PyPI
metadata on 2026-10-03 for CPython 3.14 / manylinux x86_64:

| Part | Wheels | Download bytes |
| --- | --- | --- |
| NVIDIA proprietary (`LicenseRef-NVIDIA-Proprietary`): cublas, cuda-cupti, cuda-nvrtc, cuda-runtime, cudnn-cu13, cufft, cufile, curand, cusolver, cusparse, cusparselt-cu13, nccl-cu13, nvjitlink, nvshmem-cu13 | 14 | 2,190,129,641 |
| Everything else (torch, triton, ComfyUI packages, Apache-2.0 `nvidia-nvtx`/`cuda-bindings`/`cuda-pathfinder`, …) | 89 | 1,558,104,253 |
| Whole lock | 103 | 3,748,233,894 |

All 14 proprietary wheels are served by `files.pythonhosted.org`, the same host as the rest of the lock.

**How torch finds them.** `torch/lib/libtorch_cuda.so` has
`RPATH $ORIGIN/../../nvidia/{cudnn,nvshmem,nccl,cusparselt,cu13}/lib`. The libraries must
therefore sit in the same `site-packages/nvidia/` as torch. A separate folder added through
a `.pth` file would only work through torch's `_preload_cuda_deps` fallback, which scans
`sys.path`. That fallback is a different code path from the validated one, so Option B
must not use it.

| | Option A: in the OLIVE archive | Option B: archive without them, setup fetches the pinned wheels |
| --- | --- | --- |
| Reproducibility | One archive digest covers everything | Archive digest plus 14 wheel digests from the lock. Bytes are identical when the wheels are unpacked into the same `site-packages/nvidia/` |
| First-run steps | 1 download, 1 extraction | 1 archive + 14 wheels (`python-wheels` items). Then the wheels are unpacked into the extracted runtime's `site-packages` **before** the runtime's single atomic rename, so the runtime is never registered without CUDA |
| Archive size (download) | ≈ 3.75 GB of wheels (compressed archive somewhat smaller) | ≈ 1.56 GB of wheels in the archive, plus 2.19 GB fetched from PyPI |
| Offline / mirror | One file to mirror | The archive plus 14 PyPI files. An offline install needs both sets |
| Integrity | SHA-256 of the archive (pinned in the manifest) | SHA-256 of the archive plus each wheel's lock hash, through the same `secure_download` path (HTTPS, host allow-list `files.pythonhosted.org`, exact size, resume) |
| Licence notices | NVIDIA licence texts ship inside the archive (`THIRD_PARTY-creator.txt` flags them) | Each wheel's own licence files arrive with it. The archive notices list the 14 as "fetched from PyPI at setup, not distributed by OLIVE" |
| Upstream availability | Unaffected after build | Depends on PyPI keeping those exact files. Yanking does not delete them, but an upstream deletion would break new installs until OLIVE re-pins |
| Failure recovery | The whole archive retries or resumes | Per-wheel resume. A failure leaves only the staging folder, which is removed, and nothing is registered |
| Build change needed | None (current builder) | Builder: install the lock minus `nvidia-*` proprietary wheels into the archive and emit the 14 `{url, sha256, size}` for a companion manifest entry. Installer: an "into the staged runtime" step for those wheels. Then a real REIMAGINE run on the result. **Not implemented**: it needs the multi-GB build to validate |

Under either option the final installed tree is the same. A REIMAGINE/VIDEO acceptance run on
the built runtime is required before its manifest entry is enabled.
