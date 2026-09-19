# OLIVE — clarity-first redesign and multi-project Studio

Branch `design/olive-clarity-and-multi-project`, worktree `D:\DMDO`.
Everything below was exercised through the real Electron + Python path with
isolated profiles and temporary projects. No real development folder, account,
message or purchase was touched.

---

## 1. The new navigation and Home

**Navigation.** The global work-item tab shelf is gone. In its place is one
restrained, labelled navigation pane down the left side: an identity block
carrying the Core and the honest runtime line, then Home, then five groups —
Work (Chat, Agent, Research), Build (Studio, Desktop Control), Knowledge
(Projects, Knowledge, Memory), Personal (Mail, Calendar, Tasks, Reminders,
Contacts, Profile) and System (Connections) — with Settings, "Find anything"
and the collapse control pinned in the foot so they never need scrolling.

- Every row is a visible word. Nothing essential is identified only by an icon,
  and nothing requires hovering: compact mode hides the text but each row still
  carries its label as its accessible name.
- Compact mode is the person's choice (`localStorage.navigationCompact`) and
  survives route changes; a route change never collapses it.
- Below 940px the same pane becomes a dismissable overlay with a scrim, opened
  from a slim bar that carries the Core and the current route name. The shell
  and the stylesheet now agree on that number — they did not, and the band
  between them had no navigation at all (fixed, see §9).
- Local navigation stayed local: document tabs live inside Studio, conversation
  history inside Chat, folders inside Mail.

**Home.** One greeting and date; one universal composer (Enter sends and opens
Chat, the hint says plainly `Enter to send · AI offline — replies need a local
model` when no model is reachable); one "Your apps" launcher with a search box,
where the whole tile is the button and there are no nested Open buttons; a
compact "Continue" list of at most four real items with a "Show all N" action,
which is absent entirely when there is no recent work; and the native Today
module. The pinned space cards, the "Open now" tiles, the "Right now" panel and
the separate All Spaces page are all replaced — every destination they offered
is in the launcher and in navigation, exactly once each. There is no permanent
right-hand column.

**One registry.** `desktop/src/navigation/features.ts` is the single source for
navigation rows, the Home launcher, the command palette, search aliases and
availability. Diagnostics declares `within: "settings"` and appears inside
Settings; Developer Mode opts it into navigation as well, through the same
registry (`navigationRows(developer)`), not a second hard-coded list. Nothing
is registered that is not implemented — there are no Voice, Markets or Trading
buttons waiting to disappoint.

## 2. Startup and the olive

Welcome was redesigned and the identity was kept: the same ink ground, the
rotating blue/cyan dot-matrix olive at real depth (`Core`, not a flat image or
a generic sphere), the OLIVE wordmark, one line of copy, **Enter OLIVE**, and a
readiness line that reads `Ready to open · AI offline` rather than an
unqualified "Ready". The Core hands off to its navigation anchor through a
shared layout projection. Startup waits for nothing: no model is loaded to
animate it and no cinematic delay was added. Reduced motion is respected, and
the taskbar/desktop icon is unchanged.

## 3. New project

**Reachable while anything is open.** The Studio header has a labelled
**New project** button, the workspace switcher offers it, the command palette
lists it as "New code project (Studio)", and `Ctrl+Alt+N` opens it. None of
those require closing the current project, going Home, opening an empty Studio,
or visiting settings.

It is deliberately distinct from the four things it is not:

| Action | Where | What it does |
| --- | --- | --- |
| New project | Studio header, switcher, palette, Ctrl+Alt+N | A new project folder on disk, opened as its own workspace |
| New file | Explorer → Files | A file inside the open workspace |
| Open workspace | Studio header, palette | An existing folder, opened alongside the others |
| Add project to this solution | Explorer → project panel | A project inside the open workspace's solution |
| New OLIVE Project | Palette → Projects | An organisational grouping of chats, files and records |

**The wizard.** Four steps in one readable sheet: 1 Language, from real
detected tooling, with a Refresh; 2 Project type, filtered to that language's
actually-installed templates; 3 Name and location, with the native directory
picker, name validation and a live destination preview confirmed by the backend
before anything is created; 4 Options — interpreter or framework, optional
`git init`, and an explicit note that no packages are downloaded. The final
screen names the exact destination and lists every command that ran.

Creation opens the new project as a **separate** Studio workspace and leaves the
current one open. Cancelling at any point before creation writes nothing.

## 4. Languages and what "ready" means

Discovery separates editing support from installed tooling from available
templates. Monaco's syntax list is not consulted. A language is only offered
when its own toolchain is present *and* it has a template OLIVE can actually
create, and nothing is ever installed on the person's behalf.

Measured on this machine (`artifacts/ui-review/clarity/acceptance/journey.json`):

| Language | State | Detail |
| --- | --- | --- |
| C# | Ready to create | .NET SDK 10.0.400, six templates confirmed from `dotnet new list` |
| Python | Ready to create | the detected interpreter, 3.14.5 |
| JavaScript / TypeScript | Ready to create | Node found on PATH |
| Java | Ready to create | javac found |
| Empty folder | Ready to create | no toolchain needed |

