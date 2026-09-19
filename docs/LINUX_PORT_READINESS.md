# Linux port readiness

This is preparation for a future CachyOS/Linux port of the current OLIVE
application. It implements no Linux, mobile, Connect, desktop-shell or OS work.

## Portable core

- `olive/interaction/`: natural-language interpretation, capability routing and
  interaction context. Keep authorization outside model responses.
- `olive/agent/`, application controllers, repositories and JSON stores:
  planning, confirmation, persistence, task history and completion evidence.
- Knowledge extraction, chunking, indexing and lexical/semantic retrieval;
  local Ollama inference, preset policy and most research providers.
- Mail MIME handling, IMAP/SMTP and OAuth protocols; personal tasks, calendars,
  reminders, projects and memory. Existing data schemas and migration rules
  should remain the same, including reuse of legacy profiles in place.
- React/Monaco/xterm presentation, Electron IPC contracts, LSP/DAP protocols,
  build/test orchestration and local web previews.

Portable does not mean already tested on Linux. Audit path normalization,
case sensitivity, symlinks, executable discovery and packaging in each area.

## Windows boundaries and future equivalents

| Current boundary | Future Linux work |
| --- | --- |
| `olive/studio_tooling/pty.py`, pywinpty/ConPTY | POSIX PTY adapter behind the existing terminal service; process groups and reliable descendant cleanup; retain xterm and session ownership |
| Native process launch, `.exe`, PowerShell/cmd and `.venv/Scripts` discovery | Platform executable discovery, argument-array process launches, `.venv/bin`, explicit shell choices |
| `olive/desktop/windows_*`, UIA/pywinauto, HWND ownership/focus and WinForms | AT-SPI where available; compositor/session-specific observation and input adapters; retain ACT → OBSERVE → VERIFY |
| Windows Credential Manager and DPAPI diagnostics | Secret Service/keyring with no plaintext fallback; protected diagnostic storage and explicit user opt-in |
| Native notifications, tray and startup integration | Desktop notifications, tray support and user-session startup adapters; preserve reminder deduplication |
| Electron native browser views, focus, bounds and file/confirmation dialogs | Validate under both X11 and Wayland, fractional scaling and multiple monitors; preserve sandbox/private-session boundaries |
| Windows .NET debugger/OmniSharp paths, WinForms designer and owned GUI probes | Linux tool binaries and distribution checks; WinForms remains Windows-specific, with honest unsupported status |
| Windows `.bat` setup/launcher and backend packaging | Linux development launcher and packaging in the future port; do not translate shell strings mechanically |
| Windows path comparisons and vault/profile scope | Case-sensitive identity tests, permission bits, symlink containment and profile locks |

## Expected CachyOS dependencies

Plan for Python with venv support, Node/npm, Electron's required system
libraries, Ollama with the appropriate GPU runtime, .NET SDK when selected,
Python LSP/debugpy, and available C# language/debug adapters. Optional document
features need their existing parser/OCR dependencies. Optional ComfyUI/SDXL
needs a compatible PyTorch/GPU stack and locally installed model assets.
Do not automatically download large models or make a hosted service mandatory.

Exact package names and versions must be verified against CachyOS repositories
when that milestone starts. These are dependency categories, not an installation
script or a claim that the Windows dependency pins work on Linux.

## Blockers and recommended order

1. Establish isolated Linux CI for the portable Python core and frontend checks.
2. Audit path/permission/profile-lock behavior and implement the process and
   credential adapters needed to launch the application safely.
3. Port terminal sessions, owned process shutdown and toolchain discovery;
   repeat Python/C# frontend stdin, LSP, DAP and build/test acceptance.
4. Validate the Electron shell, OLIVE GO native views, dialogs, downloads,
   notifications, fractional scaling and restart on X11 and Wayland.
5. Validate local Ollama and optional media GPU handoff on real Linux hardware.
6. Port desktop observation first, then guarded input and verification using
   owned fixtures. Wayland may require explicit portals/user consent; never
   bypass compositor security to imitate Windows automation coverage.
7. Run the full isolated acceptance suite, then opt-in live local tests.

Desktop automation parity, credential migration, GPU compatibility and native
view/focus behavior require real Linux evidence. Preserve the Windows baseline
while resolving these; no general promise of arbitrary-app automation is made.
