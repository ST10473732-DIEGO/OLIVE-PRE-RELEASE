# OLIVE post-entry redesign — rationale, evidence and record

Branch: `design/olive-complete-ui-refresh` (from `development/3.5.1-electron-experience`
at `b1fee22`, M4 complete). Presentation-only work on the Electron/React renderer.
The Welcome screen, dot-matrix Core renderer, green desktop icon, Python services,
bridge contracts, permissions, approval binding, data schemas and the Qt fallback are
unchanged. The branch is not merged, tagged or made the launcher default.

## Starting checkpoint and baseline

- Source commit `b1fee22` on a clean working tree; baseline tests at that point:
  732 Python, 25 frontend, 7 harness, 37 ordinary Electron + 4 opt-ins (M4 record).
- Baseline screens: `artifacts/ui-review/redesign/before/` (same synthetic fixture,
  1440×900 and 1366×768, dark and light). Baseline measurements: a baseline worktree
  build of `b1fee22` run three times with `tests/visual/baseline-measure.spec.ts`
  (`artifacts/ui-review/redesign/before-measure-{1,2,3}/measurements.json`).

## What the baseline looked like

- Navigation was a column of unlabeled icons; Mail, Calendar, Contacts, Tasks and
  Reminders were reachable only through All Spaces or the palette, and the All Spaces
  cards for those four were still disabled as "Not implemented yet" although M3/M4
  shipped them.
- A 58px breadcrumb bar and a floating "Ready" label used the full width for two words.
- Every workspace opened with a 30–42px marketing heading; Home's "Today" sat below the
  fold at 1440×900.
- Feature pages did not scroll: at 1366×768 the Calendar's last rows were unreachable.
- Walls of equally weighted bordered buttons (Chat tools row, Calendar toolbar, Studio
  header, Mail folders as boxes); native Windows scrollbars on the dark theme; an empty
  model select in Chat; full-width selects in Settings.

## Direction: a quiet instrument

OLIVE is a local instrument, not a website. The post-entry application reads like a
precisely machined object: a deep ink ground, three surface levels separated by
luminance and hairlines rather than boxes, one source of light (the cyan Core), a
labelled spine of navigation, and typography that is calm at rest and dense where work
happens.

- **Identity.** The dot-matrix Core is the only intelligence mark. It sits at the top of
  the spine with its real state beside it ("Ready", "Thinking", "Approval required · 1")
  and opens the activity centre. Welcome → Enter OLIVE → Home is unchanged; the Welcome
  screen keeps its baseline composition, colours and type (pinned in `app.css`).
- **Colour.** Near-black blue ground; `--surface`/`--elevated`/`--raised` layers; a
  single cyan-blue accent with a soft selection wash; amber for approval/attention,
  coral for danger, mint for success. Light mode is a native token set. Nothing is
  green except the desktop icon.
- **Depth and light.** Selected navigation carries a 3px accent mark; focus is always
  a 2px accent ring; shadows only on floating layers (sheets, menus, toasts).
- **Type.** Segoe UI Variable with system fallback, no bundled fonts or CDN. Page
  titles 22px, section titles 16px, body 14–15px, meta 12–13px; tabular numerals in
  lists and the calendar.
- **Composition.** Spacious where the user reads or writes (Home, Chat); tool-grade
  where they operate (Studio, Mail, Calendar, Settings). Each workspace has a compact
  header (title, one line of context, actions) instead of a hero.
- **Motion.** 140ms state changes, 160ms page rise-in, overlay fade for layers; drawers
  do not slide so their targets are clickable from the first frame (measured: drawer
  slide added ~170ms before a palette target was stable). Reduced motion (system or
  OLIVE preference) removes all of it. The Core keeps its own renderer and preferences.

## Information architecture

- **Spine** (232px expanded / 68px collapsed, persisted; Studio remembers its own
  compact preference): **Ask** (Home, Chat, Agent) · **Build** (Studio, Research,
  Desktop Control) · **Know** (Projects, Knowledge, Memory) · **Personal** (Mail,
  Calendar, Contacts, Tasks, Reminders) · foot: All Spaces, Settings, Connections,
  Commands, Diagnostics (Developer Mode), theme, collapse. Below 800px width the spine
  is always compact; below 740px height its items shrink to 27px so it never needs to
  scroll on 1366×768 or 1000×700 windows.