The missing case is proven rather than described: a second test launches OLIVE
with a PATH reduced to the Windows system folders, and the wizard reports
`Toolchain missing` for C#, JavaScript, TypeScript and Java, disables those
cards and refuses to create
(`artifacts/ui-review/clarity/acceptance/missing-toolchains.json`).

Discovery is cached for five minutes, refreshable on demand, runs off the event
loop, and is bounded by a declared deadline — a probe that does not answer is
reported as absent rather than waited for. That bound is load-bearing: see §9.

## 5. Multiple independent workspaces

Opening a workspace never retargets another. Studio keeps a set of open
workspaces with a labelled switcher (`Workspace: <name>` with a count), a sheet
listing what is open and what other approved folders exist, and a per-row close.

Each workspace keeps its own open files and dirty buffers, cursor and scroll,
explorer and panel state, terminal sessions, output channels, test results,
debug session and language-service context. Switching A → B and back restores A
rather than resetting it. Every request carries its workspace id, so
diagnostics, saves, Stop, debug and terminals cannot cross.

Closing a workspace with work in it names what would be lost — unsaved files,
terminal sessions, a debug session, running jobs — and offers **Save and
close**, **Close and discard** and **Cancel**. Nothing is discarded silently.

A restart reopens the workspace that was showing and the set that was open. It
resumes nothing: no program, terminal, debug session or agent action restarts
itself.

## 6. IDE capabilities preserved

Language services (OmniSharp, pylsp), DAP debugging (netcoredbg, debugpy),
ConPTY terminals, the .NET solution and project system, structured tests, safe
hash-checked file editing, Monaco, local preview, packages, checkpoints, Git
review and workspace tools are all unchanged and still reached the same way.
Three presentation problems the brief named were fixed: the build configuration
now reads **Debug build / Release build** and the debugger action reads **Start
Debugging**, so no two controls share the word "Debug"; the dock no longer
repeats the tool list, leaving one tool-tab strip in the status bar; and the
assistant is on demand and pinnable, never a permanent empty panel.

## 7. Feature parity

`docs/releases/3.5.1/CLARITY_PARITY.md` is the action-level ledger: every action
that existed before this redesign, where it is reached now, and whether it is
kept, moved or new. The only behaviour deliberately changed is the one the brief
asked for — opening a workspace no longer replaces another.

One regression this work introduced and then fixed: Developer Mode still
promised a Diagnostics shortcut in navigation but no longer had one. It does
again, through the registry.

## 8. Tests

| Suite | Command | Result |
| --- | --- | --- |
| Electron end-to-end | `npx playwright test` | **40 passed, 4 skipped, 0 failed** in 7.4m, and again in 7.6m |
| Python | `.venv/Scripts/python.exe -m unittest discover -s tests` | **757 passed** in 91s |
| Renderer unit | `npm run test` (vitest) | **25 passed** in 1.7s |
| Types | `npm run typecheck` | clean |
| Lint | `npm run lint` | clean |
| Rendered-screen QA | `npx playwright test --config playwright.visual.config.ts tests/visual/clarity-qa.spec.ts` | passed |

The four skipped end-to-end tests are the pre-existing opt-in live-inference
gates — `live-chat`, `m2-closeout-live`, `m3-language-live`, `m4-language-live`
— which need `OLIVE_LIVE_AI=1` / `OLIVE_M2_LIVE=1` / `OLIVE_M3_LIVE_LANGUAGE=1`
/ `OLIVE_M4_LIVE_LANGUAGE=1` and load a real model. They are unrelated to this
work and were skipped before it.

New tests this work added:

- `tests/e2e/clarity-acceptance.spec.ts` — the A–O journey, the missing-toolchain
  state with the tooling removed from the environment, and a check that no
  language server survives the application closing.
- `tests/visual/clarity-qa.spec.ts` — five widths, both themes, reduced motion,
  empty and populated, measuring overflow, clipping, crowding and navigation fit
  rather than only capturing pictures.
- `tests/test_project_creation.py` — 13 tests covering name and destination
  validation, exclusive template writes, explicit `dotnet new` argument arrays
  (`net10.0; rm -rf /` is rejected), honest availability, and the bounded probe.

No test was weakened. The specs that changed did so because a control was
renamed by this redesign (`Find anything`, `New task`, `Compose mail`), because
a new preload key exists (`chooseDirectory`), or because they now wait for the
documented discovery bound before clicking.

**About the earlier runs.** Three full-suite runs before the fixes had late
failures — `studio.spec` and `m4-mail-imap` timing out near the end, each with a
worker teardown timeout. That was not flakiness to be retried away: OLIVE was
leaking a language server per session, and six accumulated OmniSharp processes
starved the machine by the fortieth test. §9.11 has the fix. The two runs above
are complete runs after it, not isolated retries.

## 9. Defects found and fixed during this work

Everything here was found by the acceptance journey or the rendered-screen QA,
not by inspection:

1. **No navigation between 801px and 939px.** The shell switched to the slim bar
   below 940px while the stylesheet only switched layout below 801px, so in that
   band the pane was gone and the bar was still hidden. The two now share a
   number, and a comment in each says so.
