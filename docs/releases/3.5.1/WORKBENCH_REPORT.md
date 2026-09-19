# OLIVE — structural experience redesign + real Studio IDE

Final report for the brief "replace the old application composition, not just its
styling", delivered on branch `design/olive-workbench-redesign`. Not merged, not
tagged; defaults unchanged; no code paths removed.

## Commits

- Starting point: `26e9504` (post brief-2), which sits on the M4-complete
  baseline `b1fee22`.
- Work:
  - `8982efc` Studio tooling runtime (LSP, DAP, ConPTY terminals, .NET project system)
  - `b72506e` Workbench shell + wired Studio IDE UI
  - `1f68b6c` Chat and Mail recomposition; Studio tests aligned to the dock model
  - `2fbeec4` C# multi-project solution acceptance probe
  - `70ef932` Recomposed-pages capture

Launch (unchanged): from `desktop/`, `npm run build` then `npm start`, or the
isolated preview used for review (`electron .` with an `OLIVE_DATA_DIR` profile).
Studio tooling is provisioned once with
`python scripts/provision_studio_tooling.py`.

## Interaction model (what changed structurally)

The permanent full-height navigation spine, the fixed right-hand assistant, the
empty bottom panels and the repeated per-page structure are gone. With colour
and icons removed the new layout is still obviously different: a single thin top
bar over full-bleed content, tabs for open work, and no side rail.

- **Workbench top bar** (`desktop/src/app/WorkbenchBar.tsx`) is the whole shell:
  the OLIVE Core + live runtime state (opens the activity centre), an explicit
  Home control, the work a person actually has open as **tabs**, an overflow
  switcher, and on-demand **Spaces**, **Commands** and **Settings**. There is no
  permanent rail.
- **Work items** (`desktop/src/app/workbench.ts`) are stable identities keyed by
  kind (+ record id): a conversation, a coding workspace, a research session, a
  mail workspace. A tab's kind stays mounted while the tab is open and hides when
  inactive, so drafts, terminals and debugger views survive tab switches and
  navigation. Opening another conversation from Chat, or another workspace from
  Studio, retargets the active tab in place. Overflow is a switcher/menu.
- **Spaces launcher** (`desktop/src/app/Launcher.tsx`) replaces the global
  sidebar: an on-demand, grouped directory of every space, searchable, that
  closes as soon as a space is chosen. `Ctrl+Shift+O` toggles it.
- **Home** (`desktop/src/features/Home.tsx`) has a substantially different
  hierarchy: a compact composer, "Open now" (the real open tabs), "Recent"
  (de-duplicated against what is already open), a restrained "Right now" panel
  driven only by real runtime activity and approvals (no fabricated activity),
  pinned Spaces, and the native Today. It uses the existing snapshot/activity
  data, not mock content.

## Studio: a real IDE

`desktop/src/features/Studio.tsx` is editor-first: a compact command bar, a
toggleable Files + solution pane, the editor, an on-demand **bottom tool dock**,
a compact **labelled control strip** (never an empty panel — panels open on
request, on an operation, or on a failure), and an assistant opened on request.

- **Code intelligence** (`desktop/src/features/studio/languageClient.ts`) wires
  Monaco to the maintained language servers through validated `lsp.*` bridge
  methods: completion (+resolve), hover, signature help, go-to-definition,
  find-all-references, document/workspace symbols, live diagnostics as markers,
  formatting, **rename with a reviewed multi-file edit preview**
  (`EditPreview.tsx`), and code actions. Unsaved editor buffers are synchronised
  to the server; results that arrive after the buffer moved on, or after a
  cancelled token, are discarded; server-initiated `workspace/applyEdit` becomes
  a reviewed proposal and never writes files directly.
- **Debugging** (`debugClient.ts`, `DebugPanel.tsx`) over `dap.*`: gutter
  breakpoints with verification, current-line, call stack, scopes/locals,
  watches, exception filters and a debug console, with generation-based
  stale-reference protection.
