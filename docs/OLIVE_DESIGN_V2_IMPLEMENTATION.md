# OLIVE Design System V2 — production implementation report

**Branch:** `feature/olive-design-v2` · **Scope:** desktop renderer (Electron
+ React + TypeScript). **Specification:**
[`design/OLIVE_DESIGN_SYSTEM_V2.md`](design/OLIVE_DESIGN_SYSTEM_V2.md),
[`design/OLIVE_STUDIO_V2.md`](design/OLIVE_STUDIO_V2.md) and their artifacts.

This milestone implements the approved V2 design in the real desktop
application. It is a frontend and product-shell change only:

- No Python module, backend contract, IPC channel, preload bridge, Electron
  main-process file, persistence format or permission rule was changed.
  (Apart from this report and the two V2 status lines,
  `git diff --name-status 21c96ea HEAD` lists only `desktop/src/**` and
  `desktop/tests/**`.)
- Nothing a mockup showed as example content (greenhouse-controller, Gaming
  PC, test counts, branches, diagnostics, timings) is hard-coded. Every value
  shown comes from runtime state.
- Artifact-only controls (scenario pickers, window-size pickers, the A/B/C/D
  overlay) are not part of the product.
- C9 Mobile and C10 were not touched.

---

## 1. Areas implemented

| Area | Where | Summary |
| --- | --- | --- |
| Tokens | `design/tokens.css` | V2 semantic tokens (`--bg-base/panel/surface/elevated/raised`, `--border-*`, `--text-*`, `--accent-blue/cyan/green`, `--status-*`, syntax, radii, spacing, control heights, motion, mono stack) with every earlier name kept as an alias. Muted contrast fix (`#8093aa`, light `#5f6f85`), blue-fill primary buttons with white text, 28 px controls, flat 7 px status dots, notices, switches, empty states, progress line. |
| Page system | `design/workspace.css` | The shared `WorkspacePage` system (used by ~25 workspaces) restyled to V2: 52 px header, hairlines, radii 6/8/12, 34 px rows, V2 segmented, pills, notices, flat empty states. |
| Shell | `app/TitleBar.tsx`, `app/Navigation.tsx`, `app/App.tsx` | 34 px title bar; 216 px grouped navigation with olive active indicator and badges; 48 px rail and overlay by width/space. |
| Palette | `app/commands.ts`, `app/CommandPalette.tsx` | Provider registry (no static list) with prefix modes `>` `:` `@` `#`; keyboard-first. |
| Core | `components/olive-core/*`, `components/RailCore.tsx` | Compact Core: olive at rest, cyan only while real work runs, amber while waiting for approval. |
| Home | `features/Home.tsx`, `features/home/homeModel.ts` | Ask → Needs attention → OLIVE is working on → Continue, with a 340 px Today rail. |
| Chat | `features/Chat.tsx`, `features/chat/RemoteTarget.tsx`, `components/Markdown.tsx` | One-row header, pickers in the composer, per-turn attribution, code-block Copy, partial-answer label, vision warning, V2 notices. |
| Studio | `features/Studio.tsx`, `features/studio/*` | Full V2 IDE layout (below). |
| Remote Studio | `features/studio/RemoteStudio.tsx` | The same IDE frame, bounded to Connect C8 operations. |
| GO | `features/go/*` | V2 refinements around the unchanged native WebContentsView. |
| Devices / Files | `features/devices/*` | Header facts, trust statement, capability table, danger zone; Inbox state vocabulary. |
| Tasks / Calendar / Reminders | `features/personal/*` | Inline add and keyboard model; week time grid with mini-month rail; one Reminders list. |
| Settings / Models | `features/settings/*` | Grouped rail, V2 rows and switches, unsaved-changes bar; preset status table. |
| Dialogs | `components/Sheet.tsx` | Centred 440 px V2 dialog for approvals and confirmations; drawer for longer tools. |

## 2. Design system