2. **The narrow navigation pane was see-through.** Its modifier class was the
   same `overlay` the modal scrim uses, and inherited the scrim's translucent
   background.
3. **Two settings checkboxes shared a line.** The generic "a checkbox and its
   label are one inline control" rule outranks a plain class, so every row class
   that happens to be a `<label>` collapsed to `inline-flex`.
4. **The New project wizard could hang with no languages.** Not slowness: a
   cold `dotnet new list` leaves a grandchild holding the pipes, and
   `subprocess.run(timeout=...)` waits on them again after killing the child.
5. **Studio forgot which workspace was open across a restart.**
6. **A language server answering about a position it had not yet seen reached
   the window as an application error.** Editor intelligence is advisory and now
   returns no answer instead of throwing; rename and command execution still
   report their failures.
7. **In compact mode a navigation row's only accessible name was its tooltip.**
8. **The whole feature list did not fit on a 768px-tall screen**, and launcher
   tile names sat at different heights depending on whether the description
   wrapped.
9. **The safe mail view drew before its inline images resolved**, showing the
   message once without pictures and then reflowing.
10. **Unlabelled action pairs touched** in the project panel and the explorer.
11. **Language servers outlived the application.** On exit the backend stopped
    each one politely and one at a time, which takes longer than Electron gives
    it, so OmniSharp instances kept running after OLIVE had gone — six of them
    accumulated over one suite run and starved the machine. Exit now stops them
    all at once without the polite round-trip, and a test fails if any survives.

## 10. Security and permissions

Unchanged boundaries: sandboxed renderer with context isolation, a narrow
preload, zod-validated IPC, and every consequential operation going through the
existing tool/permission/approval path. Project creation declares
`filesystem.write` and `terminal.execute` and is confirmation-bound like any
other high-risk tool. Commands are explicit argument arrays — never a name
concatenated into a shell string — and both the template short name and any
target framework are validated against a closed set (`net10.0; rm -rf /` is
rejected, and there is a test for it). Destinations must be absolute, inside the
chosen location, and empty: an occupied folder is refused and left untouched. A
failed creation leaves the partial output where the SDK put it and says so;
nothing is recursively deleted as cleanup. No package is downloaded and no
template hook runs without a separate, explicit step.

The one new IPC channel is `olive:choose-directory`, which returns a path and
nothing else — it creates nothing and approves nothing, and Python still
validates the path.

## 11. Performance and limitations

- Toolchain discovery: ~0.6–1.7s warm, up to its declared deadline when a .NET
  CLI home is cold and rebuilding its template cache. It is cached for five
  minutes and never re-probes on a re-render.
- Language servers ready in about a second after a workspace opens.
- Limitations, stated plainly: the wizard's curated template set is deliberately
  smaller than everything `dotnet new` offers; framework upgrades are never
  silent and are not offered here; JavaScript/TypeScript and Java creation
  writes local starter files rather than invoking a third-party scaffolder; and
  the repository object store still has pre-existing missing blobs in old
  history from a failed background gc (recent commits and the worktree verify
  intact, but a full-history push or bundle will fail until that is repaired).

## 12. Evidence

| What | Path |
| --- | --- |
| Acceptance journey A–O, screenshots and data | `artifacts/ui-review/clarity/acceptance/` |
| Language readiness and templates, as measured | `artifacts/ui-review/clarity/acceptance/journey.json` |
| Missing-toolchain state | `artifacts/ui-review/clarity/acceptance/missing-toolchains.json` |
| Rendered-screen QA, five widths, both themes | `artifacts/ui-review/clarity/qa/` |
| QA measurements (overflow, clipping, crowding) | `artifacts/ui-review/clarity/qa/measurements.json` |
| Multi-project journey (earlier capture) | `artifacts/ui-review/clarity/multiproject/` |
| Before — the workbench shell this replaces | `artifacts/ui-review/redesign/wip-shell/` |
| Before — the workbench pages | `artifacts/ui-review/redesign/after/` |
| Full-suite logs, in order | `artifacts/ui-review/clarity/e2e-*.log` |

## 13. Branch, commits and how to run it

Branch `design/olive-clarity-and-multi-project`, worktree `D:\DMDO`, nothing
merged, published, tagged or re-pointed. Fallback code is intact and launcher
defaults are unchanged. Seven commits on top of `dfda419`:

```
60e2e62 Stop leaking language servers when OLIVE closes
0e950af Bound toolchain discovery and stop the wizard hanging on a cold SDK
c7ae152 Fix four layout defects the rendered-screen QA found
1014174 Prove the acceptance journey and keep language answers advisory
385cad5 Restore the Developer Mode Diagnostics shortcut and realign the suite
87d1d19 Add the narrow navigation bar and align the suite to the new shell
85eecbf Replace the tab shelf with labelled navigation and rebuild Home
```

To build and run it:

```bash
cd /d/DMDO/desktop && export PATH=/d/DMDO/.toolchains/node-v24.21.0-win-x64:$PATH && npm run build && npm start
```

To run it against a throwaway profile instead of your own data, set
`OLIVE_DATA_DIR` to an empty directory before `npm start`.
