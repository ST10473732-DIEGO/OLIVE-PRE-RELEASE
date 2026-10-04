# First-run setup

OLIVE 1.0 sets itself up from a downloaded package: no Git, Python, Node, npm, cloned repository,
environment variables or hand-made folders.

## Pieces

| Piece | Where | Role |
| --- | --- | --- |
| Runtime manifest | `olive/runtime_manifest/1.0.0.json`, schema `schema.json` | The only list of what setup may install, with source, integrity, size, destination, licence and the evidence for each value. Features name the component slots they need; profiles are derived from features |
| Release approvals | `olive/runtime_manifest/release-approvals-1.0.0.json` | **Owner-controlled.** Which entries the owner allowed into the public release, each bound to the entry's release fingerprint. Empty until the owner decides |
| Manifest API | `olive/services/runtime_manifest.py` | Validation, the three-gate "offerable" rule (below), fingerprints; platform targets |
| Release tools | `packaging/release/release_gate.py`, `packaging/release/check_ollama_pins.py` | Show each entry's gate state and print (never write) a candidate approval; report registry digest drift (never rewrite pins) |
| Downloader | `olive/services/secure_download.py` | HTTPS to manifest hosts (every redirect hop too), pinned size ceiling, SHA-256, bounded resumable ranges, cancellation |
| Archive extractor | `olive/services/safe_archive.py` | Member validation (no traversal, absolute paths, link escape, hard links, devices), size and count limits, executable-bit normalisation |
| Installer | `olive/services/runtime_installer.py` | Plans, disk preflight per filesystem, jobs (progress, cancel, retry), atomic placement (archives and model files), Ollama pulls with digest checks, registration, uninstall |
| Setup state | `olive/storage/setup_state_repository.py` → `<profile>/setup.json` | Persisted state, step, package, verified features and install records. No credentials |
| First-run service | `olive/services/first_run.py` | Reported state (including repair), name, verification |
| System check | `olive/services/system_check.py` | OS, CPU, RAM, GPU, VRAM, free space; "Verified" only for validated combinations |
| Optional components | `olive/services/optional_components.py` | Puts an installed component (Playwright) on the import path at start |
| Bridge | `olive/bridge/setup_routes.py`, `desktop/electron/setup-contracts.ts` | Strict `runtime.*` contracts |
| Wizard | `desktop/src/features/setup/` | The renderer flow; manifest-driven, names no model or file |

## Release gate

An entry's licence and release state moves through three separate gates:

| State | Meaning | Recorded by |
| --- | --- | --- |
| `license_identified` | A licence and provenance source was located (`licence.identified`) | Release engineering, in the manifest |
| `engineering_reviewed` | Source, SHA-256 or registry digest, size, safe destination and licence metadata were verified (`licence.engineering_reviewed`, plus every pinned field the validator checks) | Release engineering, in the manifest |
| `release_approved` | The owner intentionally allowed exactly these pins into the public release | The owner, in `release-approvals-<version>.json` |

Setup offers an entry only when it is enabled, its engineering evidence is complete **and** it is
release-approved. An approval names the entry's *release fingerprint*: a SHA-256 over its pinned
URLs, digests, sizes, destination, platforms and licence. Changing any pin voids the approval.
An approval never makes an entry with incomplete evidence installable. The shipped manifest
cannot carry approvals; only a test manifest marked `"fixture": true` may approve its own
fixtures. Unapproved entries are shown as "Not yet approved for the public OLIVE release". The
old single `reviewed` flag is rejected by the validator. None of this is legal advice or legal
approval.

`python packaging/release/release_gate.py` lists every entry's state;
`--record <id> --by <name>` prints a candidate approval for the owner to add by hand.

## Model files and storage

Creator models are kind `file`: a set of pinned files (`files.any` or per platform), each with
its own relative `path` under the destination (for example `models/comfy/diffusion_models/…`),
so each lands in the ComfyUI folder its loader searches. A file already in place with the pinned
SHA-256 is kept; any other existing file stops the install before anything is downloaded.
Uninstall removes only files setup recorded that still have the recorded bytes.

