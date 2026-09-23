# OLIVE Studio V2 — design specification and implementation handoff

**Status:** design proposal, not implemented. Nothing in this document changes
backend contracts, the security model, IPC names or persistence.
**Interactive artifact:** [`olive-studio-v2-artifact.html`](olive-studio-v2-artifact.html)
(open it next to this file; it loads `v2-assets/olive-v2.css` and the
`v2-baseline/` captures).
**System-wide rules:** [`OLIVE_DESIGN_SYSTEM_V2.md`](OLIVE_DESIGN_SYSTEM_V2.md).
**Baseline evidence:** `v2-baseline/04…15-*.jpg`. These are captured from the real app on
`feature/olive-connect-c9` with an isolated temporary profile and the synthetic
`seed_visual_fixture.py` data. Absolute interpreter paths are redacted.

Every proposed element carries an implementation class. Treat the class as the contract:

| Class | Meaning |
| --- | --- |
| **A** | Visual only. The backend and frontend state already support it. |
| **B** | Frontend behaviour change using existing APIs/IPC. |
| **C** | Needs a small backend or IPC addition. |
| **D** | Future / not supported. Must not be presented as working. |

---

## 1. Why Studio needs the largest redesign

Studio already has serious capability: Monaco, pylsp and OmniSharp-Roslyn
language services, debugpy and netcoredbg over DAP, native PTY terminals with
multiple sessions, structured tests, Git, .NET build configurations, Remote
Studio (C8). The ergonomics do not match that capability. Measured on the
baseline captures:

| Finding (current) | Evidence |
| --- | --- |
| The editor viewport at 1440×900 is **978×754 px**. It starts at x=462 (232 px OLIVE navigation + 230 px Explorer) and y=118 (a 42 px row holding only *Local* / *Remote*, plus a 42 px toolbar). | `04-studio-editor.jpg` |
| At 1366×768 the toolbar wraps to two rows, the editor starts at y=154 and is **904×586 px**. | `06-studio-1366.jpg` |
| At 1100 px the toolbar wraps and *Ask OLIVE* drops to its own row; the status bar truncates. | `15-studio-1100.jpg` |
| Panel tabs (Terminal, Problems, Tests, Output, Git, Debug) live in the **status bar**, next to status text. Navigation and status are mixed. | all Studio captures |
| Git is **seven buttons** ("Working changes", "Staged changes", "Review staging selected file", …). You can't see what changed without clicking, and staging means opening the file first. | `10-git.jpg` |
| Debug Call Stack and Variables share the ~240 px bottom dock with the editor. | `11-debug.jpg` |
| The assistant shows **one** response, and the selection is sent without being shown (only a file chip is visible). | `14-assistant.jpg` |
| A disabled *Stop* uses a hollow square icon that reads as a checkbox. | all captures |
| The status bar shows the **absolute interpreter path**. | redacted in captures |
| Workspace text search exists but is buried in *Workspace actions → Find in files*. | `WorkspaceTools.tsx` |

What is already good and must survive: structured Tests (run all / failed /
selected, durations, messages, source links), the real PTY terminal with
interactive programs, edit previews for language-server edits, hash-checked
saves, the Review-before-Git-write flow, and Remote Studio's per-share permissions.

## 2. Principles

1. **The editor is the primary surface.** It gets the brightest background
   (`background.surface`) and never drops below **560 logical px** wide.
2. **VS Code information architecture, OLIVE visual identity.** A VS Code user
   should find Explorer, Search, Source Control, Run and Debug, Testing, the
   panel and the status bar where they expect them, with the same shortcuts.
   No Microsoft artwork, codicons, logos or colour theme is copied. Icons are
   lucide (already bundled). The theme is OLIVE Night (§17).
3. **Chrome is navigation. The status bar is status.** Panel tabs live in the
   panel. The status bar only reports.
4. **OLIVE augments, it doesn't take over.** The assistant is a secondary
   sidebar with explicit context. Answers are conversational. File changes
   are proposals that go through review, and saving stays explicit.
5. **Truthful capability.** Anything classed D appears only in the artifact's
   class overlay (dashed outline), never in shipped UI.

## 3. Layout and panel hierarchy

```
Studio window
├─ Title bar (34)                          shared OLIVE V2 title bar, Studio variant
├─ Body
│  ├─ OLIVE rail (48, optional)            collapsed global navigation
│  ├─ Activity bar (44)                    Studio views
│  ├─ Primary sidebar (240–280, resizable 200–480)
│  │   Explorer | Search | Source Control | Run and Debug | Testing
│  ├─ Editor column (flex, min 560)
│  │   ├─ Editor tabs (32)
│  │   ├─ Breadcrumbs (24)
│  │   ├─ Contextual notice (optional, 30)  remote, code-intelligence stopped, offline
│  │   ├─ Monaco editor (flex)  + minimap (≥1600 only) + overview ruler (12)
│  │   └─ Panel (200–280, max 40% of column)
│  │       Problems | Output | Terminal | Debug console | [Local preview] | [References]
│  └─ OLIVE secondary sidebar (320–380, optional)
└─ Status bar (22)
```

