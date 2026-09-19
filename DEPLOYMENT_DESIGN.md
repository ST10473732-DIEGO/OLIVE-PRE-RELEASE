# OLIVE deployment design

The 3.4 development runtime adds opt-in Windows control. It starts no UIA workers or interactive
browser merely by opening Home. Each UIA operation uses a bounded helper process and a shared
emergency-stop event. Interactive Chrome/Edge uses a dedicated profile under OLIVE data; it never
imports the normal user browser profile. Browser credentials and screenshots are not included
in the explicit application backup component list. No unattended login, send or purchase is
part of live validation. Source execution is tested; frozen helper startup remains packaging work.
Windows media support loads PyWinRT bindings lazily. No media session or clipboard content
is collected merely by opening Home. Browser downloads retain untrusted quarantine metadata;
moving an approved download uses the existing filesystem permissions. Active desktop operations
finish cancellation cleanup before shared resources close.
Final acceptance uses installed Chrome for interactive and system-media tests. Gmail
requires manual login in the approved profile. No credentials, downloaded models or
production user data are bundled by acceptance checks.

OLIVE 3.3 remains a native PySide6 / Qt Windows desktop application. Docker is not required.

Research uses public HTTP reads and optional Playwright-rendered reads through a OLIVE-owned public-only proxy. Each rendered page uses a fresh nonpersistent context with no imported cookies, passwords or normal browser profile. Edge can supply the installed executable; otherwise Chromium setup is manual. This is browser sandboxing and constrained egress, not a claim of a separate OS security boundary for the Python process. Future disposable browser workers can strengthen that boundary without changing the Research observation contract.

Research sessions, reports, subscriptions and approved web bodies are backed up alongside Knowledge metadata and RAG. Temporary page cache and quarantined download bytes are excluded from backups. Subscriptions remain disabled; restart never resumes network activity automatically.

## OLIVE 3.2 optional execution isolation

Docker Desktop may be used only as an optional execution provider for untrusted project code. OLIVE does not install or start Docker. Containers receive one approved workspace mount, no Docker socket, no host-root access, a non-root user, bounded CPU, memory, processes, output and runtime, filtered environment variables, and no network by default. Trusted and approved workspaces continue using the native Windows provider.

## Native Windows trust boundary

- PySide6 / Qt 6 desktop UI with one shared background runtime
- confirmation dialogs and permission settings
- local Tool Host
- Windows filesystem, terminal, and application launching
- local Ollama runtime and optional Tesseract
- user data under `~/.olive`

Host-specific controls must not be placed into an unrestricted container. A future separate Windows Tool Host must authenticate its client, validate schemas, enforce the same permission decisions, constrain paths/time/output, and return normalized `ToolResult` records.

## Optional future service boundary

Future Docker services may contain an agent API, isolated browser/research workers, Tor research worker, PostgreSQL, a vector store, and background schedulers. They receive no implicit host filesystem or desktop-control access.

Conceptual future composition:

```yaml
services:
  agent-backend: { profiles: [server] }
  research-worker: { profiles: [research] }
  browser-worker: { profiles: [research] }
  tor-worker: { profiles: [tor] }
  postgres: { profiles: [server] }
  vector-store: { profiles: [server] }
```

This is a design boundary, not a committed deployment. Each remote worker will require authentication, least privilege, explicit source provenance, resource limits, and auditable requests. Native operation remains the supported default.

## Qt desktop deployment

`main.py` launches one Qt shell with Home as its initial page. Cached workspaces share
one service container. Tray actions activate the shell and navigate without duplicate
windows; explicit pop-outs reuse page instances. The tray does not enable permanent
background operation by default. Closing the main window checks unsaved files and
invokes graceful cancellation of generation, agent work, indexing, terminal and run
processes. Restoring a backup requires idle services and a restart before further mutations.

PySide6 Widgets are the baseline. WebEngine is loaded lazily for an isolated localhost preview, not general browsing. No QML or Monaco assets are required. Package Qt plugins and WebEngine subprocess/resources together; see PACKAGING_WINDOWS.md. The desktop lock prevents two Qt runtimes from opening the same data directory. Existing v2/v3 stores and migration paths are preserved; UI layout is noncritical, separately stored state.


OLIVE was formerly named DMDO. See [the rebrand compatibility map](docs/OLIVE_REBRAND.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