- **Command palette** (Ctrl+Shift+P): grouped into *Start* (New Chat, New Project, New
  Calendar Event, New Personal Task, Compose Mail, Open Workspace) and *Go to* (every
  space, Diagnostics). The query resets on every open; typing works immediately.
- **Home**: greeting line, universal composer (the same `interaction.submit` path as
  before — no Home-only parser), starter chips that only pre-fill the composer, recent
  conversations/workspaces that reopen the exact record, pinned spaces as compact
  tiles, and a Today panel from `personal.today` with a designed empty state.
- **All Spaces**: every shipped space is enabled; pinning is a pressed toggle.
- Routes, `navigate()` ids, handoffs and `hidden` route hosts are unchanged, so
  Projects relationships, Reminders record links and the palette keep working.

## Screens redesigned

Home · All Spaces · Chat (header actions, model placeholder when no local model,
speaker bubbles, branch controls, Markdown/code/table/blockquote) · Agent (objective
surface, task badge tones, timeline with state dots) · Studio (grouped toolbar, title
with switch-workspace sheet and truncating path, explorer with clamped indentation,
dirty markers, single output header with channel select and Problems/Tests/Git/tools,
loaded-workspace-without-file state, theme-aware terminal, quieter assistant) ·
Research · Desktop Control (prominent Stop, disabled-state callout) · Projects ·
Knowledge · Memory · Contacts (scrolling master list, initials, sticky detail) ·
Calendar (segmented views, chip filters, weekday strip, dimmed outside days, today
marker, wrapping long titles, "+N more") · Tasks (segmented views, check control,
priority badges) · Reminders (formatted times, badges) · Mail (icon folders with
counts, draft rows with recipients, unread badge, bordered detail with empty state,
readable composer) · Profile · Settings (search with icon, sticky category list,
bounded field widths, alert/callout styling) · activity centre · palette · approval
sheet · toasts.

## Parity

See `PARITY_CHECKLIST.md` (written before the old shell was replaced). Every handler
and `window.olive`/`call` method is the one that existed before; only presentation
changed. The existing Playwright suite is the enforcement: 37 ordinary scenarios pass,
4 opt-ins remain opt-in. Three test edits were made deliberately and are explained in
the commits: the M1 assertion that Contacts is disabled on All Spaces (it is shipped),
the M1 unit test for the old "Available in Electron / Temporary Qt fallback / Not
implemented yet" captions, and two locators (`m3-workflows`, `live-chat`) scoped to the
navigation because the spine now also lists Contacts/Chat.

## Defects found and fixed along the way

- Feature pages could not scroll (Calendar clipped at 1366×768).
- All Spaces disabled four shipped native workspaces.
- Discarded Studio buffers could be restored from a stale runtime snapshot when
  `runtime.initialized` arrived after typing (frontend adapter fix in `Studio.tsx`).
- The palette query persisted between opens.
- Backend, separately committed with regressions: mis-encoded Ollama status text
  ("Ollama unavailable ? start …"), and Mail list summaries lacked recipients so drafts
  could not be told apart.
- Narrow windows: Studio and Chat headers wrapped character-by-character; fixed with
  proper flex bases, word wrapping and a truncating path.

## Validation (fresh, on the final commit)

| Check | Result / log |
| --- | --- |
| `python -m compileall -q .` | exit 0, `artifacts/ui-review/redesign/logs/compileall.log` |
| Python `unittest discover -s tests` | **733 passed** (`logs/python-tests.log`) |
| Frontend unit (`npm test`) | **25 passed** |
| `npm run typecheck`, `npm run lint`, `npm run build` | pass |
| Harness (`node --test scripts/*.test.cjs`) | **7 passed** |
| Ordinary Electron (`npx playwright test`) | **37 passed, 4 opt-in skips** (`logs/e2e-final.log`) |
| Opt-in live local streaming (`OLIVE_LIVE_AI=1 … live-chat.spec.ts`) | **passed**; real qwen3:8b stream, Stop, retention (`logs/e2e-live-chat.log`, `.experience-351/electron/chat-live-stream.png`) |
| Visual capture with edge-case fixture | **passed**, 74 screens, no page errors, no accidental overflow (`artifacts/ui-review/redesign/after/`) |

