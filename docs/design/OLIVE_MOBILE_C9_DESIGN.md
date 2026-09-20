# OLIVE Mobile — C9 Approved Design Specification

Status: DESIGN FROZEN
Implementation: NOT YET STARTED
Connect baseline: C1–C8 complete

This document describes the artifact exactly as built. It does not propose
changes, alternatives, or anything beyond what the artifact already shows.
Where the artifact's behavior is a visual approximation of something a real
client would need to do differently (e.g. talking to an actual backend), that
gap is called out explicitly as **Implementation binding required** rather
than papered over with an invented API.

Source of truth: `docs/design/olive-mobile-c9-artifact.html` (single
self-contained file — see "Files to save for Codex" at the end of this
document). This Markdown file is a reading guide to that artifact, not a
replacement for it. If the two ever disagree, the HTML artifact is correct.

---

## 1. Product goals

- Give OLIVE a real, native-feeling iPhone surface that extends OLIVE
  Connect (C1–C8) rather than re-implementing a shrunk desktop.
- Be honest about what a phone can and can't do on its own: no local model
  inference, no arbitrary filesystem access, no unrestricted remote
  execution. Every capability the app offers is explicitly served by a
  paired desktop the person has pairing-trusted.
- Make permission state legible everywhere at once: Off / Ask / Allow is a
  single per-capability, per-device value read by every screen that touches
  that device, so "Offline," "Revoked," and "Permission Off" never drift
  between Chat, Files, Devices, and Home.
- Keep Remote Studio a bounded companion (review, small edits, kick off
  build/test/run) — never a full mobile IDE.
- Cover the unglamorous states (offline, interrupted, revoked, conflicting,
  declined, unavailable) as first-class, polished screens, not afterthoughts.

---

## 2. Final information architecture

**Bottom tab bar (5 permanent tabs):**

1. Home
2. Chat
3. Today
4. Devices
5. Files

**Settings is not a tab.** It's reached via a gear icon in the top-right of
the Home screen's navbar and a gear icon in the Devices list navbar (next to
the "+" add-device action). Settings presents with a centered title and a
"Done" text button in place of a back chevron — a modal-style dismiss back to
Home, because it's an occasional destination, not a daily one.

Remote AI has no tab of its own; it lives inside Chat as a Model / Run-on
pair of controls, since every response already needs that context. Remote
Studio and the pairing flow are drill-ins from Devices, reached by a specific
device's detail screen or a Home shortcut card — not top-level tabs, because
they're occasional actions.

---

## 3. Screen inventory

