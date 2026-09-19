# OLIVE workbench redesign + real Studio IDE — working status

Branch `design/olive-workbench-redesign`, created from `design/olive-complete-ui-refresh`
at `26e9504` (which sits on the M4-complete baseline `b1fee22`). This file is the
resumable record for the brief "structural experience redesign + real Studio IDE".
Update it at every checkpoint; do not restart from scratch.

## Verified tooling (2026-09-12)

| Need | Choice | Version / provenance | Licence | Probe result |
| --- | --- | --- | --- | --- |
| C# language service | OmniSharp-Roslyn (LSP mode, net6.0 build, rollForward LatestMajor) | v1.39.15 `omnisharp-win-x64-net6.0.zip`, sha256 `b03eb6b9…8658e8` | MIT | initialize 6 s; completion, hover, definition across projects, references, signature help, workspace symbols, formatting, diagnostics on unsaved text all real |
| .NET debugger | netcoredbg (DAP `--interpreter=vscode`) | 3.2.0-1092 `netcoredbg-win64.zip`, sha256 `3c410a45…9274a` | MIT | launch, verified breakpoints, stopped, threads, stack, scopes, locals with values, evaluate, next, continue, disconnect |
| Terminal | pywinpty (ConPTY backend) | 3.0.5 (PyPI wheel cp314) | MIT | input echo, `set /p` receives typed value, resize reflected, Ctrl+C interrupts |
| Python debugger | debugpy | 1.8.21 (PyPI) | MIT | installed; adapter probe pending |
| .NET SDK | installed | 10.0.400 (runtimes 6/8/10) | — | `.slnx` is the default solution format; OmniSharp loads projects by directory scan |

Tooling lives in `.toolchains/studio/` (ignored) provisioned by `scripts/provision_studio_tooling.py`.

OmniSharp client rules learned: point `-s` at the workspace directory; declare
`dynamicRegistration` and wait for `client/registerCapability` before document
notifications; server request ids can collide with client ids (distinguish by
`method`); after `o#/projectadded|projectchanged` re-assert open buffers with a
full-text `didChange` (didOpen text is dropped by the initial project load).

## Architecture decisions

- Tooling processes (LSP, DAP, PTY, dotnet CLI) are hosted by the Python runtime
  (`olive/studio_tooling/`), behind the existing tool registry / permission engine
  and approved-workspace checks; the renderer reaches them only through validated
  bridge methods (`olive/bridge/contracts.py` + `desktop/electron/*contracts.ts`).
  Output streams are bridge events (`lsp.diagnostics`, `dap.event`, `terminal.data`,
  `tests.results`, `build.output`).
- The shell becomes a workbench: top bar (Core + state, Home, work-item tabs,
  Spaces launcher, Commands, Settings); tabs are stable work items keyed by
  kind+record id; feature views stay mounted while their tab is open.
- Studio: editor-first; explorer, bottom tool dock (Terminal, Problems, Tests,
  Output, Git, Debug) and the assistant open on demand and remember their state.

## Checkpoints

- [x] 0 Audit + tooling probes (this file)
- [x] 1 Backend: provisioning script, tooling package (dotnet, lsp, dap, pty, tests,
      run configurations, web inspector), bridge routes/contracts, Python tests
      (commit 8982efc; 11 tooling tests + full Python suite green)
- [x] 2 Shell: workbench bar, work items, Spaces launcher, Home (commit b72506e)
- [x] 3 Studio IDE UI: Monaco LSP wiring, debug UI, terminal, tests, run configs,
      project system, preview/request inspector (commit b72506e). Python workflow
      verified end-to-end through the UI: LSP ready + hover, native terminal input,
      structured tests, real debugpy session (breakpoint, locals, step, continue).
- [~] 4 Other pages recomposed: Chat is conversation-first with on-demand history;
      Mail is two-pane reading with full-width compose and no compulsory third pane;
      Agent/Research keep their task/result composition; Home rebuilt around open work.
- [~] 5 E2E updated to the workbench navigation (tests/e2e/shell.ts helper);
      Python Studio acceptance captured; C# acceptance + full regression + report
      in progress.

## Post-brief-3 findings

- Renderer event delivery: a lazily-loaded chunk that registers its own
  `window.olive.subscribe` under the sandbox stops receiving events after the
  first one. The tooling store therefore does not self-subscribe; the single App
  subscription forwards every event to `tooling.handle`. The store module is
  pinned to one chunk (`vite.config.ts` manualChunks) so App and the lazy Studio
  chunk share one instance.
- Event-loop starvation: `module_available` and `dotnet_info` used blocking
  `subprocess.run`/repeated probes that froze the asyncio loop while a language
  server was initialising, leaving pylsp/OmniSharp stuck in "starting". Both are
  cached now; language servers reach "ready" in ~1 s.
- netcoredbg `internalConsole` provides debuggee stdout via output events but no
  stdin; documented as a limitation.
