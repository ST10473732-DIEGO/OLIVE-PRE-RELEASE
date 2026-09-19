# OLIVE workspaces — redesign report and handoff

**Branch** `design/olive-workspaces`, cut from `design/olive-go` at `819dc0a`; the
redesign is commit `d53e835` (this note follows it).
OLIVE GO is untouched: nothing under `desktop/src/features/go/`,
`desktop/electron/main/browser.ts` or `desktop/electron/browser.ts` changed.

Nine pages and the Activity panel were restructured to the OLIVE GO material:
Mail, Tasks, Reminders, Projects, Knowledge, Memory, Desktop Control, Agent,
Chat and the Activity sheet. Routes, navigation labels, IPC calls, handlers
and every accessible name the e2e suite relies on are unchanged unless listed
under *Test changes* below.

## 1. Shared design system

Two new files, imported once from the shared page component so every page
gets them in the same order after `tokens.css`, `app.css` and `workspaces.css`:

- **`desktop/src/design/workspace.css`** — the OLIVE GO material as page
  primitives. Tokens are aliases (`--ws-ink/chrome/raised/field/line/
  line-strong/ring`) of the existing `--bg/--surface/--elevated/--go-field/
  --go-line/--go-line-strong/--go-focus`, so light mode and the existing
  theme switch keep working. Primitives: the page frame (`.ws`, `.ws-head`
  with mark, title, one-line subtitle, status pill and grouped actions,
  `.ws-toolbar`), body regions (`.ws-rail` 248/300 px, `.ws-main`,
  `.ws-side` 360/440 px), `.ws-panel` (head, body, foot, tones), `.ws-card`,
  `.ws-row` (list item that is a control), `.ws-seg` (horizontal and vertical
  segmented control with counts), `.ws-pill`, `.ws-chip`, `.ws-empty`
  (icon tile, heading, one sentence, actions — the OLIVE GO error-page
  shape), `.ws-composer` (raised field with focus ring, the OLIVE GO address
  field shape), `.ws-timeline`, `.ws-facts`, `.ws-notice`, `.ws-disclosure`,
  `.ws-pager`, button hierarchy (`.primary`, default, `.quiet`, `.danger-
  action`, `.icon-button`), the pill search field, and `.ws-switch` (a native
  checkbox drawn as OLIVE GO's toggle so tests still see a checkbox).
  Rules are written `.ws .ws-x` so they outrank the global `button`/`input`
  defaults in `tokens.css` — the same cascade discipline OLIVE GO needed.
- **`desktop/src/design/pages.css`** — per-page compositions of those
  primitives only (widths, gaps, which column collapses at which width).
  No page introduces its own colours or radii.
- **`desktop/src/components/WorkspacePage.tsx`** — `WorkspacePage` keeps
  its old signature and default (`layout="legacy"`: Calendar, Contacts,
  Profile, Research, Settings and the desktop tool panels are unchanged) and
  gains `layout="flow" | "fill"`, `icon`, `status`/`statusTone`, `toolbar`,
  `rail` and `side` slots. New exports: `Rail`, `Main`, `Side`, `Panel`,
  `SectionHead`, `EmptyState`, `Seg`, `Pill`, `Notice`, `Facts`,
  `Disclosure`, `Pager`. `Details` is unchanged.
- `desktop/src/features/personal/shared.tsx` — `Blank` now renders
  `EmptyState` (with optional icon and actions), so Calendar and Contacts
  inherit the designed empty state without being restructured.
- `desktop/src/components/GrowingComposer.tsx` accepts a forwarded `ref`
  (Chat focuses the composer from a starter chip).

## 2. Pages

| Page | Layout | What changed |
| --- | --- | --- |
| **Chat** | rail + conversation | Conversation rail docks open on windows ≥ 1180 px and is remembered (`localStorage` `olive.chat.history`); it overlays with a scrim ≤ 800 px and closes on selection only there. Header groups model/mode into one bordered cluster with icons, a hairline divider, then Attach / Options / More. Message column widened to 880 px; user turns are right-aligned raised bubbles, OLIVE turns carry the olive dot; actions appear on hover. Empty state: Core mark, heading, four starter chips that prefill the composer, drop hint. Composer is the OLIVE GO field: raised, 18 px radius, focus ring, attach button and mode pill on the left, round accent send. Attachments sit above the composer. |
| **Mail** | fill: rail · list · reading pane | A three-column client. Rail: account select, folders with counts, server actions (when an account is chosen), "More" (Draft from Calendar, Local folders). List column: pill search, filter popover (formerly an inline `<details>`), folder title with account and count, rows with a state glyph (draft / unread / read), unread pill, meta. Reading pane: subject with Reply / Reply all / Forward / close, envelope facts, project + remote actions + "More actions" popover, body, "Turn this into" hand-offs, attachments, import limitations. Composer spans list + pane. Empty inbox: Compose a draft / Import an EML file / Connect an account. Below 1150 px the pane replaces the list with "Back to messages". |
| **Tasks** | fill: rail · list · detail | Rail: vertical view switcher with icons (Today / Upcoming / All / Completed / By project) and the project filter. Main: view title and count, pill search, tasks grouped by deadline (Overdue · Today · Tomorrow · This week · Later · No deadline · Completed) in panels; rows keep the check, title, meta, Schedule and Delete. Side: the selected task (description, due, priority, status, project, calendar link) with Edit task / Find a work block / Delete. Below 1180 px the side hides and a title opens the editor. Empty states per view. |
| **Reminders** | flow, two columns | Left: **Upcoming** panel (scheduled reminders with bell icon, kind and time, Edit / Delete) and **Notification history** panel (delivered / snoozed / dismissed rows with a tone pill, Snooze / Dismiss / Open). Right: the reminder form as a raised panel when adding or editing, otherwise a "How reminders work" panel. Header pill shows waiting / scheduled counts. Both lists have designed empties. |
| **Projects** | fill: rail · hub | Rail: search, project rows, "Approved workspaces" disclosure with count in the foot. Main: project hero (title, description, workspace pill), **Connected work** — ten count tiles (Chats, Workspace/Files, Tasks, Research, Knowledge, Web Knowledge, Memories, Calendar, Personal Tasks, Mail) that select the relationship, then the relationship panel (existing `Project relationships` navigation with counts + record cards with "Continue in …") beside a **Workspace folder** panel (trust select, Link a workspace folder). Empty: "Choose a project" with Create a project. |
| **Knowledge** | fill: sources · side | Toolbar: pill search, type filter, count, refresh. Main: source cards in a responsive grid (file icon, name, conversation · kind, health pill, chunks and index kind, Source details / Re-index / Relink / Remove), designed empty with Add a local document, "Website learning and saved material" as a disclosure. Side: **Index health** facts, **Indexing jobs** (latest five with state pills, All jobs opens the existing sheet), **Index maintenance** disclosure (upgrade / cancel). Sheets for details, remove, jobs and the retrieval inspector are unchanged. |
| **Memory** | fill: rail · cards · side | Rail: categories with counts (All memories + each category). Toolbar: search, count, refresh. Main: memories grouped by category when All is selected, cards with category pill (olive for sourced, neutral for manual), source, content, hover edit/delete, "Source and context". Side: **Suggestions** panel (preview of the first three, Review opens the sheet) and **What Memory is** (three sentences). Empty: "Keep what matters" with Add a memory / Review suggestions. |
| **Desktop Control** | fill, centred | Header pill: Checking / Disabled / Idle / Active / Stopped. Objective composer (Control permissions, hint, Submit objective). Notices (status, attachment failure, disabled callout with Open Settings). Then **Active workflow** panel (session with facts and phase timeline, or the designed empty) beside **Controls** (Stop Control, Pause / Resume when active, the Control stopped card with Reset Stop) and **Permissions** (enabled, screen observation, vision fallback, keyboard, mouse, provider + Change). **Developer Details** is a disclosure with the same four lazy tabs. |
| **Agent** | fill: history rail · workspace | Rail: search and task history rows with a state dot. Main: objective composer with workspace and project selectors as bordered fields, Ctrl+Enter hint, Start objective / Cancel current request. Then either the task: title row with state pill and Pause / Resume / Cancel controls, the request, **Steps** timeline panel (state-coloured dots and pills, tool results) beside **Validation** (status pill, summary, evidence) and **Changed files**, error notice, Developer details disclosure — or the ready state with three "how it works" tiles (Plans · Works in a workspace · Validates). Recent tool audit is a disclosure. |
| **Activity sheet** | sectioned | Status panel (Core, label, detail, summary). **Controls** (Cancel current request, Stop desktop control, shortcut). Today module. **Context** row with Clear context. **Appearance** rows: Theme, Reduced motion (switch), Core animation, Show Welcome on startup (switch). **System**: Connections. |

## 3. Behaviour kept

Every IPC call, handler, `aria-label`, dialog title and route is the same.
Selectors the suite depends on still exist: `.messages`, `.message-*`,
`.conversation-items`, `.conversation`, `.chat-composer`, `.composer`,
`.mail-list-item`, `.record-card`, `.project-card`, `.personal-task`,
`.task-timeline`, `.category-tabs`, `.empty-workspace`, `.research-evidence`,
`.sheet`, `.toast`. Buttons that duplicate a header action inside an empty
state have distinct names (Create a task, Create a reminder, Create a
project, Add a memory, Add a local document, Compose a draft) so exact-name
locators stay unambiguous.

## 4. Test changes

- `tests/e2e/shell.ts` — new `openHistory(page)` helper: presses
  "Conversation history" only when the rail is not already open.
  `m2-chat.spec.ts`, `visual/walkthrough.spec.ts` and
  `visual/wip-pages.spec.ts` use it instead of an unconditional click,
  because the rail now docks open on a wide window.
- New evidence specs (not part of the ordinary suite; run with
  `--config playwright.visual.config.ts`): `tests/visual/workspaces-audit.spec.ts`
  (every page, populated and empty, 1440 and 1920; `OLIVE_CAPTURE_LABEL`,
  `OLIVE_CAPTURE_PAGES`, `OLIVE_CAPTURE_SEEDED` narrow the run) and
  `tests/visual/workspaces-qa.spec.ts` (composing mail, task detail and
  editor, reminder form, every page at 1366 / 1100 / 900) and
  `tests/visual/workspaces-light.spec.ts` (light theme). The populated
  run seeds projects, tasks, reminders, memories and drafts through the same
  IPC the UI uses, imports three synthetic EML messages through
  `scripts/seed_visual_mail.py` (temporary profiles only), and adds two
  Knowledge sources through the dialog double. Output:
  `artifacts/core/functionality/workspaces/{before,after,qa}/`.

## 5. Verification

- `tsc --noEmit`, `eslint src electron` and the two new specs: clean.
- `vitest run`: 29 tests, all passing.
- Playwright, targeted (all pages touched): `m2-chat`, `m2-agent`,
  `m2-desktop`, `m2-data`, `m2-handoffs`, `m2-active-fixtures`,
  `m3-personal`, `m3-workflows`, `m4-mail-local`, `m4-mail-content`,
  `mail-accounts`, `m2-core`, `core-motion`, `responsive`, `owned-launch`,
  `m2-review`, `rebrand` — all passing after the fixes below.
- Full Playwright suite (`tests/e2e`, 54 tests): 43 passed, 10 skipped
  (live-environment specs, as before), 1 failed — `olive-core.spec.ts`,
  because the Activity sheet's "Reduced motion" switch had gained a
  description inside its label. The input now carries an explicit
  `aria-label`; `olive-core`, `core-motion` and `visual-security` pass on
  the rerun. `m3-backup.spec.ts` passed in this run.

Defects the tests caught during the pass, all fixed: duplicate exact names
(New project / New Task / New Reminder in empty states), relationship tab
names polluted by their counts (counts are now `aria-hidden`), the Agent
header pill duplicating the exact "Pausing" text, mail rows briefly given
`role="listitem"` (they are buttons again), and the switch label above.

## 6. Visual QA

Contact sheets in `artifacts/core/functionality/workspaces/after/`
(`sheet-populated-1/2.jpg`, `sheet-empty-1/2.jpg`) and `…/qa/`
(`sheet-a..d.jpg`, `sheet-light.jpg`); the `before/` folder holds the
baseline captured from the same fixtures before any change.
Checked: every page populated and empty at 1440 × 900; Mail, Chat, Agent,
Knowledge and Projects at 1920 × 1080; Mail reading pane and composer;
Tasks with a selection and with the editor; Reminders with the form; the
Activity sheet; all nine pages at 1366, 1100 and 900 px; Chat, Mail, Tasks,
Projects, Memory, Agent and the Activity sheet in the light theme; Calendar
and Settings (legacy layout) after the shared `Blank` change.

## 7. Limitations and notes

- The mail list shows sender, subject and meta only: `mail.search` returns
  no date or preview text, and the backend was out of scope, so none is
  invented.
- Tasks view counts are not shown in the rail: `tasks.search` is per view,
  and adding four extra queries per render was not worth it. The main title
  shows the count of the current view.
- Chat's rail state is per device (`localStorage`), not in the profile.
- Calendar, Contacts, Profile, Research, Settings, Studio and Home keep the
  legacy `WorkspacePage` layout by design (not in the brief); they inherit
  only the designed empty state.
- Known unrelated failures keep their classification from the OLIVE GO
  report: the Studio ConPTY Python tests (backend hand-off). `m3-backup`
  passed in this run; it remains sensitive to native dialog focus.
