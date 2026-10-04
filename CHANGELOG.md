# Changelog

All notable changes to OLIVE are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and versions follow
[Semantic Versioning](https://semver.org/).

OLIVE was formerly named DMDO. The 3.x DMDO/OLIVE development line is the history
before 1.0 ([project journey](docs/history/PROJECT_JOURNEY.md)).

## [Unreleased] — 1.0.0

The first OLIVE release. Not yet released: installers and first-run model setup
are still being prepared on `release/olive-1.0`.

### Added

- **Chat modes:** FAST, NORMAL, MAX and UNCENSORED (automatic routing over
  installed local models), all running locally through Ollama.
- **Research:** NOW for live web research with sources, and DEEP for answers from
  your documents with page citations.
- **Create:** REIMAGINE image generation and editing (FLUX.2 Klein preferred, SDXL
  compatibility), AUDIO speech through a local VoiceStudio service, and VIDEO with
  target durations, long-form segments and image-to-video, all inside Chat.
- **Work:** Agent Workspace coding tasks with diffs, test runs and receipts; Linux
  desktop navigation (KDE).
- **OLIVE Notes and OLIVE Draw:** local-first notes and drawings that sync with
  the iPhone, including offline edits and image import.
- **OLIVE for iPhone:** a native companion with every desktop Chat mode (run by
  the paired computer), attachments, verified media results, Notes, Draw, Today,
  Files and Remote Studio.
- **OLIVE Connect:** pairing with mutual confirmation, pinned TLS 1.3 between paired
  devices, per-device Off/Ask/Allow permissions, record sync and resumable file
  transfer.
- **Connect World:** a self-hostable relay (`world-relay/`) that lets the phone
  reach the computer from any network without port forwarding, with automatic
  Direct ↔ World failover. The relay forwards end-to-end encrypted traffic it
  cannot read.
- Project licence ([LICENSE](LICENSE)), [security policy](SECURITY.md) and
  [third-party notices](THIRD_PARTY_NOTICES.md).
- Desktop packaging foundation: a self-contained Python backend (relocatable
  CPython 3.14.8 with hash-locked dependencies), Linux AppImage, per-user Windows
  installer and unsigned macOS DMG configuration. Only the AppImage has been built so
  far, and nothing is published.
- Runtime discovery: OLIVE finds its Ollama, ComfyUI, VoiceStudio and media-model
  folders itself and remembers them in `runtimes.json`, without moving anything.
  Missing or moved runtimes show *Needs setup*.
- macOS foundations: Keychain credential storage, opening files with `open`, and
  macOS runtime folders and process handling. None of this is validated on a Mac yet.
- **First-run setup:** a wizard for new profiles (name, system check, OLIVE Core /
  Creator / Complete, runtimes, models, verification, OLIVE Connect, Connect World).
  It installs only what the pinned runtime manifest allows: the Ollama 0.34.2 runtime
  (Linux, Windows), the FAST, NORMAL, NOW, embedding, vision and coding models from
  the Ollama library (registry digests pinned), and optional Playwright. Downloads are
  HTTPS-only, resumable and SHA-256 verified; archives are unpacked with path,
  link and size checks. Setup completes only after verification, including a short
  FAST answer. Existing profiles are never forced through it, and existing runtimes
  and models are reused, never replaced. Creator engines and models, MAX and
  UNCENSORED are shown as "not yet available in this build".
- A beginner guide to running your own Connect World relay
  (`docs/connect-world/self-host-relay.md`), also readable inside setup.
- Packaged backends carry `THIRD_PARTY-backend.txt`, the licence texts of every
  bundled Python distribution and CPython, also copied to `resources/legal/`.
- A draft end-user licence for official builds (`docs/legal/EULA-DRAFT.md`), marked
  for owner and legal review; it is not in force or shipped.
- **Release gate:** the runtime manifest (schema 3) separates *licence identified*,
  *engineering reviewed* and *release approved*. Setup offers a component only when the
  owner has approved its exact pins in `olive/runtime_manifest/release-approvals-1.0.0.json`;
  a changed pin voids the approval. No component is approved yet, so this build's setup offers
  nothing to download until the owner records approvals (`packaging/release/release_gate.py`).
- **Creator distribution groundwork:** reproducible, hash-locked ComfyUI runtime definitions
  for the image and video engines (`packaging/creator/`, built only in private CI, not yet
  published); FLUX.2 [klein] 4B (Apache-2.0) as the distributable REIMAGINE model, pinned by
  revision and SHA-256 (not yet validated in a real run, so it is not routed yet); an existing
  FLUX.2 [klein] 9B, community LTX set or VoiceStudio keeps working.
- Setup installs multi-file models (each file verified and renamed into place, never over an
  existing file) and checks free space per filesystem, so runtimes or models on another volume
  or bind mount are planned correctly.
- **Connect World relay release bundle:** `packaging/relay/build_relay.py` builds a standalone,
  deterministic `olive-world-relay-1.0.0.tar.gz` (relay only, no source checkout needed, no
  secrets). Not published yet; the beginner guide describes it.
- **Release CI (build only):** `.github/workflows/release-build.yml` builds unsigned desktop
  packages for Linux, Windows and macOS, the relay bundle and image, optional Creator
  runtimes and SHA256SUMS as private artefacts. It never publishes or signs.
- Packaged notices now include every runtime npm package's licence texts (with the fonts'
  OFL), Electron/Chromium notices in `resources/legal/`, and the licences of the libraries
  compiled into the bundled CPython.
