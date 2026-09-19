# Linux application readiness

OLIVE now has native Linux launch, local inference, Studio terminals, secure
credentials, notifications and user-session startup integration. This document
tracks the application, not an OLIVE OS, ISO, custom desktop shell, Connect,
Mobile or cross-device milestone.

Validated checkpoints and detailed classifications:

- [L1: native launch, portable data and Wayland](LINUX_L1_REPORT.md)
- [L2: local NVIDIA inference, OLIVE GO and Studio](LINUX_L2_REPORT.md)
- [L3: native services, DEEP/media and parity evidence](LINUX_L3_REPORT.md)
- [Preserved Windows baseline](WINDOWS_STABLE_BASELINE.md)

## Supported application foundation

| Area | Linux implementation and evidence |
| --- | --- |
| Launch | `./run_olive.sh`; native KDE Wayland/default display launch; single profile instance and owned shutdown |
| Data | XDG fresh profile, configured paths authoritative, existing legacy profiles retained; no destructive migration |
| Local AI | Ollama, NVIDIA FAST/NORMAL/MAX; cancellation, model switching and supervised app-owned runtime |
| DEEP | Native parsing/OCR, bounded retrieval and citations; real qwen3-vl:8b scanned-page inference passed in L3 |
| Studio | POSIX PTY, Python/C# interactive input, local LSP/DAP, Git and Monaco; Windows ConPTY retained |
| Mail credentials | SecretStorage → Secret Service → KWallet, encrypted sessions, fail closed when locked/unavailable; synthetic OAuth and provider readiness |
| Notifications | Linux Electron/Plasma adapter; bounded completion events, durable deduplication, native reminder/restart acceptance |
| Login startup | Explicit XDG user autostart enable/disable commands; no daemon/root service; real logout/login still manual |
| Browser | Native sandboxed views, local fixture navigation, downloads, private storage and restart; Google CAPTCHA remains an external constraint |
| REIMAGINE | Fixed loopback ComfyUI workflows and SDXL; lazy managed Linux runtime with owned cleanup; real generation/edit/cancel and both Chat handoffs passed with `--cache-none` |
| Personal features | Tasks, calendars, reminders, projects, knowledge, memory and Mail local data covered by native UI/portable regression |

## Desktop Control is a foundation, not Linux automation parity

Linux session detection and honest unavailable UI are implemented. KDE's
Screenshot and RemoteDesktop portals are present on the acceptance host, but
OLIVE does not yet request consent or implement a portal input/capture session.
The AT-SPI user bus is present, but AT-SPI and Linux window enumeration are not integrated. There is no certified
Linux focus/observe/verify adapter, under either Wayland or X11. Do not force X11
or grant root privileges to imitate Windows automation.

Explicit application copy/paste, native file dialogs, Electron shell operations
and xdg-open remain separate from Agent desktop authority. Windows native entry
points reject Linux, including below the bridge. Existing deterministic scopes,
confirmations, emergency stop and model-untrusted boundaries remain authoritative.

## Remaining validation and parity gaps

- Physical X11 session, multiple monitors/fractional scaling and real native
  picker interaction require manual acceptance. Controlled picker responses in
  automated tests do not certify those dialogs.
- Actual logout/login startup and user-visible notification presentation under
  DND/session lock require manual checks. Reminder popup acknowledgement and
  restart deduplication have automated native coverage.
- Linux Desktop Control needs consent-aware portal/AT-SPI adapters and owned
  fixtures before exposing controls. X11-only capabilities must be labelled.
- Windows native execution is not certified by Linux fixture passes; run the
  preserved native Windows suite before a cross-platform release.
- Java and optional Python language-server code actions remain outside this
  milestone's certified toolchain coverage.
- DPAPI diagnostics remain Windows-only; Linux uses safe metadata diagnostics.
- Clean-machine packaging/installer certification remains separate. This
  checkout's provisioned runtimes and models are local ignored installations.

Use the L3 report's test totals and failure/skip/manual classifications for the
acceptance decision. Do not interpret missing capability rows as passed tests.