| Screen | Purpose | Entry point | Primary actions | Important states | Backend capability it depends on |
|---|---|---|---|---|---|
| Home | Daily dashboard: greeting, Ask OLIVE shortcut, Today snapshot, recent chat, paired devices, Remote Studio summary | App launch / Home tab | Tap Ask OLIVE, See all (Today), Open (Chat), Manage (Devices), open Remote Studio, open Settings (gear) | Connect off banner; stale-sync banner; no chat history; no paired devices | Device repository/permissions (C1), Remote AI availability (C7), sync status (C5) |
| Chat list | Conversation history | Chat tab | Open a conversation, start new chat | No chat history (empty state) | Sync (C5) for continuity, Remote AI (C7) for attribution shown per row |
| Chat thread | Ask OLIVE, see Remote AI responses | Chat list row, Home shortcut, "New chat" | Pick Model, pick Run-on device, send, stop generating, simulate approval (Ask-gated) | Model unavailable; waiting-for-approval; thinking; streaming; done; device offline/busy mid-conversation | Remote AI request/response + attribution (C7), device permission gate (C1) |
| Today | Unified agenda: timed events, all-day events, tasks due, overdue, reminders due/snoozed | Today tab | Swipe a task to Complete; swipe a reminder to Snooze/Dismiss; drill into Tasks/Calendar/Reminders | Nothing scheduled today (empty state); overdue banner | Tasks & Calendar Sync (new C9 surface over synced records, C5-style) |
| Tasks | Full task list grouped by Overdue/Due today/Upcoming/Completed | Today → Tasks | Open task detail, mark done | Empty per-group sections simply omitted | Tasks & Calendar Sync |
| Calendar | Month grid + day agenda | Today → Calendar | Open event detail | — | Tasks & Calendar Sync |
| Reminders | Reminders grouped by Due/Upcoming/Snoozed/Completed | Today → Reminders | Swipe to Snooze/Dismiss, open detail | Empty per-group sections omitted | Tasks & Calendar Sync |
| Devices list | This iPhone, devices needing approval, paired devices, nearby devices, revoked devices | Devices tab | Add device (pairing), open a device's detail, open Settings (gear) | No paired devices; no nearby devices; needs-approval row; revoked section | Device repository, pairing, permissions, revocation (C1–C2) |
| Device detail | One device's identity, capabilities, shared Remote Studio workspaces | Devices list row | Set each capability to Off/Ask/Allow, open a shared workspace, revoke access | Offline banner; revoked (terminal) state | Device repository/permissions (C1); per-capability gate for C5/C6/C7/C8 |
| Pairing: Start | Choose scan vs. manual code | Devices "+" / Home empty-state | Scan QR, enter code | — | Pairing/identity exchange (C2) |
| Pairing: Scan QR | Camera viewfinder mock | Pairing start | Simulate scan, switch to manual code | QR expiry note | Pairing/identity exchange (C2) |
| Pairing: Enter code | Manual 6-character code entry | Pairing start | Continue | — | Pairing/identity exchange (C2) |
| Pairing: Connecting securely | Interstitial while a mutually-authenticated channel is set up | After scan/code | (auto-advances) Cancel | — | Mutual TLS pairing handshake (C2) |
| Pairing: Confirm identity | Human-comparable word fingerprint | After connecting | "They match — confirm," "They don't match" | — | Identity fingerprint comparison (C2) |
| Pairing: Waiting | Waiting for the other device to confirm the same words | After confirm | Cancel (→ Cancelled) | — | Mutual confirmation handshake (C2) |
| Pairing: Success | Confirms pairing; states permissions are Off by default | Waiting resolves | Set permissions now (→ Device Detail), Done (→ Devices list) | — | Device repository write (C1) |
| Pairing: Mismatch | Words didn't match; nothing trusted | Confirm → "They don't match" | Try again | Terminal | — |
| Pairing: Expired | Code/QR expired before use | Reachable as a named edge state | Get a new code | Terminal | — |
| Pairing: Cancelled | User cancelled while waiting | Waiting → Cancel | Start over, back to Devices | Terminal | — |
| Pairing: Connection lost | Local connection dropped mid-pairing | Reachable as a named edge state | Retry | Terminal | — |
| Pairing: Denied | Other device explicitly declined | Reachable as a named edge state | Try again | Terminal | — |
| Remote Studio: Workspaces | Cross-device list of shared, bounded workspaces | Home "Remote Studio" card, Device Detail workspace chip | Open a workspace | No shared workspaces (empty); a device's group shown offline/dimmed | Remote Studio session + workspace sharing (C8) |
| Remote Studio: Workspace | One workspace's bounded file tree + Build/Test/Run + session info | Workspaces list row, Device Detail chip | Open the workspace's main file, Build, Test, Run | Unavailable (offline / permission off / not shared); "not a buildable project" for non-code workspaces | Remote Studio bounded file listing + build/test/run (C8) |
| Remote Studio: File | Lightweight code viewer/editor for one file | Workspace's main file | Edit, Save (revision-checked), Build, Test, Run, Stop | Dirty/unsaved; revision conflict; offline draft; build/test/run output streaming | Remote Studio revision-checked save + structured build/test/run + bounded output (C8) |
| Files (OLIVE Inbox) | Incoming file transfers needing approval or already in the Inbox | Files tab | Approve/deny incoming transfer, open a file, Open/Share-Save a verified file | Waiting for approval, Receiving, Verifying, Verified, Interrupted, Failed, Declined, empty Inbox | Authenticated file transfer + SHA-256 verification (C6) |
| Settings | Identity, Connect, Notifications, Appearance, Privacy & Security, Sync, Storage, About | Gear icon (Home, Devices) | Toggle Connect, toggle notifications, open Paired/Revoked devices, toggle sync prefs, view/clear storage | Connect off | Connect state (C3), device repository links (C1) |

Sheets (not full screens, but every one is a distinct piece of UI a
person will see) are listed in §12.

---

## 4. Screen-to-screen navigation

The artifact's router keeps one **stack per tab** plus a single **overlay
stack** for sheets. Two navigation primitives:

- **`push(tab, screen, params)` / `pop(tab)`** — used for same-tab
  drill-downs (e.g. Devices list → Device detail → Remote Studio workspace →
  file). The back chevron always calls `pop()`, so back-navigation is
  real browser-style history, not a fake "go home" button.
- **`jump(tab, screen, params)`** — used for cross-tab entry points (a Home
  card opening a specific Chat thread) and for flows that should **not**
  remain in back-history once finished or abandoned (finishing pairing lands
  on Devices list or Device Detail with the whole pairing flow discarded from
  the stack; starting a fresh pairing attempt after a failure does the same).

Each tab has a defined root screen (`ROOT_SCREEN`): Home → its dashboard,
Chat → the conversation list, Today → the agenda, Devices → the device list,
Files → the Inbox, Settings → its main list. `jump()` always resets to that
root before optionally pushing a target screen on top, so there is never an
orphaned or blank intermediate state.

Sheets open on `openOverlay(type, params)` (pushes onto the overlay stack,
rendered as a bottom sheet over a dimmed backdrop) and close with
`closeOverlay()` (pops one level — nested sheets, like Share/Save opening on
top of a file detail sheet, close back to the sheet beneath them, not all the
way out).

---

## 5. Reusable components

| Component | Class(es) | Used for |
|---|---|---|
| Card list | `.card`, `.card-row` | Every list of tappable rows (devices, files, tasks, settings rows, file tree) |
| Status pill | `.pill[data-tone]` | Online / Busy / Offline / Waiting / Revoked |
| Badge | `.badge[data-tone]` | Small inline tags: model preset, Verified/Failed/Declined, "Edited locally" |
| Segmented control | `.segmented` | Model preset (FAST/NORMAL/MAX), permission level (Off/Ask/Allow), Appearance |
| Toggle switch | `.switch` (settings-scale), `.small-switch` (control-panel scale) | Connect, Discovery, notification prefs, sync prefs |
| Bottom sheet | `.sheet-backdrop` / `.sheet` | Task/event/reminder/file detail, Share/Save, approvals, Run-on picker, revoke confirm, This iPhone identity |
| Banner | `.banner` (`.info` / `.warn` / `.err`) | Connect-off, stale-sync, offline, conflict, offline-draft, honesty notices |
| Timeline row | `.timeline`, `.tl-item` | Today's agenda |
| Swipe row | `.swipe-row`, `.swipe-actions`, `.swipe-content` | Today tasks (Complete), Today/Reminders reminders (Snooze/Dismiss) |
| Output panel | `.output-panel` | Bounded Build/Test/Run log |
| Editor pane | `.editor-pane` | Remote Studio file viewer/editor |
| File-tree row | `.file-tree-row` | Remote Studio bounded workspace listing |
| Empty state | `.empty` | Every "nothing here yet" / unavailable screen |

---

## 6. Visual tokens

Dark is the default/base palette (this is a dark-first product); a full
light palette is defined and applied automatically when the system is in
light mode.

**Dark (base `:root`):**

| Token | Value | Role |
|---|---|---|
| `--bg` | `#0b0f16` | App background |
| `--surface` | `#11171f` | Cards, sheets |
| `--elevated` | `#182029` | Rows, icon chips |
| `--raised` | `#1f2933` | Pressed/selected surfaces |
| `--text` | `#e8eef7` | Primary text |
| `--muted` | `#9db0c7` | Secondary text |
| `--faint` | `#6f819a` | Tertiary text, disabled |
| `--accent` / `--accent-strong` | `#7cc4ff` / `#3d9cf5` | Interaction only (never status) |
| `--success` | `#7fd8a8` | Online / Verified / Allow-passed |
| `--warning` | `#f0c36b` | Busy / Ask-pending / recoverable interruption |
| `--error` | `#ff8f8f` | Blocking offline / Failed / Revoked action |
| `--olive` | `#9ab534` | Brand identity mark only, never UI state |
| `--pimento` | `#c0232a` | Brand mark accent dot only |

**Light** mirrors every token (e.g. `--bg:#eef1f6`, `--accent:#1e63c8`,
`--success:#1c7a4c`) under `@media (prefers-color-scheme: light)` and
`[data-theme="light"]`, so both themes are fully specified, not inverted
guesses.

Font stack: `-apple-system, "SF Pro Text", "SF Pro Display", system-ui,
"Segoe UI", sans-serif` (display face for large titles), monospace `"SF
Mono", "Cascadia Code", Menlo, Consolas, monospace` for code and hashes.