- **Terminal** (`TerminalPanel.tsx`) is a real interactive xterm ↔ ConPTY
  session: typed input, resize, Ctrl+Shift+C/V and right-click copy/paste,
  multiple sessions, and a plain disclosure that a native shell runs with the
  user's own OS permissions and is not limited to the workspace. It is separate
  from build Output, structured Tests and the Debug console. The agent never
  types into it.
- **Structured tests** (`TestsPanel.tsx`) via `project.test`: discover, run
  all / failed / selected, pass/fail/skip with duration, message and stack
  trace, and click-to-source. .NET uses a TRX logger; Python uses a structured
  unittest runner. The toolbar **Test** button keeps the reviewed,
  approval-bound validation streamed to Output; the dock provides the structured
  experience — both are real, neither is a mock.
- **Project system** (`ProjectPanel.tsx`): reads solutions (`.sln`/`.slnx`),
  projects (SDK, TFMs, output type, references, packages, test/web markers,
  launch profiles), `global.json` and the detected SDK; New Project templates
  (console / webapi / classlib / xunit / mstest / nunit / sln), add-existing,
  set startup project, Build/Rebuild/Clean/Restore, and a run configuration
  (startup project, configuration, arguments, working directory, launch profile,
  interpreter, safe environment overrides that reject secret-looking names).
- **Web** (`WebPanel.tsx`): an ASP.NET launch surface plus a small request
  inspector limited to the running program's own announced localhost origin, with
  no global certificate-validation disable, and the isolated `LocalPreview`.

## Other pages

- **Chat** is conversation-first: the conversation fills the width and history is
  an on-demand panel (docked on wide windows, an overlay with a scrim on narrow),
  reached from a persistent History control, with a header new-chat control.
- **Mail** reads as two panes (folders + list); the thread/detail pane appears
  only on selection (no compulsory third pane), and composing spans the reading
  area full-width while folders stay navigable.
- **Agent** and **Research** keep their task/result composition; **Home** was
  rebuilt around open work; Calendar/Tasks/Contacts/Settings/Projects/Knowledge/
  Memory retain the browsable composition from the prior redesign. All M3/M4
  behaviour and data semantics are preserved.

## Providers and versions

| Capability | Provider | Version | Licence |
| --- | --- | --- | --- |
| C# intelligence | OmniSharp-Roslyn (LSP) | 1.39.15 | MIT |
| .NET debugger | netcoredbg (DAP) | 3.2.0-1092 | MIT |
| Python intelligence | python-lsp-server | 1.15.0 | MIT |
| Python debugger | debugpy | 1.8.21 | MIT |
| Terminals | pywinpty (ConPTY) | 3.0.5 | MIT |
| .NET SDK | user's installed SDK (detected, never installed/upgraded) | 10.0.400 | — |

Provenance, SHA-256 digests and roles are in `desktop/THIRD_PARTY.md`. Tooling is
provisioned into the ignored `.toolchains/studio/` and the repo virtual
environment; nothing is installed system-wide.

## Acceptance demonstrated through the real UI (isolated profiles, temp projects)

Evidence in `artifacts/ui-review/redesign/` (ignored): `wip-shell`, `wip-studio`,
`wip-csharp`, `wip-pages`. Automated as opt-in specs under `desktop/tests/visual`.

- **A — C# multi-project solution**: scaffolded a `.slnx` with classlib +
  console + xUnit and project references through the project system; the solution
  view shows projects, TFMs, references and the startup project. (`wip-csharp`)
- **B — C# code intelligence**: OmniSharp reaches ready on the solution; the
  tooling suite proves completion, hover, cross-file definition, references,
  diagnostics (CS0029 appears then clears) and rename edits across files on
  unsaved buffers (`tests/test_studio_tooling.py::LanguageServerTests`).
- **C — build, fail, fix**: built the solution, ran the structured tests (pass),
  introduced a real failure (assert message with expected/actual, stack trace and
  a click-to-source link), then fixed and re-ran only the failed test.
  (`wip-csharp`)
