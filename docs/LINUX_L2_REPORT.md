# OLIVE Linux L2 — local AI, OLIVE GO and Studio

Date: 2026-09-19. Branch: `platform/linux-l2`.
Starting checkpoint: `da5abda` (accepted L1). The initial checkout was clean on `platform/linux`; this task created `platform/linux-l2` from that checkpoint. L1 was retained rather than repeated.
Final implementation commit: `6cdf3851d5a253ae423935e788c2838b1a6e5bb0`.
The subsequent report-only completion commit is identified by `git log -1 --format=%H -- docs/LINUX_L2_REPORT.md` (a commit cannot embed its own hash).

## Outcome

The native daily-use journey passes on CachyOS: real local responses from FAST/NORMAL/MAX, OLIVE GO navigation, Python and C# interactive xterm input, Studio editing/tooling, route churn, and owned shutdown. Public Google search results remain constrained by Google's CAPTCHA. Generated project code still requires review and validation; a fully specified live calculator journey passed twice, while earlier invalid/truncated proposals were stopped honestly.

## Environment and installation evidence

Actual host commands: `uname -r`, `plasmashell --version`, session/XDG variables, `lscpu`, `free -h`, executable discovery, `nvidia-smi`, `dotnet --info`, Ollama version/list/ps/API, Python module inventory, and repository toolchain versions. Raw evidence and test logs are in `/tmp/olive-l2-evidence` on the acceptance host; these temporary files are not tracked product data.

| Component | Observed |
| --- | --- |
| CachyOS / kernel | x86-64, `7.2.6-1-cachyos` |
| KDE / session | Plasma 6.7.5, native Wayland; `WAYLAND_DISPLAY=wayland-0`, Xwayland `DISPLAY=:0` |
| CPU / RAM | i9-12900HX, 24 logical CPUs; approximately 62 GiB usable RAM |
| NVIDIA | RTX 3080 Ti Laptop GPU, 16,384 MiB VRAM, driver 615.71.09; CUDA UMD 13.4 |
| Hybrid graphics | Intel UHD Graphics 770/i915 also present; Ollama selected NVIDIA CUDA without PRIME overrides |
| Python | 3.14.7; existing L1 `.venv` retained |
| Node / npm / Electron | 24.21.0 / 11.19.0 / 44.3.0, existing L1 local toolchain and locked desktop dependencies |
| Git | 2.55.0, already installed |
| .NET | Initially absent; agent installed official SDK 10.0.401 into ignored `.toolchains/dotnet` |
| Ollama | Initially absent, no API/service/models; agent installed official Linux 0.34.2 into ignored `.toolchains/ollama` |
| Java | Absent; not required for the Python/C# acceptance journey, not installed |
| Python tooling | debugpy 1.8.21, python-lsp-server 1.15.0; added pinned pyflakes 3.4.0 and autopep8 2.3.2 for actual diagnostics/formatting |
| C# tooling | OmniSharp 1.39.15 and netcoredbg 3.2.0-1092, pinned Linux x86-64 archives |

No manual user installation or system package/service changes were made. The agent provisioned the small development dependencies and official local runtimes. Ollama's 1.43 GB runtime archive was SHA-256 verified against its official release metadata. Both C# archives were verified before extraction; an incomplete OmniSharp download was rejected, discarded and successfully downloaded again. No hash verification was bypassed. `pip check` passes.

The earlier L1 NVIDIA warning came from restricted execution: running the probe with host GPU access succeeds. Actual CUDA inference, rather than hardware enumeration alone, was verified in L2. No GPU offload environment was forced for Electron; the compositor retains its normal hybrid setup.

