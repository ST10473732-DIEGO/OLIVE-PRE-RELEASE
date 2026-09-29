# OLIVE Agent / Workspace milestone

Branch: `feature/olive-agent-workspace` (from `000bea7`, the media-chat milestone).
Date: 29 September 2026. Status: implemented and tested; **not committed**.

This milestone extends the existing agent, Studio, Owner Mode and desktop-control
architecture. It does not add a second task engine, permission system, editor,
terminal or preview. Chat stays the entry point: an ordinary request that asks
for code work becomes one durable task; everything else keeps its existing route.

## 1. One task model

`olive/agent/agent_task.py` — `AgentTask` is the single task record for Chat,
Studio and the Agent page (schema 2; schema 1 records load unchanged, every new
field has a default).

States: `created, planning, ready, running, waiting_permission,
waiting_confirmation` (plus the historical `waiting_for_confirmation` the executor
uses), `waiting_user, paused, stopping, completed, failed, cancelled`.
Terminal states (`completed, failed, cancelled`) never transition again; resuming
is explicit new work from `paused`/`waiting_user`.

Persisted per task: id, chat id, user message id, workspace id, request, times,
state, current step, OLIVE-authored plan (step id, tool, expected observation),
factual timeline, bounded observations, effect receipts, changed files with
before/after SHA-256, commands with exit codes, validation evidence (parsed test
counts, diagnostics), preview status, owned run sessions, constraints, failure
category and resume state. No hidden reasoning is stored.

Public failure categories: workspace unavailable, file changed, build failed,
test failed, tool unavailable, application not found, window unavailable,
control changed, authorization required, task timed out, no progress, preview
failed, port unavailable, command cancelled, external outcome uncertain, model
unavailable, invalid proposal, unsaved editor changes.

## 2. Planner / executor boundary

`olive/agent/coding_task.py` — `CodingTaskRunner`, the bounded loop:

```
inspect → baseline checks → read relevant files → propose → apply → re-check
                                   ↑                                   │ failed
                                   └──────── bounded replan ◄──────────┘
```

* **OLIVE authors the plan.** Step order and tools are fixed by OLIVE
  (`_plan`). The model never chooses tools, commands, workspaces or permissions.
* **The model proposes edits only**, in `olive/agent/edit_plan.py`'s strict
  schema: `replace` (verbatim, unique `find`), `create` (new file), `rewrite`
  (a small file OLIVE read completely). Rejected: unknown fields/actions,
  absolute/`..`/`~`/drive paths, `.git`/`node_modules`/`bin`/`obj`/`.venv`,
  shell metacharacters in paths, edits to files not read in this task, creation
  over existing files (case-folded), non-unique replacements, authority-looking
  keys (`approved`, `permission`, `command`, `sudo`, …).
* **Every effect goes through the existing `ToolExecutor`** (`code.read_file`,
  `code.replace_exact`, `code.replace_range`, `code.create_file`,
  `workspace.run_validation`, `studio.run`, `studio.new_project`), so persistent
  Deny, Owner Mode grants, approvals, audit and per-task checkpoints apply.
* **Validation** uses only the workspace's detected standard commands
  (`BuildAndTestService`), never model command strings.
* **Model routing**: `ModelRouter` role `coding` (qwen3-coder:30b on this
  machine; falls back to `reasoning`). Chat's own preset, including UNCENSORED,
  never becomes the editing model; every model has the same (zero) authority.
  Residency is unchanged (`ModelResidencyService` via `OllamaService`).

Limits (`TaskLimits`): 2 replans after the first proposal, identical failure
fingerprint once ⇒ stop ("no progress"), 3 failed rounds, 2 schema-invalid
proposal attempts, 40 recorded effects, 20-minute runtime, 8 files / 30,000
characters of context per proposal. Large files are read as excerpts around
diagnostics.

Completion requires evidence: every detected check passes, or (no detected
checks) every written file's hash equals the intended result, plus a reachable
owned loopback preview when one was requested. A model saying "done" proves
nothing.

