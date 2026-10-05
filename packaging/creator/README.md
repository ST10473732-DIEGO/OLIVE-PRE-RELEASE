# OLIVE Creator runtimes

Creator (REIMAGINE, VIDEO, image to video, long-form VIDEO) needs a ComfyUI engine with
PyTorch and CUDA. First-run setup never runs `pip`. Instead, release engineering builds each
engine **once**, as a checksum-pinned archive, and the wizard downloads, verifies and unpacks it
with the same installer that installs Ollama.

**NVIDIA wheels, and wheels that bundle NVIDIA components, are never inside the OLIVE archive
("Option B+").** The archive holds everything else (83 wheels); setup downloads the 20 exact pinned
direct-download wheels from PyPI and unpacks them into the staged runtime before it is
registered. This is an engineering/distribution decision, not a legal determination. The source
of those 20 is PyPI; who made each one is whatever its own METADATA says (recorded per wheel),
never one assumed publisher.

```
definitions/<id>.json ──┐
pins/<engine>.txt ── lock_creator.py ──> locks/<id>.txt (complete hash lock)
                                         │
                         split_lock.py ──┼─> locks/<id>.archive.txt  (archive subset, verbatim blocks)
                                         ├─> locks/<id>.wheels.json  (every wheel: file, URL, SHA-256, size,
                                         │                           "archive" or "direct", why, METADATA attribution)
                                         └─> locks/<id>.direct-licences.json (direct wheels' licence/NOTICE texts)
build_creator_runtime.py ──> <id>.tar.zst (+ .sha256, .manifest-entry.json, .inventory.json,
                             .THIRD_PARTY-direct-downloads.txt)
audit_archive.py ──> no direct package, no bundled NVIDIA component, marker = split, no build paths
```

| Input | Pinned by |
| --- | --- |
| CPython 3.14.8 | `packaging/backend/python-runtime.json` (python-build-standalone 20261001, SHA-256), the same interpreter as the backend |
| ComfyUI | git commit in the definition (`v0.35.0` = `40c4fcdf…`), fetched by hash and checked |
| Custom nodes | git commit (video only: ComfyUI-GGUF-Loader `ba92ceb8…`) |
| Archive wheels | `locks/<id>.archive.txt`, each file fetched by the exact URL and SHA-256 in `locks/<id>.wheels.json`, installed with `pip --no-index --require-hashes --only-binary=:all: --no-deps` |
| Direct downloads | `locks/<id>.wheels.json` records with `"distribution": "direct"`, copied into the manifest entry's `direct_wheels` |
| Compressor | `compression.json`: the pinned CPython's built-in libzstd 1.5.7, level 12, `nb_workers` 0 (single-threaded), no checksum, no content size; its SHA-256 is `inputs.compression_sha256` |

The pins are the exact distributions of the reference machine's validated image and video
environments (torch 2.14.0, CUDA 13.0 wheels). Image and video stay **separate** runtimes
(`runtime/comfy`, `runtime/video-comfy`): the video engine needs `gguf`, `protobuf` and a custom
node the image engine must never load.

## The split (split_lock.py)

The definition's `direct_download` policy decides, per locked package:

- `nvidia-*` and `cuda-*` packages are **direct downloads** unless `archive_allowed` names them with
  an open SPDX licence. Today that is only `cuda-pathfinder` (Apache-2.0, pure Python).
- Packages listed in `bundles_nvidia`, each with its audit evidence, are **direct downloads**:
  `triton` (ptxas, cuobjdump, nvdisasm, CUPTI, CUDA headers), `torchvision` (libcudart,
  libnvjpeg), `comfy-kitchen` (statically linked cudart) and `cuda-bindings` (embedded CUDA
  runtime in `cuda/bindings/_internal/runtime*.so`).
- Direct downloads for the image engine: the 14 `LicenseRef-NVIDIA-Proprietary` wheels,
  `nvidia-nvtx` (its metadata says "Apache 2.0" and "Other/Proprietary" at once), the
  `cuda-toolkit` metadata package (no licence field) and the four bundling wheels. **20 wheels,
  2,518,725,343 bytes.**