**Colour.** Near-black navy environment (`--bg-base #0b0f16`, panel
`#0f141b`, surface `#11171f`); blue for interaction (`--accent-blue`, fill
`#2f74d0`); cyan for computation (streaming caret, running jobs, context sent
to a model, compact Core while working); olive green for identity (mark,
active-space indicator, OLIVE author mark); amber for Ask/attention; red for
errors and destructive actions. Status is never colour alone: every state has
an icon or a word (tests assert spoken totals and descriptions).

**Typography.** Platform-native faces; `workspace.title` 17, `page.title` 18,
`section` 13/650, body 13, compact 12.5, metadata 12, uppercase eyebrows 11.
Mono stack adds JetBrains Mono, Fira Code and DejaVu Sans Mono so Linux gets a
real code face; Monaco keeps the person's `editor_font` first.

**Spacing and surfaces.** One scale (2 4 6 8 12 16 20 24 32 48); controls
28/24/32; rows 34 (lists), 30 (navigation), 22 (Studio); radii 3/4/6/8/12, the
16 px radius is retired; shadows only on overlays.

**Components.** Buttons (default, primary, quiet, danger, compact, prominent),
icon buttons, fields, segmented, permission segmented (Off · Ask · Allow),
switches (`role="switch"`), pills, count badges, notices, empty states,
dialogs, toasts, menus (`components/MenuButton.tsx`), palette rows.

## 3. Desktop shell

- **Title bar (34 px):** olive mark + wordmark (Home); the space name, which
  becomes a space-switcher menu only when navigation is hidden (no two
  competing selectors); a context crumb (conversation title); the command
  centre ("Find anything", `Ctrl+Shift+P`); a slot for workspace controls
  (Studio); activity with the compact Core; model status (preset + real
  readiness, remote device when Chat runs remotely); Connect status (off /
  paired / online counted separately); notifications count (approvals and
  delivered reminders) with a spoken total.
- **Navigation (216 px):** grouped Work / Build / Knowledge / Personal /
  System, every existing space kept (Agent, Desktop Control, Projects,
  Knowledge, Memory, Mail, Connections included), Settings and Collapse at the
  bottom, badges for due reminders and Connect Ask requests.
- **Responsive (V2 §15):** ≥1280 expanded (user may collapse), 1100–1279
  48 px rail, <1100 overlay; Studio: rail ≥1600, hidden below (reachable from
  the title bar, the olive mark and the palette).
- **Window controls** stay with the operating system frame (see §11).

## 4. Studio V2