Sources for manual runtime installation: [Ollama Linux installation](https://docs.ollama.com/linux), [Ollama GPU support](https://docs.ollama.com/gpu), [Microsoft manual .NET installation](https://learn.microsoft.com/en-us/dotnet/core/install/linux-scripted-manual).

## Models and public presets

The user explicitly approved FAST, NORMAL and MAX downloads, **37.58 GB total**. All three downloaded successfully, including Ollama's digest verification. No model was deleted or silently substituted.

| Preset | Installed model | Download bytes | Manifest digest prefix | Real Chat / residency |
| --- | --- | ---: | --- | --- |
| FAST | `qwen3:8b` | 5,225,387,677 | `500a1f067a9f` | Answered recursion; 5,578,204,118 bytes resident on GPU; context 4096 |
| NORMAL | `gpt-oss:20b` | 13,793,440,755 | `17052f91a42e` | Answered recursion; 12,740,408,114 bytes resident on GPU; context 8192 |
| MAX | `qwen3-coder:30b` | 18,556,700,222 | `06c1097efce04` | Answered recursion; 20,430,074,616 total resident bytes, 15,338,506,812 GPU bytes; context 16384 |

These are API residency measurements for the tested contexts, not permanent VRAM guarantees. MAX uses host memory as well as NVIDIA; it does not fit entirely in 16 GB VRAM. The actual model inventory contains those three models only. DEEP retains native extraction/retrieval plus NORMAL; no vision or embedding model was downloaded. Lexical fallback remains available. Full DEEP vision acceptance is deferred. REIMAGINE generation remains unconfigured; no ComfyUI/SDXL installation was attempted.

Model switching retained exactly one resident model at each measurement. Streaming cancellation followed by a fresh successful answer passed. Idle retention follows the existing 300-second policy; cancellation does not promise immediate eviction. An existing external Ollama server remains running after OLIVE exits. When OLIVE starts its own server, normal shutdown closes that server and its runner; the API became unreachable and observed NVIDIA use returned to about 114–115 MiB.

## Platform changes and launch

```bash
./run_olive.sh
# Explicit native Wayland, also tested:
./run_olive.sh --ozone-platform=wayland
```

The launcher still resolves its own repository directory. It adds optional local .NET/Ollama toolchains to PATH and enables Linux-only automatic Ollama startup. `OLIVE_START_OLLAMA=0 ./run_olive.sh` disables automatic startup. Startup reuses a working server, serializes startup with a user-runtime lock, and only auto-binds `127.0.0.1:11434`. Alternate/remote endpoints remain externally managed. Owned servers disable cloud access and automatic model pruning. No system-wide service was installed, and there is no public LAN binding.

The new `LocalOllamaRuntime` owns only a process it creates. Shutdown cleanup runs in a `finally` block. Existing services are never stopped. The existing inference service, preset meanings, routing and permission checks remain shared. A confirmed shared resource-manager bug was fixed: HTTP 404 from a missing model no longer leaves that nonexistent model marked as resident and blocks every later switch. Actual missing-model → FAST recovery now passes, with no implicit substitute or download.

Studio reuses the existing terminal/session contracts and xterm UI. Linux dispatch selects a real PTY adapter; Windows still selects the original ConPTY implementation. Each Linux run has a controlling terminal and dedicated session supervisor. Subreaping is confined to that supervisor. Natural exit, Stop and Ctrl+C reap owned descendants, including a child that creates another session. Tests also keep an unrelated process alive. The same supervisor also covers pipe-based build/test jobs and LSP/DAP processes. It detects abrupt owner exit and reaps the subtree; app-started Ollama uses it too. Linux Studio disables detached shared .NET build daemons. There are no broad `pkill`/`killall` commands and no global backend subreaper.

Linux project interpreters prefer the workspace's `.venv/bin/python` or `venv/bin/python`, then the normal base Python interpreter. They do not default every workspace to OLIVE's tooling venv. The debugger adapter may run from OLIVE's venv while the debuggee retains its project interpreter. Installed tooling and Bash/POSIX shell choices are exposed through the existing controls; no layout, styling or design files changed.

Pinned C# tooling provisioning now chooses verified Linux tar archives or the original Windows zip archives. The Windows launcher, ConPTY implementation, credential backend, notifications and desktop automation remain present and unchanged in platform selection. Windows execution was not available on this host and is not reported as passed.

Fresh Linux data remains `$XDG_DATA_HOME/olive`, normally `~/.local/share/olive`. Explicit profiles and existing legacy profile rules remain authoritative. Ollama models are in `~/.ollama/models`. Tool binaries are ignored development dependencies under `.toolchains`; synthetic acceptance profiles are under `/tmp/olive-*`. No credentials, runtime databases, model files or personal profiles are committed. No persistence format changed.

## Acceptance results

- **Chat → Studio:** the fully specified calculator fixture created one workspace through real scoped approvals, saved model-generated source, passed project checks, ran expressions through actual stdin, preserved an unrelated file during the division-by-zero follow-up, then completed real xterm input and Browser/Studio/Chat navigation with no rejected requests. Model output is not deterministic: earlier attempts hit truncation, generated failing tests, an acceptance-only import restriction, and a response timeout. Those attempts were not counted as passes. The fixture now states its input grammar, starter compatibility and allowed imports explicitly; production prompts and preset meanings were not weakened to pass it.
- **Chat/local AI:** real FAST code response stayed in Chat without workspace, run or Agent-task creation. NORMAL answered recursion and provided Python calculator code in Chat. UI preset switching across all three named presets produced real local responses, with cancellation and recovery. Actual missing-model 404 followed by a real FAST answer passed. SDK transport fixtures additionally cover malformed JSON and recovery; existing tests cover empty/truncated streams, selected-record context and deterministic permission routing.
- **OLIVE GO:** comprehensive fixture/restart test passed on Wayland: address navigation, tabs, pin/reorder/duplicate/reopen, favourites/history, downloads, private boundaries, Customise/panels, geometry/resizing/125% zoom, route visibility and remote-page isolation. Remote pages retain no Node, no OLIVE bridge and no privileged preload. Safe folder opening already uses Electron's desktop shell adapter. Downloads never auto-execute.
- **Google:** real search URL loaded Google's response, but Google supplied its bot/CAPTCHA page. Browser navigation passed; usable public search results are **not certified** by that run.
- **Studio terminal:** both Python and C# passed actual xterm typing of `level`, `hello`, `radar`, Backspace, Enter, DOM paste through xterm, prompt without newline, Ctrl+C, Stop, normal exit and stale-input rejection. The combined launcher test left an input-waiting program running and verified all captured owned processes disappeared on application close.
- **Studio editor/Git:** real Monaco save, concurrent revision protection, dirty close, search, retained output, reviewed-command cancellation/Stop, and Git review with approval binding/dirty-history protection all passed.
- **Python tooling:** completion, hover, signature, definition, references, symbols, diagnostics, rename, formatting and debugger breakpoint/stack/variables/continue passed through real installed servers. Python code-action availability depends on optional plugins and is not claimed as verified.
- **C# tooling:** real completion, hover, signatures, definitions, references, workspace symbols, live unsaved diagnostics, formatting, rename and code actions passed. netcoredbg verified breakpoints, locals, stack, watches, step, continue and stale-generation rejection. A separate test also passed through Studio's actual controller, permission and filtered-environment path.
- **.NET:** actual SDK discovery, restore, build, interactive run and one generated MSTest passed. Existing process tests verify warning stderr with exit code zero is successful; failure remains based on process status/exit code.
- **Route churn:** Chat → OLIVE GO → Studio repeated three times with a browser document, project and terminal history; WebContents count stayed at two, with zero renderer errors and zero rejected `olive:call` requests. Existing terminal fixture tests also exercise route churn.
- **Backend interruption:** explicit disconnection notice, no automatic action replay, and restart recovery with a saved synthetic draft passed. Recovery requires restarting OLIVE, as stated in the existing notice; no unsafe automatic action replay was added.
- **Design:** inspected actual Chat and Studio screenshots. The accepted navigation, typography, colors, editor and xterm layout remain intact. Linux window captures use the owned Electron window, without implementing desktop control.

## Final verification

| Check | Result |
| --- | --- |
| Python source compilation | Passed for all repository source; ignored toolchains/venv excluded |
| Exact `python -m compileall -q .` | Fails only on the same ignored PySide6 Android `__init__.tmpl.py` Jinja template reported in L1; this is not executable OLIVE Python |
| Python full regression | 845 total: **837 passed, 8 explicit Windows-only skips** |
| Frontend unit tests | 31 passed, 11 files |
| TypeScript / ESLint | Passed |
| Vite production / Electron main+preload build | Passed |
| Applicable Electron acceptance | 11 distinct tests passed across the broad run and targeted final runs; includes real local AI and actual xterm input |
| C# actual restore/build/MSTest | Passed; one synthetic MSTest, no failures/skips |
| Python/C# LSP and DAP | Real installed adapters passed; included in Python totals |
| Missing model and stream recovery | Real missing-model → FAST passed; malformed/empty/truncated response fixtures passed |
| Native shutdown | 11 captured processes exited when reusing external Ollama; 13 in the initial app-owned run. Final supervisor-based startup and abrupt backend exit also passed subtree-exit assertions; the final host probe found no remaining OLIVE/toolchain processes and 114 MiB GPU use |
| Dependency consistency / diff check | `pip check` and `git diff --check` passed |

The eight explicit Python skips are two Windows Credential Manager tests, three Windows native UI ownership tests, one DPAPI diagnostic test, one ConPTY shell test and one WinForms desktop build. These are not Linux passes. Java/vision/REIMAGINE absence and unverified Python code actions are separate availability limits, not test successes. Python emits an existing shutdown GC ResourceWarning; owned process assertions pass independently.

The broad Electron run passed 9 of 10 tests; its additional legacy M2 Studio fixture still had a Windows Python path cached at collection. After porting that fixture, the final six-test ownership/Studio/Git run passed completely. Together they cover all 11 distinct selected cases with no unresolved fixture failure. Live model-generation variability described above remains a real limitation.

Repeat the non-model checks from the repository root:

```bash
export PATH="$PWD/.toolchains/dotnet:$PWD/.toolchains/node/bin:$PATH"
export DOTNET_ROOT="$PWD/.toolchains/dotnet" # when using the local SDK
.venv/bin/python -m compileall -q -x '(^|/)(\.venv|node_modules|\.toolchains|\.git)/' .
.venv/bin/python -m unittest discover -s tests -v
(cd desktop && npm run typecheck && npm run lint && npm test && npm run build)
```

Repeat the native live acceptance with the installed models, on an actual desktop session:

```bash
export PATH="$PWD/.toolchains/ollama/bin:$PWD/.toolchains/dotnet:$PWD/.toolchains/node/bin:$PATH"
export DOTNET_ROOT="$PWD/.toolchains/dotnet"
(cd desktop && OLIVE_LIVE_AI=1 OLIVE_LIVE_WEB=1 OLIVE_START_OLLAMA=1 npx playwright test \
  browser.spec.ts browser-public.spec.ts calculator-chat.spec.ts calculator-project.spec.ts \
  interactive-run.spec.ts linux-l2.spec.ts studio.spec.ts m2-studio.spec.ts m2-studio-git.spec.ts)
```

A fresh checkout needs native Ollama plus the selected models, a .NET SDK for C#, and `.venv/bin/python scripts/provision_studio_tooling.py` for optional LSP/DAP dependencies. The launcher discovers PATH tools or the documented ignored local toolchain directories; it does not download model files. The checked-in Linux CI now installs Studio Python tooling and exercises portable process/PTY tests; it does not certify a physical NVIDIA/KDE session.


## Known differences and L3 prerequisites

Windows-only credentials/live credential-dependent integrations, DPAPI diagnostics, Desktop Control, Windows startup, Windows notifications, WinForms execution and ConPTY-specific tests remain explicitly unsupported/skipped on Linux. Java is absent. No Linux secret-store fallback or plaintext credentials were introduced.

L3 can address the separately approved vision/embedding and ComfyUI/SDXL stacks, secure Linux credential integration, broader Python code-action plugins, and additional physical multi-monitor/fractional-compositor-scale checks. The Browser test's 125% page zoom is not a claim of testing every KDE fractional display scale or decoration theme. Google CAPTCHA is an external provider constraint. Concurrent clients of a server originally started by another OLIVE instance should use a separately managed Ollama service when they need independent lifetimes; the creating instance owns that server's shutdown.

OLIVE OS, Mobile, Connect, packaging, custom KDE shell and arbitrary Linux Desktop Control were not started.
