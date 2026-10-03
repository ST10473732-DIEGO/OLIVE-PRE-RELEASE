# First-run setup

OLIVE 1.0 sets itself up from a downloaded package: no Git, Python, Node, npm, cloned repository,
environment variables or hand-made folders.

## Pieces

| Piece | Where | Role |
| --- | --- | --- |
| Runtime manifest | `olive/runtime_manifest/1.0.0.json`, schema `schema.json` | The only list of what setup may install, with source, integrity, size, destination, licence and the evidence for each value. Features name the component slots they need; profiles are derived from features |
| Manifest API | `olive/services/runtime_manifest.py` | Validation and the "installable" rule; platform targets |
| Downloader | `olive/services/secure_download.py` | HTTPS to manifest hosts (every redirect hop too), pinned size ceiling, SHA-256, bounded resumable ranges, cancellation |
| Archive extractor | `olive/services/safe_archive.py` | Member validation (no traversal, absolute paths, link escape, hard links, devices), size and count limits, executable-bit normalisation |
| Installer | `olive/services/runtime_installer.py` | Plans, disk preflight per volume, jobs (progress, cancel, retry), atomic placement, Ollama pulls with digest checks, registration, uninstall |
| Setup state | `olive/storage/setup_state_repository.py` → `<profile>/setup.json` | Persisted state, step, package, verified features and install records. No credentials |
| First-run service | `olive/services/first_run.py` | Reported state (including repair), name, verification |
| System check | `olive/services/system_check.py` | OS, CPU, RAM, GPU, VRAM, free space; "Verified" only for validated combinations |
| Optional components | `olive/services/optional_components.py` | Puts an installed component (Playwright) on the import path at start |
| Bridge | `olive/bridge/setup_routes.py`, `desktop/electron/setup-contracts.ts` | Strict `runtime.*` contracts |
| Wizard | `desktop/src/features/setup/` | The renderer flow; manifest-driven, names no model or file |

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
- **Creator** engines and models stay disabled in the manifest until their provenance, checksum
  and licence are proven; setup says "Some components are not yet available in this build".

## Testing without downloads

`OLIVE_RUNTIME_MANIFEST=<file>` replaces the manifest. A manifest with `"fixture": true` may use
loopback `http://` sources only when `OLIVE_INSTALLER_ALLOW_LOOPBACK_HTTP=1` is also set. Setup
shows "Test manifest in use" whenever a replacement manifest is active. The tests use local
fixture servers (`tests/setup_installer_fixture.py`).