### Proportions per window size

| Region | 1920×1080 | 1440×900 | 1366×768 |
| --- | --- | --- | --- |
| Title bar | 34 | 34 | 34, run controls icon-only |
| OLIVE rail | 48 (collapsed nav) | hidden | hidden |
| Activity bar | 44 | 44 | 44 |
| Primary sidebar | 280 | 256 | 240 |
| OLIVE sidebar (when open) | 380 docked | 340 docked | 320 docked; overlay drawer if editor < 560 |
| Panel (when open) | 280 | 236 | 200 |
| Minimap | on | off | off |
| Editor width with sidebar open, OLIVE closed | 1548 | 1140 | 1082 |

Measured gains against the baseline: **+17% editor width and +4.5% height at
1440**, and **+178 px width and +70 px height at 1366** (the toolbar no longer wraps).

### Collapse order

1. The OLIVE rail hides below 1600 px wide. OLIVE spaces stay reachable through
   the title-bar space switcher, the olive mark and the palette.
2. Run-control labels become icon-only with tooltips below 1440 px.
3. The OLIVE sidebar becomes an overlay drawer when docking it would leave
   the editor below 560 px.
4. The primary sidebar becomes an overlay below 1180 px.
5. The panel is capped at 40% of the editor column height, can be maximised, and
   `Ctrl+J` toggles it.

Sizes and open/closed states persist per workspace, extending the existing
`panelLayout.ts` / `sessions.ts` (B).

## 4. Title bar (Studio variant)

Left to right:

| Element | Behaviour | Source | Class |
| --- | --- | --- | --- |
| Olive mark | Opens OLIVE navigation (all spaces) | layout | B |
| Space switcher "Studio ▾" | Menu of OLIVE spaces | `navigation/features.ts` | B |
| Workspace switcher | Existing *Workspaces* dialog; shows "· Gaming PC" in remote mode | existing selector | A |
| Local / Remote segmented | Existing RemoteStudio switch, relocated from its 42 px row | `RemoteStudio.tsx` | A |
| Command centre (260–420 wide) | Shows the workspace name; opens the palette (§10) | existing palette | B |
| Run configuration select | Python: program + interpreter; .NET: startup project + Debug/Release | `project.config_save` | A |
| Build (.NET only) | `project.build`; Rebuild / Clean / Restore in the overflow and palette | existing | A |
| Run | `studio.run` in the PTY terminal | existing | A |
| Debug | `dap.launch` (Python, .NET only) | existing | A |
| Test | Structured test run | existing | A |
| Stop | **Shown only while something can be stopped** (program, debug session, tests, reviewed command, job). Error-coloured, with a label | existing stop logic | A |
| Core + activity text | "Idle / Testing / Debugging / Running / Thinking / Needs approval" | `runtime.activity` | B |
| OLIVE toggle | Opens the secondary sidebar (`Ctrl+Alt+B`) | existing assistant toggle | A |
| Window controls | Inside the 34 px bar | Electron `titleBarOverlay` (Windows) / frameless (Linux) | C |

The existing accessible names **must be kept** on the relocated controls (see §22).

## 5. Activity bar

Items, top to bottom: **Explorer** (`files`), **Search**, **Source Control**
(badge: changed-file count), **Run and Debug** (badge "‖" while paused),
**Testing** (badge: failed count). At the bottom: **Studio settings** (opens
Settings › Studio). Active item: 2 px `accent.blue` left indicator and primary
text colour. Clicking the active item toggles the sidebar (`Ctrl+B`). It is a
roving-tabindex vertical toolbar (`role="toolbar"`, `aria-orientation="vertical"`).

In **remote mode**, Search, Source Control, Run and Debug and Testing are
disabled. The tooltip says "not available for remote workspaces" (Remote
Studio has no code intelligence, debugger, Git or terminal).

There is **no Extensions item**, because no marketplace exists. OLIVE is not an
activity item either: it is the secondary sidebar, so files and the assistant
can be visible together. Class: **B** (layout; every view uses existing APIs).

## 6. Primary sidebar views

Shared anatomy: a 34 px header (uppercase 11 px title plus up to three
icon actions), collapsible sections with 22 px headers (uppercase 11 px/700),
and 22 px rows.

### 6.1 Explorer