- `packaging/release/check_ollama_pins.py` reports Ollama registry digest drift for review
  without ever changing a pin.

### Changed

- Product version metadata is 1.0.0 on the desktop and Python side. The iPhone
  app's version and bundle ID change in a later iOS release phase.
- The default embedding model is `qwen3-embedding:0.6b` everywhere (it was
  `nomic-embed-text` in some defaults). Profiles that already store an embedding
  model keep it. Without an installed embedding model, document retrieval stays
  lexical.
- `pyproject.toml` is the single source of Python dependency declarations; the Qt
  fallback (`qt`), Playwright browser (`browser`) and Studio tools (`studio`) are
  optional extras, never part of the packaged backend.
- Documentation moved under `docs/` with an index; historical reports are in
  `docs/archive/`.
- Windows-only features now say which platform they are unavailable on, instead
  of always naming Linux.
- Document vectors now record the embedding model that made them (`rag.sqlite3` schema 3,
  an added nullable column). Vectors from another model are no longer compared with the
  current model's queries; the index upgrade re-embeds them. Existing vectors are left
  exactly as they were.
- OLIVE Connect no longer offers loopback as a pairing network in Devices or setup (it
  cannot reach an iPhone). Developers can list it with `OLIVE_CONNECT_DEVELOPER_LOOPBACK=1`.
- Setup verification no longer blocks on Creator or Complete parts only you can install
  (such as VoiceStudio); Core still does.
- The Linux sandbox refusal is a tested function: the error dialog is shown first, and OLIVE
  exits with status 78 only after it is dismissed.
- New profiles no longer default the preferred name to the developer's name. It
  stays empty until you set it. Profiles that already store a name keep it.
- `run_olive.sh` no longer exports runtime paths; the backend discovers them, as a
  packaged app does. The `OLIVE_*` runtime variables remain optional overrides.
- On Linux, `scripts/install_linux_desktop_entry.py` now writes a visible
  `olive.desktop` and a hidden `local.dmdo.desktop.desktop`.
- Linux: OLIVE refuses to start without the Chromium sandbox. When an AppImage
  launcher falls back to `--no-sandbox` (no unprivileged user namespaces, for example
  Ubuntu 24.04 with AppArmor), OLIVE explains how to fix it instead of running
  unsandboxed. A clearly named developer-only override exists.
- Windows: `pywinpty` is now a core dependency, so the Studio terminal works in the
  packaged Windows backend (not yet validated on a Windows build).
- Research with Playwright uses Chrome, Edge or Chromium already installed and never
  downloads a browser; without them, research stays on HTTP pages.
- The Linux Creator image engine is a reproducible runtime archive that never contains
  NVIDIA's CUDA wheels or wheels that bundle NVIDIA components: setup downloads those 20
  pinned wheels from PyPI and unpacks them into the OLIVE-owned runtime (RECORD-verified, no
  pip) before checking and registering it.
  The archive is built and validated but not yet published, so setup does not offer it.
- An image engine that OLIVE started stops after it has been idle for the model keep-alive
  period (5 minutes by default, at least 1 minute), freeing several GB of memory. It never
  stops during a job, while another OLIVE job holds the GPU, while another client has queued
  work, or when someone else started it; the next request starts it again.

### Fixed

- iPhone FAST requests no longer fail with `input_too_large`: Remote AI caps the
  answer reserve at half of FAST's context window, as desktop Chat does.
- Connect World failover after Wi-Fi loss: a silently dead Direct connection no
  longer blocks the World connection for up to a minute.
- Linux: the window announces `olive.desktop`, so it groups under an OLIVE entry.
- Remote AI: a Stop or permission change arriving after a job had already ended no
  longer interrupts that job's cleanup, which could leave the model slot held.
- Research diagnostics and the browser provider no longer fail when the optional
  Playwright component is absent; research stays on HTTP pages.
- Windows VIDEO: the app-owned ComfyUI launch keeps the LTX GGUF loader enabled.

### Removed

- `run_dmdo.bat`. It only forwarded to `run_olive.bat`, which remains the Windows
  source launcher.

### Compatibility

- Existing `~/.dmdo` profiles are reused in place; `DMDO_*` environment variables
  are still accepted. Legacy identifiers that key stored state (`dmdo://app`,
  `local.dmdo.desktop`, the Windows `DMDO/` credential namespace, backup and
  record identifiers) are kept on purpose
  ([compatibility map](docs/architecture/legacy-dmdo-compatibility.md)).

### Known limitations

- No installer has been published yet for any platform.
- macOS desktop is an OLIVE 1.0 target but is not supported yet (no Keychain
  credential backend, Linux-only runtime management).
- A first Windows installer may be unsigned; SmartScreen will warn.
- OLIVE never downloads models automatically. Several models (the locally built
  UNCENSORED models, FLUX.2 Klein, LTX video, Qwen-Image 2.1) are not yet
  distributable until their source, checksum and licence are recorded.
- Desktop navigation and control are verified on KDE Plasma only.
- Only one hardware configuration has been measured (RTX 3080 Ti Laptop, 16 GB VRAM).
