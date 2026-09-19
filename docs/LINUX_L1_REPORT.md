# OLIVE Linux L1 — native CachyOS foundation

Date: 2026-09-19. Branch: `platform/linux`.
Starting commit: `95d3a3b` (clean Windows stable snapshot; the local history contains only that snapshot).
Final implementation commit: `648d661a9640899929f18e1d3cfc4a469bb59ac8` (foundation in `fa4f28c82c147e55a3e1941e34b2d0f4a8089ff7`, followed by tested unavailable-message preservation).
The report-only completion commit is identified by `git log -1 --format=%H -- docs/LINUX_L1_REPORT.md`; a commit cannot embed its own hash.

## Outcome

**Native launch acceptance passes on this CachyOS host.** `./run_olive.sh` opens the existing Electron/React application. Both default display selection and explicit Wayland launch passed the automated L1 journey, with zero renderer errors and all nine captured owned processes gone after each normal close. No model inference, account login, external send, model download, OS development, or visual redesign was needed.

Chat, Projects, Knowledge, Memory, Tasks, Calendar, Reminders, Agent, offline Mail, Settings and Activity open and navigate. Activity retains its existing sheet, opened from the OLIVE activity button. Studio and OLIVE GO also open. Synthetic Projects, Memory, Tasks, Calendar events, Reminders and Mail drafts save through the existing interface. A synthetic document ingests and returns lexical retrieval evidence with Ollama unavailable. Memory survives renderer reload. These are bounded L1 checks, not full Linux feature parity.

The captured Chat screenshot was inspected: existing navigation, typography, workspace structure, colors and OLIVE core render correctly. No CSS, layout, Studio or OLIVE GO design files changed. Only the existing Desktop Control notice and Mail connection status gained Linux availability wording.

## Environment and dependencies

| Item | Observed state |
| --- | --- |
| OS/kernel | CachyOS, Arch family; `7.2.6-1-cachyos`, x86-64 |
| Desktop/session | KDE Plasma; `XDG_SESSION_TYPE=wayland`, `WAYLAND_DISPLAY=wayland-0`, `DISPLAY=:0` |
| XDG | `XDG_DATA_HOME` unset; standard home-relative fallback applies |
| Python | System Python 3.14.7; no initial pip or repository venv; `python -m venv .venv` succeeds and supplies pip |
| Node/npm | Initially absent; provisioned official Node 24.21.0 and npm 11.19.0 in ignored `.toolchains/node-v24.21.0-linux-x64`, with `.toolchains/node` symlink; official SHA256 manifest verified before extraction |
| Electron | Locked Electron 44.3.0 Linux runtime installed; `ldd` reports no missing libraries |
| Desktop libraries already present | glibc 2.44, GTK 3.24.52, NSS 3.129, ALSA 1.2.16.1, libXss 1.2.5, libdrm 2.4.134, Mesa 26.2.3 |
| Git | 2.55.0, already present |
| .NET / Java | Absent; optional developer toolchains left uninstalled |
| Ollama | Executable absent; no daemon or model installed/started |
| GPU | Intel UHD Graphics 770 enumerated; `nvidia-smi` exists but cannot communicate with the NVIDIA driver. No GPU inference claim |
| Native opener | `/usr/bin/xdg-open` already present |
| Secure Linux vault | No adapter selected or installed; credential-dependent integrations explicitly unavailable |

Agent-provisioned dependencies, not manual user installations: the isolated Node runtime, Python requirements plus loopback Mail test requirements, `npm ci` using the committed lock, and the locked Electron installer. PySide6 6.11.2 was resolved within the existing bounds. `pip check` passes; npm reported zero vulnerabilities at installation. No system package manager changes were made. No dependencies were installed manually by the user during this task.

Native Node components include Linux GNU builds of Rolldown and Lightning CSS, and Electron's platform-specific archive extraction helper. There is no node-pty dependency to port for L1: Studio uses Python ConPTY and remains deferred on Linux. No case-sensitive frontend import failures were found. Dependency pins and the lockfile were retained.

`AGENTS.md`, both required baseline/readiness documents, architecture and Electron/Python boundary documentation were read. `CLAUDE.md` is absent from this checkout.

## Launcher and data

From this checkout:

```bash
./run_olive.sh
```

Explicit Wayland selection is also tested:

```bash
./run_olive.sh --ozone-platform=wayland
```