- **D — real debugger**: a debugpy session through the UI — breakpoint set in the
  gutter, launch, hit, locals (`name = 'OLIVE'`), call stack, step, continue,
  clean stop (`wip-studio`); netcoredbg equivalently in
  `DotnetDebuggerTests` (verified breakpoint, locals total 3, evaluate, step,
  stale-generation rejection, continue → terminated).
- **E — interactive terminal**: a native PowerShell session receiving typed
  input and echoing output through ConPTY (`wip-studio`);
  `TerminalTests` covers input, resize and cleanup.
- **F — ASP.NET**: request inspector limited to the owned origin
  (`WebInspectorTests`); launch state + `LocalPreview` + `WebPanel` in the UI.
- **G — Python**: open a temp project, run, structured tests, and a real debug
  session (`wip-studio`).
- **H — state/conflict**: unsaved buffers survive navigation; an external disk
  edit is detected and reconciled without silent loss (`studio.spec.ts`,
  `m2-studio.spec.ts`).
- **I — offline**: every demo above ran with Ollama unavailable
  (`OLIVE_OLLAMA_HOST=http://127.0.0.1:1`); manual edit, completion, build, test
  and debug all work without any model.

Visual Studio was never opened; no debugger values or test outcomes were injected
— every result above is produced by the real tooling.

## Security and toolchain trust (preserved)

Context isolation, renderer sandbox, the narrow preload, validated IPC, the one
authoritative Python runtime, profile locking, permission/approval binding, and
preview/mail isolation are all unchanged. New language servers, debug adapters
and the terminal run as owned child processes of the Python runtime behind the
tool registry, permission engine and approved-workspace checks; the renderer
reaches them only through validated bridge methods, never a raw process handle.
Build/restore/test and package changes follow existing policies (project-local
`DOTNET_CLI_HOME`, filtered safe environment, secret-name rejection). The native
terminal is disclosed as running with the user's real OS permissions. The
redesign authorises no real email, account access or desktop actions.

## Tests and quality gates

- Python: full suite **744 pass**; Studio tooling suite **11 pass** (real
  OmniSharp, netcoredbg, ConPTY, debugpy, pylsp, dotnet).
- Frontend: unit **25 pass**; typecheck and ESLint clean; production build clean.
- Electron e2e: **36/37 pass**; the one miss is a load-induced 120 s timeout in
  `studio.spec.ts` that passes in isolation (7.5 s). Specs were updated to the
  workbench navigation (new `tests/e2e/shell.ts` helper) and the Studio dock
  model.
- New/changed coverage: workbench Core hand-off and tab lifecycle
  (`m2-core.spec.ts`), on-demand history (`m2-chat`, `responsive`), the dock and
  Workspace-tools sheet (`m2-closeout`, `m2-studio-git`), plus the tooling and
  acceptance probes above.

## Findings worth recording

- Under the renderer sandbox, a lazily loaded chunk that registers its own
  `window.olive.subscribe` stops receiving events after the first one. The
  tooling store therefore does not self-subscribe; the single App subscription
  forwards every event to it, and the store module is pinned to one chunk
  (`vite.config.ts` manualChunks) so App and the lazy Studio chunk share one
  instance.
- Blocking `subprocess.run` probes (`module_available`) and repeated
  `dotnet --list-*` calls were freezing the asyncio loop while a language server
  was initialising, leaving it stuck in "starting". Both are cached now; servers
  reach ready in about a second.

## Limitations

- netcoredbg's `internalConsole` streams debuggee stdout via output events but
  provides no stdin; the debug console is therefore read-of-output plus
  evaluate, not an interactive program-stdin channel. The native Terminal is the
  path for interactive program input.
- The pre-existing repository object store reported some missing blobs in old
  history after a background `git gc` repack failed mid-session; auto-gc is
  disabled (`gc.auto=0`) and all work from this brief is intact (recent commits
  and the working tree verify clean). A source backup is retained outside the
  repo.
- The full 74-screen brief-2 capture harness (`redesign-capture.spec.ts`) is
  still written against the old spine; the after-evidence for this brief is the
  four workbench capture specs listed above rather than a rewrite of that harness.