| Surface | Implementation |
| --- | --- |
| Title-bar controls | Local/Remote segmented, workspace switcher, run configuration (Python program + interpreter name; .NET startup project + Debug/Release), Build (.NET), Run, Debug, Test, **Stop only while something can stop**, OLIVE toggle. Icon-only below 1440 px with the same accessible names. |
| Activity bar | Explorer, Search, Source Control (changed-file badge), Run and Debug (paused badge), Testing (failed badge), Studio settings. Roving tabindex, `role="toolbar"`. |
| Explorer | Open editors (dirty dots), the approved folder tree with Git letters, diagnostic counts and dirty dots (also spoken via `aria-description`), New file / Refresh / Collapse folders, the Solution/Python project view, and an Outline from `documentSymbol`. |
| Search | Text (`studio.search`: case-insensitive, first 200 matches, stated limits) and Symbols (`workspaceSymbol`), results grouped by file with highlighted matches. |
| Source Control | Branch and branches, commit message (Ctrl+Enter), Review commit, staged and working changes grouped from porcelain status, per-file Stage and Stage all (approval dialog), read-only per-file diff, recent commits. Status is read automatically only for folders approved as Git repository roots. |
| Run and Debug | Launch configuration, Start debugging, Variables, Watch, Call stack, Breakpoints (from the adapter), exception filters, floating debug toolbar (Continue/Pause, Step over/into/out, Stop — no Restart). |
| Testing | The existing structured runner (run all / failed / selected, discover, durations, messages, stack traces). |
| Editor | Unchanged Monaco with tabs (dirty dot, close), breadcrumbs (path › symbols), a code-intelligence-stopped notice, an Ask OLIVE selection affordance, OLIVE Night syntax theme from CSS tokens, minimap only ≥1600 px. |
| Panel | Problems (grouped by file, severity icon and word, `source(code)`, `[Ln, Col]`, click to navigate), Output (channel select + job header from the job record: state, counts, elapsed, exit code, Show in Problems, Rebuild), Terminal (native PTY, unchanged), Debug console; Preview and References when they exist. Collapsible (`Ctrl+J`), resizable (mouse and keyboard), maximisable, keyboard tablist, capped at 40% of the column. |
| Status bar | Local/remote, branch (`*` when dirty), problems (spoken counts), debug state, running job, cursor/selection, indentation, UTF-8, EOL, language, runtime **name** (never a path), code intelligence (`pylsp`, `OmniSharp`), save state. |
| OLIVE sidebar | Toggleable (`Ctrl+Alt+B`), overlays instead of docking when the editor would drop below 560 px, context chips (file, selection, problems, failing test, uncommitted changes — only chips that are on are sent), quick requests, the Studio thread with attribution, Stop, New thread. It cannot save, run, stage, commit or change permissions. |
| Palette | Studio registers File, Run, Build (.NET), Test, Git, Terminal, Go to, Code (rename, references, format, quick fix — only when a language server is ready), Search, View and OLIVE commands; `Ctrl+P` files, `:` line, `@` file symbols, `#` workspace symbols. |
| Keyboard | Ctrl+S, Ctrl+Shift+S, Ctrl+Shift+B, Ctrl+F5, F5/Shift+F5, F9, F10, F11, Ctrl+B, Ctrl+J, Ctrl+Alt+B, Ctrl+Shift+E/F/G/D/M, Ctrl+\`, Ctrl+Shift+\`, Ctrl+Alt+N, Ctrl+Alt+I, Ctrl+P, Ctrl+T. Keys typed in the native terminal belong to the shell (only the terminal toggles are intercepted). |

### Studio capability matrix

| Capability | Local Studio | Remote Studio (C8) |
| --- | --- | --- |
| Shared workspaces, tree, read | ✓ | ✓ (tree, read) |
| Edit and save | ✓ hash-checked | ✓ revision-checked; "Waiting for … to approve save" while Ask |
| Build / test / run | ✓ structured jobs; run in the native PTY | ✓ as remote jobs (non-interactive output, Output · Remote) |
| Run status / cancel | ✓ | ✓ |
| Interactive stdin, terminal, PTY | ✓ | ✗ disabled |
| Debugger (debugpy, netcoredbg) | ✓ | ✗ disabled |
| Code intelligence (pylsp, OmniSharp) | ✓ | ✗ |
| Workspace search | ✓ | ✗ disabled |
| Source control | ✓ (status, diff, stage, commit, log, branches — writes approved) | ✗ disabled |
| Packages, reviewed commands, new project, external IDE | ✓ | ✗ not offered |
| OLIVE assistant | ✓ | ✗ not offered |

`studioModel.ts` holds the matrix (`REMOTE_CAPABILITIES` is exactly tree,
read, save, build, test, run, cancel) and unit tests assert it.

## 5. Other workspaces

- **Home:** Needs attention lists approvals, delivered reminders (Snooze
  10 min / Dismiss) and a pending chat action; OLIVE is working on lists
  `runtime.activity` items; Continue lists real recent chats and workspaces;
  the Today rail shows the next event with a countdown, the agenda, tasks due
  (checkable through `tasks.complete`) and paired devices. First-run checklist
  and AI-offline notice come from real Ollama and preset state. No telemetry,
  statistics or recommendations.
- **Chat:** attribution from the provider recorded on each message ("OLIVE
  FAST · This device"; remote answers keep "Answered by <device> · OLIVE MAX");
  the stopped answer keeps "Incomplete response" with a *Stopped · partial
  answer kept* pill; no hidden reasoning is shown; Research & evidence, drop,
  attachments, branches and regenerate are unchanged.
- **GO:** unchanged native WebContentsView and isolation; 36 px tab strip,
  `r.lg` address field, olive-marked *Ask OLIVE*, no placeholder tiles.
- **Devices:** Connection · Trust · Encryption facts; "Pairing proves this is
  … It grants no access."; Off · Ask · Allow in that order with icon + word on
  the selected state; unsupported capabilities in one *Unavailable* line;
  *Revoke pairing* in a separated danger group with the existing confirmation.
- **Files (Inbox):** state pill per backend state, SHA-256 verified wording,
  inert-by-default notice; Save, Cancel, Dismiss unchanged; no auto-open.
- **Tasks:** inline add, N / ↑↓ / Space / Enter / Del, hints footer, 34 px rows.
- **Calendar:** Week default (remembered), mini-month rail, calendar toggles,
  one-row toolbar, time grid with all-day row and now-line, Month and Agenda.
- **Reminders:** Due now (Snooze, Dismiss, Mark task done) · Upcoming ·
  History, footnote keeps the local-delivery truth; C5 semantics unchanged.
- **Settings:** grouped rail (General, Appearance · AI · Workspaces · Connect
  & accounts · Privacy & Security · Data), rows with switches, unsaved-changes
  bar with Revert / Save settings; Models preset table with real status.
- **Preserved without redesign beyond the shared V2 layer:** Agent, Desktop
  Control (focus guard, takeover, Stop Control and emergency shortcut
  unchanged), Projects, Knowledge, Memory, Mail, Connections, Research.

## 6. A/B/C/D outcomes

| Item | Class | Outcome |
| --- | --- | --- |
| Tokens, radii, spacing, type, components | A | Implemented |
| Title bar content, space switcher, command centre, status cluster | B | Implemented |
| Window controls inside the title bar | C | **Not implemented** — native frame kept (§11) |
| Navigation 216/48, grouping, badges | A | Implemented |
| Route-aware Studio collapse | B | Implemented |
| Home composition, app grid removed | B | Implemented |
| Chat header, pickers, attribution | A | Implemented |
| Chat code-block Copy, vision warning | B | Implemented |
| Open code block in Studio | D | Not shown |
| Core cyan/amber palette | B | Implemented |
| GO tab strip, favourites guidance, address field | A/B | Implemented |
| Devices facts, trust statement, capability table, unavailable line | A | Implemented |
| Devices per-capability "last used" | C | Not implemented (no timestamp per capability is exposed) |
| Files Inbox table | B | Implemented as rows per device (the list lives in each device's detail) |
| Files resume | D | Not shown |
| Tasks density, groups / inline add, keyboard | A / B | Implemented |
| Calendar week styling, now-line, toolbar / mini-month, toggles | A / B | Implemented |
| Reminders grouped list | A | Implemented |
| OS notifications while closed | D | Not shown |
| Settings rows, switches, grouped nav / unsaved bar | A / B | Implemented |
| Settings About (version/licence view) | C | Not implemented |
| Settings Notifications, Density | D | Not shown |
| Studio activity bar, sidebar views, panel, status bar, palette registry | A/B | Implemented |
| Studio Open editors, Outline, breadcrumbs, Git decorations | B | Implemented |
| Studio side-by-side HEAD diff, search options (case/word/regex/glob) | C | Not implemented (read-only unified diff and plain search are shown truthfully) |
| Model edit proposals routed into EditPreview | C | Not implemented (existing permission review remains the path) |
| Split editor, marketplace, replace in files, unstage/discard/stash/push/pull, debug a single test, inline values, restart debug, remote code intelligence/debug/Git/terminal | D | Not shown |

## 7. Design parity

| Area | Verdict | Notes |
| --- | --- | --- |
| Tokens and components | MATCHED | |
| Title bar | MINOR IMPLEMENTATION ADJUSTMENT | Window controls stay in the OS frame; the crumb is filled for Chat (and Studio via its own controls). |
| Navigation | MATCHED | |
| Home | MATCHED | Composer offers the real preset; mode and execution pickers stay in Chat. |
| Chat | MATCHED | Per-turn timing ("8.4 s") is not shown: it is not recorded. |
| Core | MATCHED | |
| Studio layout, views, panel, status bar | MATCHED | |
| Studio Explorer/panel names | MINOR IMPLEMENTATION ADJUSTMENT | Panel tabs are a proper tablist named Problems/Output/Terminal/Debug console; e2e specs use a `showPanel` helper. The sidebar keeps its pre-V2 150 px minimum. |
| Studio assistant | MATCHED | Model/device shown read-only; choose them in Chat. |
| Remote Studio | MATCHED | Remote operations stay inside the remote frame so its controls remain scoped to the C8 surface. |
| GO | MATCHED | |
| Devices | MINOR IMPLEMENTATION ADJUSTMENT | Tabs keep their Connect contract names (Status, Permissions, Activity) instead of Capabilities/Activity/Details. |
| Files | MINOR IMPLEMENTATION ADJUSTMENT | Rows per device rather than one cross-device table (the Inbox data is per device). |
| Tasks, Calendar, Reminders | MATCHED | Calendar keeps a *Go to date* field in the rail (existing capability). |
| Settings | MATCHED | About is C and not implemented. |
| Dialogs, toasts, empty/loading/error states | MATCHED | |

## 8. Responsive behaviour

Measured on the real app (CachyOS, Electron, isolated seeded profile, Ollama
unreachable) for Home, Chat, GO, Agent, Studio (with a file open), Desktop
Control, Projects, Knowledge, Memory, Mail, Calendar, Tasks, Reminders,
Devices and Settings at **1920×1080, 1440×900 and 1366×768**: no page scrolls
sideways, no button, tab, heading or status item extends outside the window.

| Width | Global navigation | Studio |
| --- | --- | --- |
| ≥1600 | expanded 216 (user choice) | 48 px rail; sidebar 280; panel 280; minimap on |
| 1440–1599 | expanded | nav hidden; sidebar 256; run labels shown |
| 1280–1439 | expanded | run controls icon-only (same names) |
| 1100–1279 | 48 px rail | as above |
| <1180 (Studio) | — | primary sidebar overlays the editor |
| <1100 | overlay from the title bar | as above |

The OLIVE sidebar overlays whenever docking would leave the editor below
560 px. The bottom panel is capped at 40% of the editor column.

## 9. Accessibility

- Contrast: V2 muted values fix the two failing pairs (muted on raised,
  light muted on white).
- Focus: one visible 2 px ring; inset 1 px rings in dense lists and trees.
- Keyboard: roving tabindex (activity bar, tree, panel tabs), palette
  (↑/↓/Enter/Esc), Tasks keys, Studio shortcuts, resizers operable with arrow
  keys, menus with arrows/Escape.
- Names: every icon button is named; palette rows are named by the command
  only; Explorer decorations, counts and badges have spoken equivalents
  (`aria-description`, spoken totals, `aria-hidden` counts).
- Status is never colour alone (icons + words for tests, diagnostics,
  permissions, transfers, devices, Connect, model status).
- Reduced motion: the app preference and the OS setting stop every new
  animation (palette, dialog rise, caret, progress line, spinners, Core).
- Disabled controls that cannot act are hidden (Stop) or state the reason
  (remote-disabled views).

## 10. Regression results

All runs on 2026-09-23 on the CachyOS development machine (Linux, Wayland),
against the final branch head. Electron's bundled Node was used because the
machine has no system Node.

| Check | Command | Result |
| --- | --- | --- |
| Python compilation | `python -m compileall -q -x '(^\|/)\.venv/' .` | OK (the unfiltered command stops on a third-party PySide6 template inside `.venv`, unrelated to OLIVE) |
| Python tests | `python -m unittest discover -s tests -v` | 1094 run, OK, 11 skipped — identical to the pre-V2 baseline; no Python file changed |
| Connect portable suite | Connect C1–C8 unit/integration tests | 240 OK |
| Typecheck | `tsc --noEmit` | 0 errors |
| Lint | `eslint src electron` | 0 problems |
| Frontend unit tests | `vitest run` | 18 files, 96 tests passed (4 new V2 files) |
| Production build | `vite build` + `scripts/build-electron.mjs` | OK |
| Electron end-to-end | `playwright test` (68 tests) | 34 passed, 14 skipped, 20 failed — see below |

**Electron end-to-end failures.** Every failing spec was also run against the
pre-V2 build (`418cbf9`, same machine, same command) to separate V2 regressions
from environment limits.

| Cause (same failure before V2) | Specs |
| --- | --- |
| Spec hard-codes the Windows interpreter `.venv/Scripts/python.exe` or PowerShell | clarity › closing OLIVE leaves no language server, m1-review, m2-backup, m2-chat, m2-closeout, m2-handoffs, m2-preview, m2-research, m2-review, olive-core, responsive (11) |
| No .NET SDK on this machine | clarity acceptance journey, csharp-project, interactive-run (C#), winforms-designer (4) |
| No Java on this machine | java-project (1) |
| Desktop Control is not available in the Linux build | m2-desktop, owned-launch, attach-diagnostics (3) |

- **Found and fixed by this comparison:** `m4-mail-smtp` (3 scenarios)
  passed before V2 and hung after it. V2's disabled-button style changes
  background, border and colour, which the base button transition animated;
  the Mail composer disables its overflow actions inside a closed `<details>`
  during review, and Chromium never settles transitions on unrendered content,
  so the evidence capture waited forever. Availability changes now switch
  instantly (`button:disabled, details:not([open]) button { transition: none }`,
  with a unit test). All 3 scenarios pass.
- **Intermittent:** `browser.spec` (OLIVE GO) failed once in the final full run
  at native find-in-page (`matches` stayed 0 for 5 s inside the isolated
  WebContentsView). It passed in the previous full run and 3 of 3 isolated
  reruns on the final build; V2 does not touch the WebContentsView or its IPC.
- No test was skipped, deleted, loosened or given a longer timeout to pass.
  The suite adaptations for V2 (palette navigation via `openFromHome`,
  `showPanel()` for Studio panel tabs, one extra 900 px step in `connect.spec`
  because the V2 rail keeps two panes at 1100 px) are listed in the commits
  and preserve every assertion.

**Manual acceptance.** Fifteen spaces (Home, Chat, OLIVE GO, Agent, Studio
with a Python workspace open, Desktop Control, Projects, Knowledge, Memory,
Mail, Calendar, Tasks, Reminders, Devices, Settings) were captured and
reviewed at 1920×1080, 1440×900 and 1366×768, plus a light-theme pass: no
horizontal overflow and no clipped controls; navigation switches between
expanded, rail and hidden as specified, and Studio hides navigation below
1600 px. Connections and Remote Studio were not in that capture matrix.
Remote Studio is covered end to end by `connect-studio.spec` (C8 sharing,
approval, remote editor conflicts, jobs, offline draft; passed), and Devices
by `connect.spec`, which checks for horizontal overflow at 1920, 1440, 1366,
1100 and 900 px. The Studio panel and assistant at small sizes are exercised
by the Studio e2e specs rather than by these captures.

## 11. Known limitations

- **Window controls** remain the operating system's frame (class C). Moving
  them into the title bar needs a frameless window and new window-control IPC;
  it was left out because it cannot be validated on Windows from this machine.
- **Settings › About** (class C) and the Devices per-capability **last used**
  column (class C) are not implemented.
- **Home composer** offers the preset only; research mode and execution are
  chosen in Chat.
- **Studio assistant** shows the model and execution target read-only.
- **Title-bar crumb** is filled for Chat only.
- **Chat per-turn timing** is not shown because the runtime does not record it.
- **This machine has no .NET SDK or Java**: C#/.NET and Java acceptance specs
  cannot run here, and several older specs are Windows-only (see §10). They
  need a Windows run before release.