The launcher finds its repository relative to the script, uses the optional local Node toolchain or Node/npm on PATH, creates a Linux venv when missing, installs declared requirements when their fingerprint changes, installs missing desktop dependencies/Electron, builds the renderer and main/preload, then replaces itself with Electron. Electron starts exactly one Python bridge over private pipes and owns shutdown. SIGINT/SIGTERM enter Electron's cleanup path. Installation/build errors return nonzero. Windows `run_olive.bat` is unchanged. No Ollama daemon is necessary for offline startup.

A new clone needs Python with venv support and a supported Node/npm installation; Node itself is not downloaded by the launcher. The local toolchain described above is ignored machine setup, not committed source. No fixed repository or personal home path is embedded.

Fresh Linux application data: **`$XDG_DATA_HOME/olive`**, or **`~/.local/share/olive`** when XDG_DATA_HOME is unset or relative. Browser/session data remains below `electron-shell` in that profile. Databases, JSON, attachments, logs, Mail state and browser profiles stay outside the source checkout. The launcher uses `umask 077`.

`OLIVE_DATA_DIR` (and compatible `DMDO_DATA_DIR`) remains authoritative. Existing nonempty `~/.olive` or `~/.dmdo` profiles are reused in place. Conflicting occupied locations require an explicit configured path; nothing is merged, copied, deleted or overwritten. Python and Electron implement matching resolution rules. Windows fresh defaults remain `~/.olive`. No persistence schema changed and no live Windows databases were imported.

All acceptance profiles were generated under `/tmp/olive-*`. To repeat isolated acceptance:

```bash
export PATH="$PWD/.toolchains/node/bin:$PATH" # only when using the provisioned local Node
cd desktop
npx playwright test linux-l1.spec.ts
```

## Platform audit and boundaries

A targeted executable/import/platform search found 474 matches in 120 files across runtime, Electron and scripts. Documentation, compatibility names and synthetic Windows fixtures were reviewed as historical/Windows material, not mechanically translated. Classes below describe the current boundary; some rows include follow-up work.

| Classification | Area | L1 treatment |
| --- | --- | --- |
| A — portable already | ServiceContainer, bridge framing/IPC, natural-language interpreter/router, permissions, Agent plans/repositories, JSON/SQLite stores | Shared implementation retained; unit/regression suite and native startup exercise it |
| A | Parsing vs chunking/indexing/retrieval, Memory/Projects/Personal Core/Mail local MIME | Shared stores, lexical fallback and offline operations verified; semantic inference requires a future local model |
| A | Profile writer lock | Existing POSIX `flock` path retained; lock tests pass |
| B — small abstraction | Fresh profile paths / XDG / `.olive` / `.dmdo` conflicts | Matching Python/Electron resolver changes, with explicit Linux and Windows-default tests |
| B | `.venv/Scripts/python.exe`, `.exe`, Electron Python spawn, icons | `desktop/electron/platform.ts` selects native venv executable and PNG icon; Windows branch retained |
| B | Dependency plans and bounded Python commands | `olive/platform_support.py` supplies platform venv path; Linux Python commands use the running interpreter; Windows shell strings remain Windows-only |
| B | Open file/folder | Windows retains `os.startfile`; Linux uses argument-array `xdg-open`, with checked exit, timeout and honest missing-opener failure; existing permission boundary stays authoritative |
| B | Electron shutdown | Existing private bridge cleanup retained; POSIX signal handlers added; native acceptance checks process identities and creation times after close |
| C — Windows-only | `olive/desktop/windows_*`, UIA, Win32, pywinauto, HWND/focus, registry, Explorer, tasklist/taskkill, application automation | Native operations reject explicitly on Linux; Desktop Control status explains unavailability. No simulated Wayland input |
| C | Windows Credential Manager, `win32cred`, DPAPI | Secure vault remains Windows-only. Linux rejects storage/read/remove with no plaintext fallback. Mail/Discord secret entry clears transient request values; DPAPI diagnostics stay Windows-only |
| C | ConPTY / pywinpty / PowerShell / cmd.exe | Explicit Linux unavailable errors; Windows terminal retained; pywinpty dependency now has a Windows marker. Bounded Python commands work independently |
| C | `.bat` / `.cmd`, PowerShell setup and WinForms tools | Retained Windows scripts/templates/fixtures; new shell launcher is separate |
| D — future Linux implementation | POSIX PTY, native application discovery/control, Secret Service, protected diagnostics | Deferred with explicit unavailable states, rather than emulation or insecure storage |
| D | Windows OmniSharp/netcoredbg paths, optional Java/.NET SDK | Missing toolchains already report unavailable; Linux tool distribution and interactive Studio acceptance belong to L2 |
| D | OS notifications / tray / startup integration | Current Electron shell has no native tray/autostart implementation to port; in-app reminder delivery remains shared. Qt notification/tray fallback retained, not certified as Linux native notification parity |
| A / D | Electron dialogs, shell file actions, external URLs, native browser views | Existing cross-platform Electron APIs retained. Sandbox/context isolation/permission denial/external-link approval remain intact. Picker response is controlled in L1 automated ingestion; real portal dialogs, outward link approval and full browser-view parity need further native acceptance |
| C / D | Packaged backend artifact guard | Windows packaging retained; this is a development launch milestone, not a Linux installer/distributable certification |