---

## 7. Typography hierarchy

| Use | Size / weight |
|---|---|
| Tab-root large title (`.nav-title-big h1`) | 26px / 700, tight tracking |
| Drill-down nav title (`.navbar h2`) | 16.5px / 650 |
| Sheet title (`.sheet-head h2`) | 16px / 650 |
| Card row title (`.card-row strong`) | 13.5px / 600 |
| Section title (`.section-title h3`) | 13px / 650 |
| Body / control text | 13.5–14px / 400–600 |
| Supporting text (`.card-row small`, `.muted`) | 11.5–12.5px |
| Eyebrow labels (`.eyebrow`, e.g. "MODEL", "RUN ON") | 10.5px / 700, uppercase, tracked |
| Timestamps / tabular figures | `font-variant-numeric: tabular-nums` |

---

## 8. Spacing

- Section horizontal padding: 14px.
- Card-row padding: 12–14px vertical/horizontal, giving each row roughly a
  44–48px touch target with its icon + two lines of text.
- Standard stack/row gaps: 8–10px.
- Sheet body side padding: 16px; grab handle 36×4px, 9px top margin.
- Bottom tab bar buttons: 48px min-height.

## 9. Radii

- `--radius: 14px` — cards.
- `--radius-sm: 9px` — buttons, fields, icon chips, editor/output panels.
- `--radius-lg: 20px` — sheets (top corners only) and side control-panel cards.
- Pills/badges/switches use fully-rounded (999px / half-height) radii.

---

## 10. Status styles (semantics, not just colors)

| Color | Meaning | Examples |
|---|---|---|
| Success (green) | Reachable / verified / a permission's Allow state took effect | Online pill, Verified badge |
| Warning (amber) | Needs attention but recoverable, or a request is pending | Busy pill, Ask-pending states, Interrupted transfer's recoverable framing |
| Error (red) | Blocking or terminal negative | Offline pill (when it blocks an action), Failed badge, Revoked pill, revision-conflict banner |
| Neutral (grey) | Off / inactive / declined | Off permission level, Declined file badge, disabled "This iPhone" row |
| Accent (blue) | Interactive element, never a status | Buttons, links, the streaming cursor, selected segmented option |

Brand green/olive and the pimento red dot are reserved for the app's own
identity mark (header, chat avatar) — they never double as a status color,
so "OLIVE-green" is never confusable with "success-green" conceptually even
though both happen to be green tones on the desktop scale (the app carefully
uses a distinct `--olive` token from `--success`).

---

## 11. Sheets / modals

Nine sheet types, all bottom sheets over a dimmed backdrop, dismissible by
tapping the backdrop or an explicit Close/Cancel/Done:

1. **Task** — due date, project, linked-context banner, mark done.
2. **Event** — time only (read-only in this artifact).
3. **Reminder** — when, Dismiss / Snooze / Done.
4. **File** — from, size, status badge, SHA-256 (when verified), state-specific
   banner and actions (Retry / Cancel transfer / Remove / Open + Share-Save).
5. **Share** — mock native share sheet: Save to Files, Share…, Open in OLIVE GO.
6. **Approval** — requesting device, capability, target, **Deny** and
   **Allow once** as the two co-equal primary actions, with a visually
   de-emphasized "Manage this device's permissions instead →" link below —
   deliberately *not* a one-tap permanent Allow.
7. **Run-on picker** — devices that support the selected preset, devices that
   don't (with the reason), and a permanently-disabled "This iPhone · Local
   AI unavailable" row.
8. **Revoke** — confirms revoking a device; Cancel / Revoke access.
9. **This iPhone** — this device's own identity (name, short code, created
   date), read-only.

---

## 12. Empty states

Every list-type screen defines its own empty state rather than showing
nothing:

- Home: "No conversations yet" (Chat card), "No paired devices" (Devices
  card, with a Pair a device button).
- Chat list: "No conversations yet."
- Chat thread (new): "Ask OLIVE anything… nothing runs on this iPhone."
- Today: "Nothing scheduled today."
- Devices list: "No paired devices" (with Pair a device button), "No nearby
  devices" (Discovery is opt-in copy).
- Remote Studio workspaces: "No shared workspaces… there's no arbitrary
  filesystem browsing."
- Files: "Inbox is empty."

## 13. Error / unavailable states