The Qt fallback GUI harness (49 checks) was not rerun: no Qt code changed.

## Visual QA

Fixture: `scripts/seed_visual_fixture.py` + API-seeded personal data — long and
single-character titles, a 120-character conversation title, a 60-line code block, an
8-column table, Unicode (café, Straße, 東京, العربية, emoji), a long unbroken URL, a
deep 9-level path with a 70-character file name, 30 contacts with long names and two
addresses, five events in one day, long event titles, 15 tasks incl. completed, drafts
with four recipients and a long subject, an empty draft, a real Python validation
error, a real offline error toast, a real backend approval that is cancelled, and the
unsaved-buffer sheet.

Content viewports checked (`setContentSize`): 1920×1080, 1440×900, 1366×768, 1000×700
and 760×560; dark and light; keyboard-only palette (Ctrl+Shift+P → type → Tab → Enter)
and spine focus rings. Every capture in `artifacts/ui-review/redesign/after/` was
opened and inspected; earlier `wip1`–`wip9` sets record the defects found and fixed
(rail overflow at 768, chat layout collapse, two-column foot, explorer depth, contact
list scrolling, header wrapping, palette query). An automated check for elements
extending past the viewport outside scroll containers reports none on the final set.

Interface enlargement (150%) is exercised by `olive-core.spec.ts` through the
application's own scale setting; this is Chromium zoom, not a physical multi-DPI test.

## Performance (same procedure, 3 runs each, same machine, Ollama unreachable)

| Metric | Before (`b1fee22`) | After |
| --- | --- | --- |
| Startup to "Your local space is ready" | 1838–1878 ms | 1833–1884 ms |
| Palette navigation (open → Open X → +200 ms wait), Mail | 267–273 ms | 284–293 ms |
| Palette navigation, Chat | 321–326 ms | 377–383 ms |
| Spine navigation to a retained route (Agent) | 32–33 ms | 31–34 ms |
| First mount of a lazy route (Research) | 343–847 ms | 340–852 ms |
| Studio Test → completed | 376–397 ms | 389–404 ms |
| Monaco: 60 characters typed | 310–349 ms | 306–345 ms |
| Renderer process working set / idle CPU | 202 MB, 0.16–0.18 % | 228–231 MB, 0.15–0.16 % |
| GPU process | 113–114 MB | 128–132 MB |

Live streaming: first visible token 16.7 s with qwen3:8b cold on this machine — model
bound, not compared. Renderer memory rose ~25 MB (more retained DOM: labelled spine,
Today panel, richer lists); idle CPU is unchanged. No metric regressed materially.

## Remaining limitations

- Loading states are brief and were not captured as still images; they use the
  existing "Opening …" fallbacks and `role="status"` text.
- Mail's "Review submission" surface was not captured because it is honestly disabled
  without a configured connection; the M4 SMTP tests exercise it with a loopback sink.
- Popover placement (workspace actions menu, chat "more") anchors to the right edge and
  was inspected at 1440 and 760 widths only.
- The Explorer clamps indentation after six levels; deeper names rely on the tooltip,
  the tab title and the resizable panel.
- Windows DPI scaling and multi-monitor DPI changes were not physically tested.
- The four opt-in Electron scenarios other than live-chat (Agent/public Research and
  the M3/M4 local-language workflows) were not rerun for this presentation change.

## Launch

```powershell
scripts\launch_electron_preview.ps1
```

opens an isolated synthetic preview profile of the current build
(`cd desktop; npm run build` first). The Qt default launcher is unchanged.

## Continuation record

State at the end of this session: all work committed on
`design/olive-complete-ui-refresh`; working tree clean except ignored evidence; the
temporary baseline worktree used for measurements was removed. If resuming: the
capture spec (`desktop/tests/visual/redesign-capture.spec.ts`) and measurement spec
regenerate all evidence; open the `after/` captures rather than starting from the
`before/` set. To re-measure the baseline, `git worktree add <tmp> b1fee22`, junction
`desktop/node_modules`, build, and run `tests/visual/measure.spec.ts` there with
`OLIVE_PYTHON` pointing at this repository's `.venv`.

No `frontend-design` skill was available in this session; the design work was done
directly.
