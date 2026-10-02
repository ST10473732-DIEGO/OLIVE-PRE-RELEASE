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

### Fixed

- iPhone FAST requests no longer fail with `input_too_large`: Remote AI caps the
  answer reserve at half of FAST's context window, as desktop Chat does.
- Connect World failover after Wi-Fi loss: a silently dead Direct connection no
  longer blocks the World connection for up to a minute.
- Linux: the window announces `olive.desktop`, so it groups under an OLIVE entry.
- Remote AI: a Stop or permission change arriving after a job had already ended no
  longer interrupts that job's cleanup, which could leave the model slot held.

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