- Connect off (Home banner).
- Stale synced data (Home banner, tied to a specific offline device).
- Model unavailable (Chat banner when the selected preset has no serving
  device).
- Remote AI device offline/busy mid-conversation (status pill + attribution
  stay accurate; sending is blocked until a valid Run-on device exists).
- Device offline (Device Detail banner: "Permissions still apply once it
  reconnects").
- Device revoked (Device Detail terminal banner + "Remove from history").
- Remote Studio unavailable — three distinct reasons, each with its own
  copy: device offline, Remote Studio permission off everywhere, workspace
  not currently shared.
- File: Interrupted (connection lost mid-transfer, Retry offered), Failed
  (SHA-256 mismatch, discarded, Remove only), Declined (never downloaded,
  Remove only).
- Revision conflict and offline draft in Remote Studio — see §18.

---

## 14. Pairing states

Full state machine (12 screens, §3 has entry points and actions for each):

`Start → Scan QR / Enter code → Connecting securely → Confirm identity
(word comparison) → Waiting for the other device → Success`

Branches: **Mismatch** (words don't match), **Expired** (code/QR timed out),
**Cancelled** (user cancels while waiting), **Connection lost** (network
drops mid-pairing), **Denied** (other device explicitly declines). All five
branches are terminal, single-action screens ("Try again" / "Get a new
code" / "Start over") — none of them silently retries or auto-recovers.

Success explicitly states: **"Paired successfully. Permissions are Off
until you choose otherwise — Remote AI, Files, Sync and Remote Studio don't
turn on by themselves."** Two actions: "Set permissions now" (→ that
device's Device Detail) or "Done" (→ Devices list). No permission is ever
defaulted to Allow by the pairing flow itself.

---

## 15. Permission states: Off / Ask / Allow

Every device has exactly six independently-set capabilities, each Off / Ask
/ Allow, edited only from **Devices → Device Detail → Capabilities &
permissions** (a 3-way segmented control per row):

1. Remote AI
2. Tasks & Calendar Sync
3. Chat continuity
4. Receive Files
5. Send Files
6. Remote Studio

This is the single source of truth: Home's device rows, Chat's Run-on
picker, the Files Inbox, and Remote Studio's workspace list all read the
same per-device value rather than keeping their own copy. Approval sheets
never grant a permanent Allow — they offer Deny / Allow once, plus a link
back to this same screen for anyone who wants to make it permanent.

---

## 16. Remote AI provider/model behavior

- Three presets: **FAST, NORMAL, MAX**. Which devices can serve a given
  preset is per-device (`aiPresets` on the device record) — in the shipped
  data, Diego's Studio PC serves FAST/NORMAL and Gaming PC serves MAX.
- Chat shows **Model** and **Run on** as two separate, clearly labeled
  controls — never merged into one ambiguous picker.
- Attribution is always shown: `OLIVE {preset} · {device name}` above the
  response, "Thinking on {device}…" while waiting on the response, and
  "Answered by {device}" once it completes.
- If the selected device's Remote AI permission is **Ask**, sending shows an
  explicit "Waiting for approval on {device}" state before anything runs —
  never silently proceeds. (In the artifact, a "Simulate approval" control
  stands in for the real desktop-side prompt this represents.)
- If Remote AI is **Off** everywhere, or the selected preset has no serving
  device, Chat shows a "model unavailable" banner and disables sending
  rather than falling back to anything local.

---

## 17. Truthful iPhone local-AI unavailable behavior

The Run-on picker always includes a permanently-disabled row: **"This
iPhone · Local AI unavailable."** It is never selectable and never implied
to be a working option. The artifact's copy is explicit in multiple places
("nothing runs on this iPhone," "Responses are generated by a paired device
you choose below") specifically so this isn't a one-off disclaimer but a
consistent claim across Home, Chat's empty state, and the picker.

**Implementation binding required:** if a future OLIVE Mobile release adds
genuine on-device inference, this row's disabled state and copy are exactly
what should change — nothing else in the Chat flow assumes local-only
absence beyond this one row and the associated banners.

---

## 18. Today / Tasks / Calendar / Reminders behavior

- **Today** is the single daily surface: one timeline mixing timed events,
  an all-day event, tasks due, and reminders due/snoozed, plus an overdue
  banner. Tasks and reminders in the timeline are swipeable (see below);
  events are not (no quick action applies to a calendar entry here).
- Swipe-left on a **task** row reveals **Complete**.
- Swipe-left on a **reminder** row reveals **Snooze** and **Dismiss**.
- Swiping is a real pointer-drag gesture (delegated `pointerdown` /
  `pointermove` / `pointerup` on `document`, since the app re-renders whole
  screens on state change), not a static mock — it tracks drag distance,
  snaps open past a threshold, and the action buttons underneath are real
  buttons wired to the same handlers Tasks/Reminders use directly.
- **Tasks**, **Calendar**, and **Reminders** exist as full drill-down
  screens (grouped by Overdue/Due/Upcoming/Completed, a month grid + day
  agenda, and Due/Upcoming/Snoozed/Completed respectively) for anyone who
  wants the complete list rather than just today's slice.

---

## 19. Files / OLIVE Inbox behavior

Seven states, each with distinct copy and actions:

| State | Meaning | Actions |
|---|---|---|
| Waiting for approval | Incoming transfer needs a decision | Approval sheet: Deny / Allow once / manage permissions |
| Receiving | Transfer in progress | Progress bar, Cancel transfer |
| Verifying | Fully received, SHA-256 check in progress | (no action; transient) |
| Verified | SHA-256 confirmed | Open, **Share / Save** (mock native share sheet) |
| Interrupted | Connection lost mid-transfer, nothing unverified kept | Retry |
| Failed | SHA-256 mismatch, file discarded | Remove |
| Declined | Transfer was declined, never downloaded | Remove |

OLIVE Mobile never auto-exposes a received file to other apps — Share/Save
is an explicit, separate action after verification, and the sheet says so
directly ("OLIVE Mobile doesn't expose received files to other apps until
you choose one of these").

---

## 20. Remote Studio workspace/file/edit/build/test/run UX

- **Workspaces list**: grouped by the sharing device (with its live status
  pill), each row a specific shared workspace — never arbitrary filesystem
  browsing. In the shipped data: Gaming PC shares *RaceDay* and *OLIVE Test
  Project*; Work Laptop shares *Coursework*.
- **Workspace screen**: a bounded file tree (only the workspace's own files,
  with directories shown for context but only the workspace's designated
  main file actually openable), a session/connection status row with the
  current revision, and Build/Test/Run actions. A workspace with no
  build/test/run defined (Coursework, a non-code folder) shows those three
  actions disabled with "This workspace isn't a buildable project" — build
  tooling is not assumed to exist for every shared folder.
- **File screen**: read view by default; **Edit** switches to a lightweight
  textarea; **Done editing** returns to read view and marks the file dirty
  ("Edited locally" badge). **Save** is revision-checked (disabled while
  offline; see §21 for the conflict path) — never a raw overwrite.
- **Build / Test / Run**: each streams into a bounded, scrollable output
  panel line-by-line, prefixed with which device is running it ("running on
  Gaming PC"). Test results show a summary line (passed/failed/skipped/
  duration) plus per-test detail lines. Run has a **Stop** action while in
  progress. Remote Run is non-interactive — there is no stdin, shell, or
  interactive prompt in this artifact.
- Explicitly **not** designed, matching C8's actual scope: shell/terminal,
  PTY, arbitrary commands, debugger, LSP, package installation, or
  unrestricted filesystem access.

---

## 21. Offline draft and revision-conflict UX

Two distinct, non-overlapping banners in the file editor, both surfaced only
when there's a local unsaved edit (dirty):

- **Offline draft** — the owning device is offline. Banner: "Unsaved local
  draft — {device} is offline, so this edit only exists on this iPhone… Its
  revision will be checked again once {device} reconnects." **Save stays
  disabled** the entire time the device is offline; nothing is claimed to be
  saved remotely.
- **Revision conflict** — the file changed on the owning device since
  editing started (surfaced here via a "simulate conflict" control since
  there's no live desktop to actually race against). Banner: "This file
  changed on {device}. Saving now would silently overwrite it." Two actions
  only: **Reload** (discard the local draft, take the newer revision) or
  **Keep local draft** (dismiss the banner, edit remains local-only,
  unsaved). There is no path in this artifact that silently overwrites a
  newer remote revision.

---

## 22. Settings structure

Reached via gear icon on Home and Devices; presented with a "Done" dismiss.

1. Identity row (this iPhone's name + short code → This iPhone sheet).
2. **Connect** — Connect on/off toggle (with live status text), Paired
   devices link (→ Devices list), Discovery toggle (off by default, opt-in
   local-network mDNS-style lookup).
3. **Notifications** — Trusted approvals, File transfers, Remote AI
   completion, Sync activity (independent toggles).
4. **Appearance** — System / Light / Dark segmented control.
5. **Privacy & security** — Activity & audit log, Revoked devices (→
   Devices list), plus a standing honesty banner: "OLIVE Mobile doesn't use
   cloud AI. Remote AI and sync only happen through devices you've
   explicitly paired."
6. **Sync** — Tasks & Calendar Sync toggle, Chat continuity toggle (mirrors
   the two corresponding per-device capabilities at a global-preference
   level).
7. **Storage** — Downloaded files (size), Clear downloaded files.
8. **About** — Version ("OLIVE Mobile 0.1 (C9 design)"), Help.

---

## 23. iPhone safe-area behavior

The artifact renders inside a drawn phone frame (390×844 aspect ratio,
scaling down on narrow viewports) with a drawn notch and home-indicator bar
purely for presentation. **This is a design-time approximation, not the
runtime technique a real app should use.**

**Implementation binding required:** a real build must use the platform's
actual safe-area facilities (e.g. `SafeAreaInsets` in SwiftUI /
`safeAreaLayoutGuide` in UIKit, or `env(safe-area-inset-*)` if the client is
web-based) for the status bar, navigation bars, the bottom tab bar, and any
bar that pins to top/bottom — the artifact's drawn notch/indicator are
stand-ins for that, not a spec for exact inset values.

## 24. Keyboard behavior

Chat's message textarea calls a `chatKeyboardOpen(true/false)` handler on
focus/blur that tightens the input bar's bottom padding while composing —
a placeholder for real keyboard-avoidance. **Implementation binding
required:** the real behavior should come from the platform's keyboard
layout guide, not a fixed padding change; this artifact only demonstrates
*that* the input bar should react, not the exact avoidance mechanics.

## 25. Accessibility / touch-target expectations

- Card rows, list rows, and buttons are sized to roughly 44–48px minimum
  touch height (Apple HIG's minimum), including the 48px-tall bottom tab
  bar buttons.
- Icon-only actions (Settings gear, "+" add device) carry `aria-label`.
- Focus is always visible (`:focus-visible` outline in the accent color) on
  every interactive element, not just a subset.
- Status is never color-only: every pill/badge pairs its color with a text
  label ("Online," "Busy," "Verified," "Failed," …), and swipeable actions
  are also reachable by opening the row's detail sheet (Snooze/Dismiss/Mark
  done are present there too), so no action is swipe-only.
- **Implementation binding required:** VoiceOver labeling, Dynamic Type
  scaling, and reduced-motion handling for the streaming cursor / spinners
  are not modeled in this HTML artifact and need real platform work.

---

## 26. Intentionally unavailable functionality (by design, not omission)

- No local model fallback — the iPhone never claims to run FAST/NORMAL/MAX
  itself; a disabled Run-on row makes this explicit rather than silently
  omitting it.
- No remote terminal, PTY, debugger, LSP, package installation, or
  unrestricted filesystem access in Remote Studio.
- No one-tap "Allow always" from an approval popup — permanent grants only
  happen from Devices → Device Detail → Permissions.
- No arbitrary Remote Studio filesystem browsing — only workspaces
  explicitly shared by a paired device appear, ever.
- No automatic cross-app exposure of received files — Share/Save is a
  separate, explicit step after verification.

## 27. C10 is out of scope

**Internet relay (C10) is explicitly NOT part of this design.** Every flow
in this artifact assumes the existing local pairing and transport model
from C1–C8 (mutual-TLS pairing, local discovery, local Remote AI/Studio/file
transfer). Nothing here should be read as implying or requiring a relay,
cloud broker, or any non-local transport.

---

## 28. Files to save for Codex

The artifact is a single self-contained HTML file — no build step, no
external assets beyond it. Save exactly these two files:

1. **`docs/design/olive-mobile-c9-artifact.html`** — the complete, approved,
   interactive artifact source (entry point: open this file directly in a
   browser; it is fully self-contained, including all CSS/JS inline).
2. **`docs/design/OLIVE_MOBILE_C9_DESIGN.md`** — this document.

No other files are part of the C9 design deliverable.