- Archive: the other **83 wheels, 1,229,508,551 bytes**. No version changed.

`split_lock.py --check` (offline, also run by every build and by CI) re-derives the archive lock
from the complete lock and fails on any drift: a direct package in the archive lock, a
reclassified record, a hash that is not one of the lock's, an off-host URL, or archive and
direct sets that do not add up to the complete lock. `split_lock.py` (no flag) re-resolves the
records from PyPI metadata only, including each direct wheel's own METADATA licence and
attribution fields, its layout (no `.data` scripts/headers, no overlapping files) and its licence/
NOTICE files (checked against the wheel's RECORD) through HTTP Range requests.

## Build (release CI only)

```sh
python packaging/creator/lock_creator.py        # refresh locks and the split; review the diff
export OLIVE_SOURCE_COMMIT="$(git rev-parse HEAD)"   # provenance for the sidecar files only
python packaging/creator/build_creator_runtime.py packaging/creator/definitions/creator-image-comfyui-0.35.0-linux-x86_64.json --output out
python packaging/creator/audit_archive.py out/creator-image-comfyui-0.35.0-linux-x86_64.tar.zst \
    packaging/creator/definitions/creator-image-comfyui-0.35.0-linux-x86_64.json --forbid "$PWD"
```

The builder refuses a definition without the split and re-checks it, then audits the staged tree
before packing: no direct-download distribution, every `site-packages` file belongs to an
archive distribution's RECORD, and no build-folder path in scripts or metadata (pip's console
scripts, a direct shebang or pip's long-path `/bin/sh` trampoline, are rewritten to
python-build-standalone's relocatable `/bin/sh` launcher when their interpreter is the runtime's
own `python/bin`, whether `--output` is relative, long or behind a symlink; any other script that
still names the build folder fails the build). The archive
is byte-reproducible from its runtime inputs alone (sorted members, uid/gid 0, no pip, and every
mtime = the definition's pinned `source_date_epoch`, 1788930166 = the committer time of the pinned
ComfyUI v0.35.0 commit, checked against that commit at build time). The OLIVE repository commit
is build provenance: it is written to the sidecar `manifest-entry.json` / `inventory.json`
(`build_provenance`) and to BUILD-INFO.json, never into the archive, so a metadata-only OLIVE
commit rebuilds the identical archive. A release manifest may carry it as
`source.olive_source_commit`; setup then copies it into the install marker. It holds
`ComfyUI/`, `python/`, `OLIVE-RUNTIME.json` (definition, ComfyUI commit, lock, split, licence-text
and interpreter digests, the pinned epoch and the direct-download list), `THIRD_PARTY-creator.txt` (what is inside)
and `THIRD_PARTY-creator-direct-downloads.txt` (what setup fetches separately). No models.

The compressed bytes are pinned too. `pack_archive.py` writes the tar and compresses it under a
private copy of the pinned python-build-standalone interpreter (`python -I -B -S -X utf8`), whose
libzstd is compiled in, with the fixed parameters of `compression.json`. The build machine's
Python, its `zstd`, CPU count, locale and paths never matter: stable tar + pinned compressor +
fixed parameters = the same `.tar.zst` everywhere. Before this (PASS 2F-C) the builder used the
host Python's libzstd, and the hosted runner's older library wrote different bytes for the same
tar. `nb_workers` stays 0: libzstd's multithreaded engine (any value ≥ 1) writes different bytes.
Bumping CPython changes the compressor, so the builder refuses until `compression.json` names the
new interpreter. The sidecar `compression` block records the compressor, its parameters and the
uncompressed tar's SHA-256. `build_provenance.working_tree_clean` describes the source checkout:
the builder's own `--output` folder (CI's `out/`) is left out of `git status`, nothing else is.