Windows-looking separators and drive paths remain in Windows adapters, templates and synthetic fixtures where intentional. Windows credential namespace case folding is retained for compatibility; a future Linux vault must use case-sensitive profile identities. No broad path-string replacement was performed.

## Verification evidence

Local logs are under `/tmp/olive-l1-*.log`; screenshots and acceptance metadata are under ignored `desktop/test-results/linux-l1-*`. They are synthetic local artifacts, not tracked user data.

| Check | Result |
| --- | --- |
| Exact `.venv/bin/python -m compileall -q .` | Ran; fails solely on installed PySide6 Android `__init__.tmpl.py`, which contains Jinja syntax, under ignored `.venv`. This is not marked passed |
| Compile source, excluding `.venv`, `node_modules`, `.toolchains` | Passed: `.venv/bin/python -m compileall -q -x '/(\.venv|node_modules|\.toolchains)/' .` |
| Full Python discovery | 833 tests: 818 passed, 15 explicitly skipped; zero failures/errors |
| Frontend unit tests | 31 passed in 11 files |
| TypeScript / ESLint | Passed |
| Vite production renderer / Electron main + preload build | Passed, including builds invoked by the launcher |
| `bash -n run_olive.sh` / `pip check` / `git diff --check` | Passed |
| Default launcher acceptance | Passed; requested pages, synthetic CRUD, lexical retrieval, reload, sandbox checks; 9 owned process identities reaped |
| Explicit Wayland launcher acceptance | Passed; same journey and 9 owned process identities reaped |
| Linux CI workflow | Added `.github/workflows/linux-portable.yml` for Python and frontend checks; not remotely executed. Native compositor acceptance remains a local CachyOS test |

The fifteen Python skips are explicit, not Linux passes:

- Three ConPTY program/input tests, two terminal/controller ConPTY tests.
- Three Win32 owned-window/focus tests.
- Two Windows Credential Manager tests and one DPAPI diagnostic test.
- Two C# LSP/DAP tests needing .NET plus OmniSharp/netcoredbg.
- One optional Python debugpy test (not installed).
- One WinForms SDK compilation test (.NET absent).

Windows adapters also retain inert fixture tests on Linux; these exercise shared safety/dispatch behavior, not live Windows OS support. Windows-native functions were not removed. A future Windows checkout should run its full native suite; no new Windows-host certification is claimed.

Earlier runs were not clean: test harness selectors incorrectly assumed an Activity navigation page, a Chat heading and an address textbox; those were aligned with the existing design. Python failures identified missing Windows-only skip declarations and `python.exe` discovery, and exposed a transient secret-clearing regression during implementation, which was corrected and regression-tested. The execution sandbox also stalls even a minimal `asyncio.to_thread` probe; integration checks ran through the approved external execution path instead. Earlier diagnostic processes were stopped. The full Python run retains the baseline warning about 26 uncollectable objects at shutdown; this is separate from the successful native owned-process checks.

## Remaining for L2

1. POSIX PTY and interactive Studio sessions, process-group/descendant cleanup under active work; Linux Python/C#/Java LSP/DAP toolchain acceptance.
2. Verify a desktop Secret Service/keyring adapter, fail closed when locked/unavailable, then opt-in real provider authentication. Never add a plaintext fallback.
3. Native notification/portal/tray/autostart integration and real file-dialog acceptance; explicit X11, scaling and multi-monitor checks.
4. Broader OLIVE GO remote-page/native-view security, download and restart coverage on Linux. Existing security code remains unchanged.
5. Resolve host NVIDIA driver availability and install Ollama/models only when requested; test semantic retrieval/inference/media separately.
6. Wayland desktop observation and guarded input only through supported compositor/portal interfaces, with explicit consent; no Windows automation emulation.
7. Linux backend packaging/installer, clean-machine setup and Windows regression verification before any merge/release.

No merge, push, tag, release or history rewrite was performed.