## 3. Chat routing

`olive/interaction/orchestrator.py`

* `project_request` (`olive/interaction/project_request.py`) recognises literal
  creation requests ("Create a small webpage … and show me it", "Create a minimal
  ASP.NET Core Web API … build it, run it and show me the result", "Create a
  Python project called X and run the tests"). "Write me a Python script" and
  similar remain answers in Chat.
* `fold_coding_steps` turns an interpreter's split plan (pathless
  `code.inspect`, repeated `code.modify`, unconditional `code.test`, a
  `code.run` for "run the tests") into one coding task carrying the literal
  request. Conditional programs (`when: tests_fail`) are kept.
* Workspace binding (`olive/interaction/workspace_reference.py`): an explicit
  Studio selection, a registered workspace the request names ("my BrokenCalc
  project"), or a bounded follow-up (an edit-shaped request within the last four
  user turns after this chat's own coding task, not naming another app/setting).
  Named/follow-up bindings become the conversation's selection so an older
  implicit selection cannot replace them.
* Corrections while a task runs ("Don't change the database", "Use SQLite
  instead") become task constraints, applied before the next proposal; named
  files/areas in "don't change X" are enforced deterministically.
* "Continue" resumes this chat's paused coding task. A stop/pause/continue
  interpretation with no task to control, whose text is not a short control
  phrase, is answered normally (fixes a pre-existing FAST misroute).
* `code.test` runs as a task (real counts); `code.run` of a web project starts
  the preview; remote targets still receive text answers only.

## 4. Permissions and Owner Mode

Reused unchanged in structure (`olive/authority/owner.py`, `owner_scope.py`).
Narrow additions, each deterministic over the literal request:

| Change | Why |
|---|---|
| `workspace.run_validation` budget 4, `studio.run` budget 2 per grant | A repair loop observes before and after each bounded round; a web edit may restart its own preview once |
| Code-write grant also grants detected validation in the same workspace (unless declined) | An edit is verified by the project's own detected checks |
| Explicit project request ⇒ creation grant (new folder only, name resolved exactly as the router does) | "Build me a website and show it" |
| `bind_created_workspace` | After an authorized `studio.new_project`, later effects are scoped to that new folder only; an existing folder is never adopted |
| Creation grants never inherit a previously selected workspace | Found live: ASP.NET creation after a website |
| `code_target` for bounded follow-ups | "Change the button text to Launch." after this chat's task |

Not changed: Deny precedence, 10-minute grant expiry, Stop epochs, remote
exclusion, no "allow everything" switch. `terminal.run` stays
NOT_SAFE_FOR_OWNER_AUTO. `olive/agent/command_policy.py` classifies terminal
text and only **adds** checks (`terminal.admin` for sudo/su/doas/pkexec,
including inside `$(…)`/backticks and `curl | sh`; `terminal.admin` +
`system.settings` for system package managers, `systemctl`, global installs,
`chmod` outside the workspace; `software.install` for project package installs).
Agent tasks have no shell tool.

## 5. Effect receipts and restart

`olive/agent/receipts.py`. Every effect is reserved before dispatch with what
OLIVE expects to observe (for writes: the exact resulting SHA-256), then settled
from observation. Classes: read, workspace_write, validation, process,
desktop_input, external. An identical completed effect is not repeated.

`AgentTaskRepository.recover_interrupted` (startup) never resumes. It reconciles
open reservations by re-observation only: intended hash present ⇒ completed; hash
unchanged ⇒ not applied; anything else ⇒ uncertain. Owned processes end with the
backend. Uncertain effects put the task in `waiting_user`; an uncertain
**external** effect can never be resumed automatically. Otherwise the task is
`paused`. Resume re-inspects, re-reads and re-checks before proposing anything,
and outside a new owner request its effects use ordinary approval.

## 6. Stop

Chat Stop, the task card's Stop, the Agent page and the emergency stop
(`Host.emergency_stop`) cancel the conversation's asyncio task. The runner
records `cancelled`, stops a preview it was still starting, and re-raises; the
validation tool kills its owned process (Linux supervisor reaps the subtree); no
queued step runs. A backend SIGKILL also ends owned children (supervisor parent
watch) — verified live.

## 7. Workspace / Studio

Studio remains the IDE (Monaco, xterm PTY terminals, Problems, Tests, Output,
Git, debug, search, run configurations). Added:

* `studio.files_changed` events: after an agent edit, clean open tabs reload
  from disk; the task refuses to edit any file with unsaved Studio text
  (`unsaved editor changes`, state `waiting_user`), so user typing is never
  overwritten.
* A **Task** bottom-panel tab (shown when the workspace has a coding task) with
  the same card as Chat: timeline, files, tests, preview, Stop, Show changes.
* **Show changes**: unified diff of exactly the task's changes from its own
  checkpoint snapshots, marking files edited afterwards.
* **Undo these changes**: restores only files whose current hash still equals
  OLIVE's result (hash-checked tool writes; created files go to Trash). Files
  changed afterwards are listed and left alone. No Git commands.
* Python edits drop that module's stale `__pycache__` bytecode (found live:
  an equal-length edit within the same second ran stale code).

Problems parsing adds TypeScript, javac, Go and Rust; test summaries parse
unittest, pytest, dotnet (VSTest and MTP), node --test, Jest/Vitest, cargo, go
and Maven. Counts come only from real process output.

## 8. Preview

* Static websites: `olive/services/static_preview_server.py`, run by the
  existing run service as an owned process, bound to `127.0.0.1` on a free port;
  no directory listings, no hidden paths (`.git`, `.env`), no symlink escape,
  `no-store`.
* ASP.NET Core: `dotnet run … -- --urls http://127.0.0.1:<free port>` (command
  line overrides launch-profile URLs; never 0.0.0.0).
* Web runs are bounded to 30 minutes (console runs keep 2/10 minutes).
* The existing isolated Electron `WebContentsView` preview (sandboxed, no
  bridge, origin-locked, downloads/permissions/popups denied) is reused.
  `LocalPreview` can now be opened by Chat's **Open preview**, and reloads when
  the task edits files or restarts its server. Listener ownership is verified
  (`local_preview.authorize`) before the URL is used.
* Port conflicts: another process on a port is never killed; a failed bind is
  reported (`port unavailable` / `preview failed`).

Supported preview types: static HTML/CSS/JS, ASP.NET Core. Other programs run in
Studio with terminal output. Node dev servers (npm run dev) are **not**
supported yet: they need dependency installation and framework-specific port
flags.

## 9. Desktop, browser and Discord

The Linux desktop stack (AT-SPI observation, KWin identity, portal/EIS input,
GUI-Owl fallback, effect ledger, watchdog) is reused unchanged except for one
new effect:

* **Navigate only** (`effect='go'`): "Open Discord and go to #gen-chat in
  D SERVER", "Go to the general channel on my RaceDay server in Discord". It
  uses the verified quick-switcher route shared with send/draft, verifies the
  destination (and server), and never touches the composer; `communication.send`
  is not required. Clients without a declared layout are refused. "…and send hi"
  cannot be smuggled into a navigation request; "my server" asks which server.

## 10. Known limitations

* Live Discord navigation was **not verified** this session: two safe stops in
  the existing switcher step on this multi-monitor layout (nothing typed, send
  denied by policy). Fixture tests cover the new effect.
* Live Firefox navigation was refused safely because several Firefox windows
  were open (existing identity rule: never pick one by guess).
* No Node/React/Vite scaffolding or dev-server preview (needs installs).
* Go and Rust toolchains are not installed here; parsers are fixture-tested only.
* The coding loop edits at most 8 files per proposal and needs an installed
  local coding model; quality depends on that model.
* Follow-up detection is a finite phrase grammar; other phrasings go to the
  interpreter.
* Studio's built-in terminal remains a user tool (PTY); the agent does not type
  into it.
* One effectful OLIVE task at a time (coding, Agent or desktop).