The release CI job `creator` builds and audits the image archive on manual dispatch only and
keeps it as a short-lived private artefact. Its optional `creator_assemble_nvidia` input also
runs `assemble_check.py` (setup's own primitives, then a CPU import of torch) in a scratch folder
that is deleted and never uploaded.

`audit_archive.py` also scans every archive member for NVIDIA-origin content bundled inside a
wheel: CUDA library and toolkit file names, NVIDIA header/tool folders, ELF binaries that embed
the CUDA runtime (`/cudart.shm.`, how comfy-kitchen and cuda-bindings were found), and NVIDIA
proprietary licence markers. Anything not in the reviewed list `vendored_nvidia.json` fails the
build; for the Option B+ image archive that list is **empty**. With `--direct-site` it also checks
that no archive file is byte-identical to a file of an installed direct wheel. NVIDIA copyright
lines in open-source code (ComfyUI, transformers, torch's CUTLASS notices…) are reported only.
Console-script launchers that pip would generate for direct wheels (Triton's `proton`,
`proton-viewer`) are not created by setup; the runtime does not use them.

## From archive to the wizard

1. CI builds the archive; `<id>.manifest-entry.json` gives its SHA-256, size, installed size
   (archive plus unpacked direct wheels), executables, the runtime check and the direct wheels.
2. Until it is published, the manifest entry records the build with
   `"artefact_state": "built_validated_unpublished"`, `enabled: false` and no URL. Setup shows it
   as "not yet published" and never offers it.
3. When the owner publishes the archive on an HTTPS release host: fill `source.url` and `hosts`,
   set `artefact_state: published`, `engineering_reviewed: true`, `enabled: true`.
4. The owner adds a release approval (`packaging/release/release_gate.py --record …`). The
   approval's fingerprint covers the archive AND every direct wheel's URL, SHA-256 and size.

`comfyui-0.35.0-image-linux` went through steps 3 and 4 on 2026-10-05: the accepted archive
(`ecdb6702…`, 1,121,452,201 bytes) is the asset of the GitHub release
[`creator-runtime-1.0.0-ecdb6702`](https://github.com/ST10473732-DIEGO/get-olive/releases/tag/creator-runtime-1.0.0-ecdb6702),
and the owner approved it for Linux x86_64. Never replace that asset with a rebuilt copy; a CI
rebuild only proves the bytes reproduce.

### What setup does (runtime_installer.py)

1. Plans space per filesystem: the archive and the 20 wheels are charged to the download
   volume, the unpacked runtime (≈ 7.03 GB) to the runtime volume; bind mounts of one
   filesystem count once.
2. Downloads the archive from its hosts and each wheel from `direct_hosts` only
   (`files.pythonhosted.org`), HTTPS, pinned size and SHA-256, resumable.
3. Unpacks the archive beside the destination (archive modes kept, never setuid), refuses an
   archive that already contains a direct-download distribution or whose marker lists other
   wheels, then unpacks each wheel into `python/lib/python3.14/site-packages` with
   `safe_archive.install_wheel` (every member RECORD-verified, no `.data` scripts/headers/data,
   nothing overwritten, `INSTALLER` = `olive-setup`). No pip, no wheel code runs.
4. Runs the staged interpreter once with OLIVE's own probe (`-I -B`): Python, torch, CUDA,
   cuDNN, ComfyUI import and core nodes, and no import from outside the runtime. CUDA
   unavailable, a torch or ComfyUI failure, or a leak fails the install truthfully; the verified
   downloads are kept for a retry.
5. Writes `.olive-install.json` (product version, platform, runtime id/version, ComfyUI commit,
   archive and wheel digests, check result; no personal paths) and renames the staging folder
   into place once, then registers it in `runtimes.json`.

Uninstall removes only that owned folder (links inside are not followed) and its registration.

## Other open items

- **Windows.** PyTorch's CUDA wheels for Windows come from `download.pytorch.org`, not PyPI; a
  Windows definition, split and build must happen on Windows.
- **macOS.** Not attempted: Creator on macOS is NOT YET VALIDATED.
- **VIDEO.** Defined and split, not built or validated.

Tests: `tests/test_creator_runtime.py` (fixture build and install), `tests/test_creator_option_b.py`
(split, wheel unpacking, installer, failures, storage, manifest entry).