| Section | Content | Class |
| --- | --- | --- |
| Open editors | Open buffers; dirty dot; path in muted text; click to activate | B |
| Workspace root (name; "Gaming PC · name" when remote) | Existing tree: nested folders, chevrons, expand/collapse, selection with focus outline. Actions on hover: New file (A), Refresh (A), Collapse folders (B) | A |
| · Git decorations | Letter on the right (`M` `#e2c08d`, `U`/`A` success, `D` error), filename tinted the same; collapsed folders show a dot if something inside changed | B (`studio.git status`) |
| · Diagnostics | Count on the right, filename in error colour when errors exist | B (Problems store) |
| Solution (.NET) | Projects with a Startup pill, Tests flag | A (`ProjectPanel`) |
| Outline | Classes, functions, fields for the active file; click to reveal | B (`documentSymbol`) |

The symbol search box moves out of the Explorer into Search (Symbols mode).

### 6.2 Search

A **Text | Symbols** segmented control, a query field, a result summary, and
results grouped by file (file row with count, then match rows with the hit
highlighted and the line number on the right). Clicking opens the file at the line.

- **Current implementation:** `studio.search` (case-insensitive substring,
  ≤200 matches, UTF-8 only, skips binaries and files over 2 MB) behind *Workspace
  actions → Find in files*. Workspace symbols come from the Explorer symbol box.
- **Design recommendation:** the Search view above, on those two APIs (**B**).
- Match case / whole word / regex / include-exclude globs: **C** (backend only
  does plain case-insensitive matching). Replace in files: **D**.
- The summary line states the limits: "Plain text, case-insensitive, first 200 matches."

### 6.3 Source Control

```
SOURCE CONTROL                                  ⟳  ⋯
⎇ main ▾                                   (branch picker)
┌ Message (Ctrl+Enter to commit on main) ┐
└────────────────────────────────────────┘
[ ✓ Commit 1 staged file ]                 (primary, full width)
Stage and Commit ask for your approval before Git runs.
▾ STAGED CHANGES  1
    pyproject.toml                                   M
▾ CHANGES  3                                         +
    scheduler.py   src/greenhouse          ⇄  +      M
    zones.py       src/greenhouse          ⇄  +      M
    test_scheduler.py  tests               ⇄  +      U
▾ COMMITS
    Plan slots against the daily budget   a41c9e2  2 h
```

| Element | API | Class |
| --- | --- | --- |
| Lists of staged and working changes | `studio.git status` | B |
| Stage file / Stage all | `studio.git add` via the existing review/approval | A |
| Commit message and Commit | `studio.git commit` via review/approval | A |
| Open changes (read-only unified diff in an editor tab, `diff` colouring) | `studio.git diff` (working / staged) | B |
| Side-by-side diff against HEAD | needs HEAD file content | C |
| Branch picker; create; checkout | `branch_list`, `create_branch`, `checkout` | A |
| Commits | `studio.git log` | A |
| Unstage, Discard, Stash, Push, Pull, Sync, any hosted-Git integration | none | D |

The approval dialog shows the exact command (`git add src/greenhouse/scheduler.py`,
`git commit -m "…"`) and the workspace, and states that the model can't approve it.

### 6.4 Run and Debug

Not debugging: a launch-configuration field (`Python: main.py · debugpy`,
`Acme.Inventory.Cli · netcoredbg`), a **Start debugging** primary button, the hint
"Click the gutter or press F9…", and the Breakpoints section.

Paused:

| Section | Content | Class |
| --- | --- | --- |
| Variables | Scopes (Locals expanded, Globals collapsed), expandable values, name in `syn.param`, value coloured by type | A (DAP scopes/variables) |
| Watch | Expressions with results; add; remove | A |
| Call stack | Thread row with a "Paused on breakpoint" pill; frames with file and `line:col`; selecting a frame reloads variables | A |
| Breakpoints | File, line, condition text; remove on hover; diamond = conditional, hollow = unverified | B (list over `tooling.breakpoints`) |
| Exception filters | Checkboxes from the adapter's `exceptionFilters` | A |
| Enable/disable breakpoint, inline values, restart session, data breakpoints | — | D |

**Floating debug toolbar** (over the editor, top centre, draggable handle):
Continue/Pause (F5), Step Over (F10), Step Into (F11), Step Out (Shift+F11),
Stop (Shift+F5). There is deliberately no Restart. Editor: breakpoint dots in
the glyph margin (F9), an amber current-line band with an arrow marker, and
the line number in amber. The status bar shows "‖ Paused on breakpoint ·
scheduler.py:36" on an amber background (Studio's only filled status item
besides remote mode). **Debug console** is a panel tab (B: relocated).

### 6.5 Testing