Runtimes, models, downloads and the profile can live on different filesystems (separate
volumes, bind mounts, Btrfs subvolumes). The plan charges each byte to the filesystem it will
occupy (downloads to the temp folder's, unpacked runtimes and model files to their
destination's, Ollama models to the model store's), identifies filesystems from Linux
`mountinfo` (bind mounts of one filesystem count once), and never uses the root filesystem's
free space for another volume. Archives are staged beside their destination so the final
rename never crosses a filesystem. The system check reports free space per filesystem.

## States

`setup.json` stores `not_started`, `in_progress`, `complete`, `skipped` or `existing`. The bridge
reports:

| Reported | Meaning | Wizard |
| --- | --- | --- |
| `first_launch` | New profile | Opens |
| `incomplete` | Started, not finished | Opens at the saved step |
| `complete` | Verification passed | Closed |
| `skipped` | "Set up later" | Closed; Settings › Open setup |
| `existing` | Profile held OLIVE data before setup existed | Closed; never forced |
| `requires_repair` | A feature that verified is now missing something, or `setup.json` is unreadable | Closed; Welcome shows **Repair** |

New versus existing is decided **once**, before that start writes anything into the profile
(`first_run.initialise`). Setup completes only through `runtime.verify`, never because downloads
finished.

## Bridge operations

| Operation | Ledger | Purpose |
| --- | --- | --- |
| `runtime.setup_status` | read-only | State, step, package, repairs, runtimes, current job |
| `runtime.setup_update` | effect | Step, package, preferred name, `skip` / `resume` / `reset` |
| `runtime.system_check` | read-only | Hardware facts |
| `runtime.manifest` | read-only | Profiles, features, public entry facts for this platform |
| `runtime.install_plan` | read-only | Per-slot action (present, install, different build, choose, external, unavailable), per-feature state, sizes and free space |
| `runtime.install_start` | effect | Starts a job for manifest entry ids offered by the plan |
| `runtime.install_progress` | read-only | Polled job progress |
| `runtime.install_cancel` / `runtime.install_retry` | effect | Cancel (partials kept) / resume |
| `runtime.uninstall` | effect | Only what setup installed (record + marker) |
| `runtime.choose` / `runtime.forget` | effect | Use a detected or chosen runtime location / forget a stale one |
| `runtime.verify` | effect | Refresh inventory, check each feature, run a tiny FAST answer |

Read-only operations never enter the bridge's non-evicting request ledger, so polling is safe.
None of these is a model tool: the assistant cannot download or install anything.

## Platforms

- **Linux:** OLIVE-owned Ollama under `~/.local/share/olive/runtime/ollama`; an existing system
  or OLIVE-owned Ollama is reused.
- **Windows:** OLIVE-owned Ollama (zip) or the official Ollama install. Not validated on Windows.
- **macOS:** the official Ollama app or Homebrew; no bundled install until validated on a Mac.
- **Creator:** the Linux image engine is a checksum-pinned runtime archive built by
  `packaging/creator/` (built, reproducible and validated, but not published: its manifest entry
  is `built_validated_unpublished`, disabled, with no URL and no owner approval). The archive never
  contains NVIDIA's CUDA wheels or the wheels that bundle NVIDIA components (triton, torchvision,
  comfy-kitchen, cuda-bindings): its entry lists those 20 as `direct_wheels`, which setup downloads
  from PyPI (`direct_hosts`, pinned size and SHA-256) and unpacks into the staged runtime's
  `site-packages` (RECORD-verified, no pip) before one runtime check and the single rename that
  registers it ([packaging/creator/README.md](../../packaging/creator/README.md)). The video engine
  is defined but not built. FLUX.2 [klein] 4B (Apache-2.0) is owner-approved. VoiceStudio is
  installed by the person (external). Setup says "Some components are not yet available in this
  build" and never blocks completion on Creator extras.

## Testing without downloads

`OLIVE_RUNTIME_MANIFEST=<file>` replaces the manifest. A manifest with `"fixture": true` may use
loopback `http://` sources only when `OLIVE_INSTALLER_ALLOW_LOOPBACK_HTTP=1` is also set. Setup
shows "Test manifest in use" whenever a replacement manifest is active. The tests use local
fixture servers (`tests/setup_installer_fixture.py`).
