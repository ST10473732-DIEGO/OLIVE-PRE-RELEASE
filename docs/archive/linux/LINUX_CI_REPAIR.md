# Linux portable CI repair

Validated 2026-09-19 on `platform/linux-l3`, starting from `7f85554`.
This changes CI and test fixtures only; application code, execution policy,
Studio defaults, dependency requirements and model services are unchanged.

## Causes and repairs

1. **Qt native loader dependencies.** Installing the PySide6 wheel does not
   install Ubuntu libraries linked by QtGui or QtWebEngineCore. Offscreen mode
   selects a platform plugin but does not remove these import dependencies.
   The reported missing `libEGL.so.1` is supplied by `libegl1` (Ubuntu noble
   candidate `1.7.0-1build1`). A verified official Ubuntu 24.04 base reproduced
   further missing libraries; `ldd` identified the remaining direct dependencies.
   The workflow now resolves candidates using the running image's apt metadata,
   installs only the following runtime packages with `--no-install-recommends`,
   and checks both QApplication creation and the preview interceptor import
   before running the suite. Existing `QT_QPA_PLATFORM=offscreen` is retained.

   | Packages | Required library/contract |
   | --- | --- |
   | `libegl1`, `libgl1` | QtGui EGL/OpenGL import linkage, even offscreen |
   | `libxkbcommon0` | QtGui keyboard library import |
   | `libfontconfig1` | Fontconfig and dependent FreeType for QtGui |
   | `libglib2.0-0t64`, `libdbus-1-3` | QtCore/QtGui GLib, threads and D-Bus linkage |
   | `libnss3` | QtWebEngine NSS/NSPR/SMIME libraries |
   | `libxcomposite1`, `libxdamage1`, `libxfixes3`, `libxrandr2`, `libxtst6`, `libxkbfile1` | QtWebEngine linked X libraries; no X server is started |
   | `libasound2t64` | QtWebEngine ALSA import linkage; no audio device required |

   Several packages already exist on hosted runners. Declaring the measured
   runtime set also permits testing on a minimal Ubuntu userspace. No Qt/XCB
   plugin bundle, desktop environment, GPU driver or model weights are installed.

2. **Stale LSP diagnostics and implicit providers.** `requirements-studio.txt`
   already pins python-lsp-server 1.15.0, pyflakes 3.4.0 and autopep8 2.3.2.
   No missing Python dependency needed adding. The original test checked whether
   the diagnostics cache was nonempty immediately after changing the document.
   Earlier code in the fixture produces E305, so asynchronous/debounced
   diagnostics from that earlier document could satisfy the wait. Even an
   undefined-name diagnostic for the intermediate `ad` buffer could falsely
   satisfy the old assertion. The fixture now explicitly enables Pyflakes and
   autopep8, disables competing bundled lint/format providers, and matches the
   published path **and document version**. It requires the Pyflakes diagnostic
   `undefined name 'unknown_name'`, not merely any warning. The workflow also
   imports the required Studio providers before the suite.

3. **Isolation assumed absent on the host.** The original test constructed a
   default registry, which discovers Docker. A working Docker provider correctly
   satisfies the untrusted-execution policy on hosted runners. The negative test
   now injects a registry with Docker explicitly unavailable, asserts the real
   PermissionError, and verifies neither provider was called and no run/process
   was registered. A separate available-provider fixture verifies dispatch to
   Docker only, with networking disabled. Its process is simulated; no untrusted
   command runs on the host and no Docker image is downloaded. Existing Docker
   command-limit tests remain intact.

Changed files:

- `.github/workflows/linux-portable.yml`
- `tests/test_linux_lsp.py`
- `tests/test_studio_run_ui.py`
- This report

## Verification

| Check | CachyOS | Isolated Ubuntu 24.04 userspace |
| --- | --- | --- |
| Affected tests | 53 passed | Included in full passing suite |
| Full Python suite | 854 total: **846 passed, 8 skipped** | 854 total: **843 passed, 11 skipped** |
| Frontend | **33 passed**, 12 files | **33 passed**, 12 files |
| Typecheck / lint / build | Passed | Passed |
| Qt offscreen creation / preview import | Covered by passing tests | Explicit preflights passed |
| Whole clean-source `compileall -q .` | Passed | Passed |
| Dependency consistency | Existing local environment | All 66 installed packages compatible |
| Workflow YAML / Bash syntax | Passed | Same workflow source |

The first local full run without the installed .NET SDK on PATH passed with
11 skips. Repeating with the native launcher's existing .NET toolchain PATH
enabled the three additional C# cases: 846 passed, 8 skips. Ubuntu's 11 skips
are the eight existing Windows contracts plus three cases requiring installed
OmniSharp/netcoredbg tooling. No skip conditions were added or broadened.

Ubuntu reproduction used an official Ubuntu Base 24.04.4 amd64 archive verified
against its published SHA256, extracted under a temporary directory. Bubblewrap
provided user/PID/mount namespaces; no host package or service was changed.
CPython 3.14.7 and the unchanged requirement files were installed with uv inside
that root. Node 24.21.0 ran `npm ci`, the explicit Electron installer, typecheck,
lint, tests and build against a separate tracked-source copy. Git and CA
certificates supplied baseline runner tools. No user profile, D-Bus socket,
model directories or GPU devices were mounted into the reproduction.

This is a CI-equivalent userspace check, not an execution of GitHub's hosted VM
or its action bootstrap. The unprivileged namespace needed apt to use its sole
mapped user, and fontconfig configuration was retried after its local-fonts
directory was created (the namespace cannot chown to an unmapped staff group).
Those namespace accommodations are not in the workflow. The clean-source
compile ran before dependencies were included in the checkout, as in CI.

The literal local `python -m compileall -q .` still reports the pre-existing
Jinja `__init__.tmpl.py` shipped inside ignored `.venv` PySide6 Android tooling.
Compiling the full tracked-source copy succeeds; CI installs dependencies
outside the checkout. No product/source compile failure was hidden.

## Action versions and remaining warnings

Updated checkout v4 → v6, setup-python v5 → v6 and setup-node v4 → v6 to maintained
Node 24 actions. Application Python remains 3.14, Node remains 24, and npm cache
inputs and all original verification stages are retained. Hosted GitHub runners
support the required action runtime. These versions are documented by the
[checkout maintainers](https://github.com/actions/checkout),
[setup-python maintainers](https://github.com/actions/setup-python) and
[setup-node maintainers](https://github.com/actions/setup-node).

`ubuntu-latest` remains unchanged. The Ubuntu 26 migration notice may remain;
this repair does not claim an Ubuntu 26 run. Package candidates and OS identity
will be printed on the actual runner. The current
[runner inventory](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md)
also confirms Docker is a normal hosted-runner capability. Ubuntu package
resolution uses the live apt repositories; the
[libegl1 package record](https://packages.ubuntu.com/noble/libegl1) documents its role.

Existing warnings remain: Python's 26 uncollectable objects at shutdown,
offscreen Qt raise/size-hint notices, Vite chunk size warning, and npm transitive
deprecation/install-script notices. They were not suppressed. No hosted Actions
run was triggered, so removal of its Node 20 warning is expected from the updated
action runtimes but awaits the next authorized push/run.

Native KDE/KWallet, NVIDIA, live Ollama/ComfyUI and Wayland acceptance remain
separate in `LINUX_L3_REPORT.md`. This portable job neither downloads large
models nor certifies those hardware/session contracts.