A header with Run all, Run failed, Discover, and a failed-only filter (all A),
and a summary line "5 passed · 1 failed · 0 skipped · 0.84 s" (A).
Tree: file → class → test with state icon (circle-check success, circle-x
error, circle-slash skipped muted), a checkbox for *Run selected* (A), and
duration. Hover actions: run test, go to source (A), debug test (**D**).
Failed tests show their `message` and `stack_trace` inline under the row,
with a red left rule (A). While running, rows show a spinner and a 2 px
indeterminate line runs under the header, only while the job is actually running.

## 7. Editor group

- **Tabs (32):** icon (outline, language-tinted stroke), name, "(Working
  Tree)" suffix for diff tabs, close ×. A dirty dot replaces × until hover.
  The active tab uses `background.surface` with a 1 px `accent.blue` top rule.
  Overflow via `⋯`. Class A. Split editor: **D** (single editor host today),
  shown only in the class overlay.
- **Breadcrumbs (24):** path segments › symbols (class, function) from
  `documentSymbol` (B). Diff tabs show a "Read-only diff" pill.
- **Monaco options** (A unless noted): `glyphMargin: true` (as today);
  `minimap.enabled` only ≥ 1600 px (today always off); `renderLineHighlight:
  "all"`; `fontFamily` default changes from `"Consolas"` to the V2 mono stack
  (`"Cascadia Code", "Cascadia Mono", "JetBrains Mono", "Fira Code", Consolas,
  "DejaVu Sans Mono", monospace`) so Linux gets a real code face; `fontSize`
  13 / `lineHeight` 20; user settings `editor_size` and `editor_font` keep
  priority; `stickyScroll` optional (A); `bracketPairColorization` off (the
  palette is intentionally calm).
- **Decorations:** warning and error squiggles (`status.warning` / `status.error`),
  the overview ruler (12 px) with warning, error, breakpoint and selection marks, and
  the current-line band `editor.current`.
- **Hover card:** existing LSP hover plus diagnostics, with "Quick Fix… Ctrl+." (A).
- **Selection affordance:** a floating **Ask OLIVE (Ctrl+Alt+I)** pill appears
  above a multi-line selection (B, Monaco selection listener). It opens the
  OLIVE sidebar with the Selection chip on.

## 8. Panel

Tabs are uppercase 11 px, and the active tab has a 1 px blue underline. Counts are badges.
Right-side actions depend on the tab (terminal session select / new / kill,
output channel select), then Maximise and Close.

| Tab | Content | Class |
| --- | --- | --- |
| Problems | Grouped by file (collapsible), severity icon, message, `source(code)`, `[Ln, Col]`; click to jump | A (`useProblems`) |
| Output | Channel select (Tests, Build, Run, Remote…). A **job header** above the raw output: state icon, title ("Build succeeded"), pill (counts), facts (Target, Configuration, Started, Elapsed, Exit code), then *Show in Problems* / *Rebuild* | B (job record: `label`, `command`, `state`, `started_at`, `ended_at`, `exit_code`; MSBuild diagnostics already parsed into Problems) |
| Terminal | Native PTY xterm (unchanged), session list on the right (program sessions and shells), New (`Ctrl+Shift+``), Kill | A |
| Debug console | Evaluate in the selected frame; history | B (relocated) |
| Local preview | Only when a run exposes a local URL | A (`WebPanel`) |
| References | Only after Find All References | A |

**Result semantics:** success or failure comes from the exit code and structured
results, never from stderr alone. MSBuild warnings on stderr stay warnings.
Build output shows workspace-relative paths.

## 9. Status bar (22)

Left to right; every item is a button with an accessible name.

| Item | Example | Source | Class |
| --- | --- | --- | --- |
| Remote indicator | "Local" (quiet) or **"Gaming PC"** on `accent.blue.fill` (amber-brown when offline) | RemoteStudio state | B |
| Branch | `⎇ main*` (`*` = uncommitted changes) | `git status` / `branch_list` | B |
| Problems | `⊗ 0 ⚠ 2` → opens Problems | problem counts (exist today in the strip) | A |
| Debug state | "‖ Paused on breakpoint · scheduler.py:36" (amber fill) | `debugState` | A |
| Running program / tests | cyan text with icon | run and job state | A |
| Cursor | "Ln 36, Col 17 (6 lines selected)" | Monaco | B |
| Indentation | "Spaces: 4" | Monaco model options | B |
| Encoding | "UTF-8" (Studio opens UTF-8 text only, so this is always true) | backend decode rule | B |
| EOL | "LF" / "CRLF" (newline is preserved on save) | Monaco model | B |
| Language | "Python", "C#" | languageFor | A |
| Interpreter / SDK | "3.14.7 (.venv)", ".NET 9.0.100". **A name, never an absolute path** | `scan.tooling` | A |
| Code intelligence | "pylsp", "OmniSharp"; warning "pylsp stopped" → opens Problems/Output | `languageState` | A |
| Save state | "Saved" / "2 unsaved" / "Waiting for Gaming PC to approve save" | save status | A |

## 10. Command palette

It opens from the title-bar command centre, `Ctrl+Shift+P` (commands) or
`Ctrl+P` (files). It is a 620 px overlay under the title bar with an input,
grouped results, and a footer with prefix hints. It is keyboard-first: ↑/↓, Enter
and Esc, matching text highlighted, keybinding hints on the right.

| Prefix | Mode | Source | Class |
| --- | --- | --- | --- |
| *(none)* | Go to file | `studio.tree` | B |
| `>` | Commands | Studio command registry (below) + existing global palette | B |
| `#` | Workspace symbols | LSP `workspaceSymbol` | A |
| `@` | Symbols in file | LSP `documentSymbol` | B |
| `:` | Go to line | Monaco | A |

Commands. **Only these**, because each maps to an existing function:

| Command | Keys | Calls | Class |
| --- | --- | --- | --- |
| File: Save / Save All / Compare with Saved / New File… / New Project… / Open Workspace… / Close Workspace / Open in External IDE | Ctrl+S, Ctrl+K S, —, —, Ctrl+Alt+N | `studio.save`, save all, `studio.compare`, NewFile, NewProjectWizard, selector, close, `studio.open_ide` | A |
| Run: Run Project / Start Debugging / Stop / Toggle Breakpoint | Ctrl+F5, F5, Shift+F5, F9 | `studio.run`, `dap.launch`, stop, `dap.breakpoints` | A |
| Build: Build / Rebuild / Clean Solution, Restore Packages, Select Startup Project…, Manage Packages… | Ctrl+Shift+B | `project.build` variants, `project.config_save`, Packages | A |
| Test: Run All / Run Failed / Discover Tests, Review Test Commands… | — | `project.test`, `studio.validate` | A |
| Git: Refresh Status / Stage Current File / Commit Staged… / Create Branch… / Checkout Branch… / Show Recent Commits | — | `studio.git` | A |
| Terminal: New Terminal / Focus Terminal | Ctrl+Shift+`, Ctrl+` | `terminal.open`, focus | A / B |
| Go to Symbol in Workspace… / in File… / Go to Line… | Ctrl+T, Ctrl+Shift+O, Ctrl+G | LSP, Monaco | A / B |
| Rename Symbol / Find All References / Format Document / Quick Fix… / Restart Code Intelligence | F2, Shift+F12, Shift+Alt+F, Ctrl+. | LSP, `lsp.restart` | A |
| Search: Find in Files | Ctrl+Shift+F | `studio.search` | B |
| View: Toggle Primary Side Bar / Panel / OLIVE; Show Source Control / Run and Debug / Testing | Ctrl+B, Ctrl+J, Ctrl+Alt+B, Ctrl+Shift+G, Ctrl+Shift+D | layout | B |
| OLIVE: Ask About Selection / Explain Error / Review Changes | Ctrl+Alt+I | assistant submit, quick actions | A |
| OLIVE: Suggest Fix for Failing Test / Generate Tests for File | — | assistant prompt templates | B |
| Remote Studio: Open Shared Workspace… | — | `connect.studio_*` (C8) | A |

An empty result says "No matching commands. The palette only lists what Studio can do today."

## 11. OLIVE developer assistant

The OLIVE secondary sidebar (right, 320–380) replaces today's *Ask OLIVE* aside.

```
◖ OLIVE           [OLIVE MAX ▾] [💻 This device ▾]  ✎  ×
Context sent with your next message                    3 of 5
[✓ scheduler.py] [✓ Selection · lines 31–36] [ Problems · 2]
[✓ Failing test · 1] [ Uncommitted changes]
Explain · Find bug · Refactor · Generate tests · Explain error · Suggest fix · Review changes
──────────────────────────────────────────────────────────────
  (thread: user turns right, OLIVE turns with attribution)
  ◖ OLIVE  OLIVE MAX · This device · 6.8 s
  …answer…
  ┌ Proposed change · scheduler.py  +2 −0 ┐
  │ [Review changes] [Discard]             │
  │ Nothing changes until you review it.   │
  └────────────────────────────────────────┘
──────────────────────────────────────────────────────────────
[ Ask about scheduler.py…                    Ctrl+Enter  ↑ ]
```

**Context model (B).** Chips are toggles. A solid chip with a cyan tint means
"will be sent". A dashed chip means "not sent". Only chips that are on are
included, and nothing else is sent: no silent project map or other files. Today's
`submit(text, {workspace_id, path, selection})` already carries file and
selection. Problems, failing test and Git changes are assembled into the prompt
text exactly as today's *Explain error* and *Review changes* quick actions do
(`studio.diff` capped at 12,000 chars). "Project" context is not offered
(there is no bounded project-summary API, so it would be **C**).

**Quick actions.** *Explain error* and *Review changes* exist (A). *Explain,
Find bug, Refactor, Generate tests, Suggest fix* are prompt templates over the
same submit (B). Refactor, Generate tests and Suggest fix may produce a
**proposal**; the others are answer-only.

**Answer-only vs change flow.**
- Answer-only prompts stay chat-like: streaming text with a cyan caret, and Stop
  (`chat.cancel`, A). A stopped answer is kept and labelled "Stopped · partial
  answer kept".
- Changes are **never written by the model**. A proposal card leads to *Review
  changes*: a per-file diff dialog with an include checkbox per file. *Apply to
  buffer* edits the Monaco buffer only (the tab turns dirty). Saving stays
  `Ctrl+S` with the existing hash check. Routing model-proposed edits into the
  existing `EditPreview` (today used for language-server edits) instead of the
  generic approval sheet is **C**. Until then, the existing workspace-permission
  review remains the path.

**Attribution (B).** Every OLIVE turn shows `model · device · time`, for example
"OLIVE MAX · This device · 6.8 s" or "OLIVE MAX · Gaming PC", using the same
truthful rules as Chat (`RemoteAttribution`). The execution chip offers
*This device* or explicitly paired devices with Remote AI allowed. DEEP and
REIMAGINE show "Unavailable remotely" as Chat does today.

**Thread (B).** Show the conversation from `chat.messages` after the Studio
request marker, not only the last response (today: `responseAfter`). "New
thread" starts a fresh request marker.

**No workspace authority.** The assistant cannot run commands, stage, commit,
save or change permissions. Any tool the agent proposes goes through the
existing approval flow outside the model.

## 12. Build, run and test flows

- **Build (.NET):** the title-bar Build button (Ctrl+Shift+B) opens Output ›
  Build with the job header: *Build succeeded / failed*, a warnings/errors pill,
  Target, Configuration, Started, Elapsed, Exit code. Diagnostics go to Problems.
  The Explorer shows error tint and counts.
- **Run:** always in the terminal (existing *program* PTY session).
  `input()` and `Console.ReadLine()` behave exactly as in a shell. The program
  session appears in the terminal list; Stop appears in the title bar while it
  runs. Output cards never replace the terminal.
- **Test:** structured runner → Testing view plus Output › Tests job header.
  Run failed and Run selected are existing actions.
- **Review test commands** (`studio.validate`) stays in the overflow menu and palette.

## 13. Remote Studio mode (C8)

The same IDE in remote mode:
- Title: "greenhouse-controller · Gaming PC"; the status bar left item is on
  `accent.blue.fill`.
- Notice under the tabs: "Files live on Gaming PC. Build, test and run happen
  there. Code intelligence, debugging, Git and terminals are local-only." followed by
  permission pills from `share.permissions` (Read, Save, Build, Test, Run →
  Allow / Ask / Off).
- Save with *Ask* shows "Waiting for Gaming PC to approve save" in the status
  bar and the tab. It is never shown as saved until the host approves.
- Build, test and run output appears in Output › Remote with a job header
  (non-interactive output; remote runs have no PTY).
- Offline: an error notice ("Gaming PC is offline. Your edits stay in this
  buffer…"); the status-bar remote item turns amber-brown and reads "Gaming PC · offline".
- Remote code intelligence, debugging, Git and terminals: **D**.

## 14. States

| State | Presentation | Class |
| --- | --- | --- |
| No workspace | Editor area: "Studio" with the olive mark; Start (Open folder… Ctrl+K O, New project… Ctrl+Alt+N, Open a shared workspace on a paired device…) and Recent (title + kind + "approved folder" / "Shared by Gaming PC"); the note "Studio only opens folders you have approved." Explorer: "No folder is open" with Open folder / New project | A |
| Code intelligence stopped | Warning notice under the tabs with *Restart code intelligence* and *Show output*; the status item turns amber; Problems explains that language-server diagnostics are unavailable | A |
| Remote offline | See §13 | A |
| Permission required | The existing approval dialog shows the exact command | A |
| Running job | 2 px indeterminate line in the owning region only; Core in the title bar turns cyan | A / B |
| Unsaved | Dirty dots on tabs and in Open editors; status "N unsaved"; the existing close-workspace dialog | A |

## 15. Visual density

Rows: tree and lists 22, section headers 22, tabs 32, breadcrumbs 24, panel tabs
32, status bar 22. Controls: 24 (compact buttons in sidebars) and 28 (title-bar
selects and buttons). Type: 13 px code and tree, 12.5 px tabs and panel text, 12 px
status, 11 px uppercase headers. Studio is the densest surface in OLIVE by design.

## 16. Accessibility

- Every icon button has an accessible name equal to its tooltip text minus the shortcut.
- Activity bar, tab strip, panel tabs and tree use roving tabindex. Arrow keys move,
  Enter/Space activates, Home/End jump.
- Focus: an inset 1 px `border.active` ring on rows (no layout shift); the standard 2 px ring elsewhere.
- Status is never colour alone: test states have distinct icons; diagnostics
  have icons and words; the debug state has text.
- Targets: title-bar and sidebar-header controls are 24–28 px. Icon buttons
  inside rows and panel headers are 22 px with at least 2 px between them,
  which meets WCAG 2.2 AA 2.5.8 through its spacing exception (a 24 px circle
  centred on each target does not overlap its neighbour).
- Reduced motion: no caret blink, spinners become static icons, and panels open instantly.

## 17. OLIVE Night: Studio theme

Surfaces (dark): title bar, activity bar and status bar `#0b0f16`; sidebar
and panel `#0f141b`; editor and active tab `#11171f`; hover
`rgba(197,216,240,.06)`; selection `rgba(124,196,255,.22)`; current line
`rgba(197,216,240,.045)`.

Syntax palette, with contrast measured against the editor `#11171f`:

| Token | Colour | Contrast | Used for |
| --- | --- | --- | --- |
| text | `#d6deea` | 13.29:1 | default |
| comment | `#7486a0` (italic) | 4.85:1 | comments, fences |
| keyword | `#6cb6ff` | 8.38:1 | `def class import from in is not`, `using public var` |
| control | `#c8a2f0` | 8.47:1 | `if for while return raise try with break continue` |
| string | `#d9a47a` | 8.18:1 | strings, f-strings, Markdown code |
| number | `#b5cea8` | 10.60:1 | numbers |
| function | `#e2d59a` | 12.19:1 | function names and calls |
| type | `#5cc8b4` | 8.90:1 | classes, types, builtins |
| parameter / key | `#a8d8ff` | 11.95:1 | `self`, parameters, JSON keys, TOML keys |
| decorator | `#e0af68` | 9.00:1 | `@dataclass` |
| constant | `#7fc8f8` | 9.88:1 | `REST_DAYS`, `WEEK` |
| punctuation | `#8d9bb0` | 6.39:1 | operators and brackets |
| line number | `#6e7d93` / active `#c9d4e2` | 4.30:1 / 12.00:1 | gutter |

Green is kept out of syntax (numbers are sage, not identity green) so olive
green keeps meaning OLIVE and success. The light-theme equivalents are in
`v2-assets/olive-v2.css` (`.p[data-ptheme="light"]`). Implement as a Monaco
`defineTheme("olive-night", …)` that reads the same CSS tokens Monaco already
derives from (A). The artifact's *Syntax palette* section shows Python, C#, JSON and
Markdown samples.

## 18. Keyboard map

| Action | Keys | Class |
| --- | --- | --- |
| Command palette / Go to file / workspace symbol / file symbol / line | Ctrl+Shift+P / Ctrl+P / Ctrl+T / Ctrl+Shift+O / Ctrl+G | A / B / B / B / A |
| Save / Save all | Ctrl+S / Ctrl+K S | A |
| Close tab / next tab | Ctrl+W / Ctrl+Tab | B |
| Explorer / Search / Source Control / Run and Debug | Ctrl+Shift+E / F / G / D | B |
| Toggle sidebar / panel / OLIVE | Ctrl+B / Ctrl+J / Ctrl+Alt+B | B |
| Focus terminal / new terminal | Ctrl+` / Ctrl+Shift+` | B |
| Build / Run / Debug-continue / Stop | Ctrl+Shift+B / Ctrl+F5 / F5 / Shift+F5 | A / B / A / A |
| Step over / into / out / toggle breakpoint | F10 / F11 / Shift+F11 / F9 | A / A / A / B |
| Next / previous problem | F8 / Shift+F8 | B |
| Rename / references / definition / quick fix / format | F2 / Shift+F12 / F12 / Ctrl+. / Shift+Alt+F | A |
| Ask OLIVE about selection / send / commit | Ctrl+Alt+I / Ctrl+Enter / Ctrl+Enter | B / A / A |
| New project | Ctrl+Alt+N | A |

`Ctrl+Shift+I` is not bound (it opens Electron developer tools).

## 19. Component inventory

| Component | Contents / behaviour | Existing source | Class |
| --- | --- | --- | --- |
| Title bar | §4 | selector, RemoteStudio, run handlers | B |
| Window controls | inside title bar | Electron main process | C |
| Activity bar | §5 | layout | B |
| Explorer tree | §6.1 | `Explorer.tsx`, `studio.tree` | A |
| Open editors, decorations, outline | §6.1 | open files, git status, documentSymbol | B |
| Solution section | §6.1 | `ProjectPanel.tsx` | A |
| Search view | §6.2 | `studio.search`, workspaceSymbol | B |
| Source Control view | §6.3 | `GitPanel.tsx` operations | B |
| Diff tab | read-only unified diff | `studio.git diff` | B |
| Run and Debug view + toolbar | §6.4 | `DebugPanel.tsx`, `debugClient.ts` | B (+A toolbar) |
| Testing view | §6.5 | `TestsPanel.tsx` | B |
| Editor tabs, breadcrumbs, Monaco | §7 | `Studio.tsx` | A / B |
| Panel tabs | §8 | `DOCK_TABS` | B |
| Job header | §8 | job record | B |
| Terminal | §8 | `TerminalPanel.tsx` | A |
| Status bar | §9 | strip items + Monaco | B |
| Command palette | §10 | App palette + Studio registry | B |
| OLIVE sidebar | §11 | `Assistant.tsx` | B |
| Proposal review | §11 | `EditPreview.tsx` | C |
| Remote mode | §13 | `RemoteStudio.tsx` | B |
| Split editor, marketplace, replace-in-files, unstage/discard/push, debug test, inline values, restart debug | — | — | D |

## 20. Supported vs unsupported (verified in source)

**Supported today:** approved local workspaces, tree, open/edit/save with
hash-checked writes, compare with disk; Monaco with pylsp and
OmniSharp-Roslyn (completion, hover, signature help, definition, references,
rename with preview, document/workspace symbols, formatting, code actions,
diagnostics); .NET build/rebuild/clean/restore, startup project, Debug/Release;
run in native PTY with interactive input; multiple terminals; local web
preview; structured tests (discover, run all/failed/selected, durations,
messages, stack traces); debugpy and netcoredbg (breakpoints with conditions,
continue/pause/step, call stack, variables, watch, console, exception filters);
Git status/diff/add/commit/log/branch list/create/checkout with review; text
search (`studio.search`); OLIVE assistant with file + selection, Explain error,
Review changes; Remote Studio shared workspaces (tree, read, save, build, test,
run, cancel) gated per share.

**Not supported. Never show as working:** extension marketplace; split
editor; unstage/discard/stash/push/pull/hosted Git; side-by-side diff against
HEAD; regex/word/glob search and replace in files; enable/disable breakpoints,
inline values, restart debug, debug single test; code intelligence, debugging,
Git or terminals on remote workspaces; model-driven writes without review;
non-UTF-8 files.

## 21. Suggested implementation order

All work is inside `desktop/src/features/studio/` and `desktop/src/design/`,
with no backend change except the items marked C.

1. **Tokens and theme (A).** Add the V2 token aliases (see the Design System doc §4),
   the Monaco `olive-night` theme, the mono stack, and the muted contrast fix.
2. **Shell split (B).** Break `Studio.tsx` (1,646 lines) into `StudioShell`,
   `StudioTitleBar`, `ActivityBar`, `Sidebar` (views), `EditorGroup`,
   `StudioPanel`, `StatusBar`. The state stays where it is today. `panelLayout.ts`
   gains sidebar/panel/assistant sizes per workspace.
3. **Move existing panels (B).** Git → Source Control view, Debug inspection →
   Run and Debug view, Tests → Testing view, Debug console → panel tab, and panel tabs
   out of the status strip. Keep the accessible names (§22).
4. **New views on existing APIs (B).** Search view, Open editors, Outline,
   breadcrumbs, Git decorations, status-bar Monaco items, palette modes and the
   Studio command registry.
5. **Assistant (B).** Context chips, thread, prompt templates, attribution.
6. **C items**, each as its own change: window controls in the title bar; model
   edit proposals routed into `EditPreview`; side-by-side HEAD diff; search options.

## 22. Test compatibility (e2e accessible names)

The Playwright suite locates Studio by these names. Relocated controls must
keep them. Where a name changes meaning, update the spec in the same change:

`Source editor` (textbox) · `Run` · `Save` · `Test` · `Stop program` ·
`Show Output` / `Hide Output` (today the strip toggles: keep these names on the
panel tab buttons, or change `tests/e2e` deliberately) · `New terminal` ·
`New project` · `Create project` · `Workspace: <title>` (selector) ·
`Workspaces` (dialog) · `Close workspace` (dialog) · `Workspace tools` (the panel region) ·
`Output channel` (combobox) · `Refresh Git status` · `Recent commits` ·
`Review staging selected file` · `Review commit` · `Review new branch` ·
`Commit message` · `Branch name` · `Find in workspace` · `Search files` ·
`Add project to this solution` (dialog) · `Ask OLIVE` · treeitems by file name.

`Review staging selected file` becomes the per-row **Stage** action. Keep a
hidden-label alias or update `m2`/Studio specs in the same change.
