# M3 implementation and internal acceptance

Status: **M3 implementation and internal acceptance complete.** This file is the single M3 completion record;
no intermediate user review or ZIP is required. M2 baseline `96fb78b` and all
125 original M2 action mappings remain. No release tag or M4 work is authorised.


## Final fresh checks

Implementation commit `20e4e9e`; native Restore harness correction `7a868b6`;
populated-Home capture assertions `1ed4c29`. The following documentation commit
records completion; `git log -1` identifies that final record. Branch remains
`development/3.5.1-electron-experience`; no tag created.

| Check | Fresh result | Local evidence |
| --- | --- | --- |
| Python incl. native/security/language/controller regressions | 690 passed, 29.620 s | final-regression-04/python.log |
| Compilation | exit 0 | final-regression-04/compile.log |
| TypeScript / lint / production build | all exit 0 | final-regression-04/frontend-*.log |
| Frontend | 15 passed, 6 files | final-regression-04/frontend-test.log |
| Harness safety/first-outcome capture | 7 passed, no skips | final-regression-04/harness.log |
| Complete ordinary Electron | 27 passed, 3 opt-in skips, exit 0 | final-ordinary-05/electron.log; results.json |
| Installed local model through Electron | 1 complete workflow passed, exit 0 | final-live-05/language.log; screens/language-result.json |
| Qt fallback | 49 checks passed, no errors, clean shutdown | final-qt-02/results.json |

Paths above are relative to ignored `artifacts/ui-review/M3/`. The earlier full
`final-regression-04` also passed 27/3 before the Home capture assertion was
strengthened; `final-ordinary-05` is one fresh complete ordinary run after that
change, not a collection of focused retries. The Python/application code did not
change during capture corrections. Both complete runs remain separate.

Ordinary skips: `DMDO_LIVE_AI` is the historical local-chat/model streaming opt-in;
`DMDO_M2_LIVE` is the Agent/public-Research external-source opt-in, not repeated
in M3; `DMDO_M3_LIVE_LANGUAGE` is deliberately disabled in ordinary tests and run
separately in final-live-05. None is an unreported pass. No new external desktop
acceptance or broad model/provider benchmark was performed.

The final local-model conversation used three matching delegated one-action
approvals and verified actual saved records, two-hour availability on the requested
day, Agent read and full backend restart. Other source/ID/clock cases are explicitly
controlled tests, not claims about universal natural-language reliability.

Final screenshots are in `final-ordinary-05/screens/`; additional self-inspected
Home populated capture is `home-painted-evidence/screens/home-today-1366.png`.
The native capture now waits for a browser paint after scrolling and asserts the
actual task is fully in the viewport. This changes evidence timing, not Home layout.

Measured palette-to-visible-heading samples in `home-painted-evidence/screens/result.json`
were 54-481 ms (including test-driver and navigation overhead). Cached Contacts and
Calendar samples were 84 and 73 ms. These are not pure renderer benchmarks, frame
rates or backend completion latency. Local-model stage timings remain in the
language result, separately from UI navigation. GPU/combined-model memory remains
unmeasured.

All test instances were isolated; harness shutdown closes their owned Electron/
Python processes. Synthetic profiles and evidence are retained locally for diagnosis,
not committed. The final read-only process check found no active M3 fixture Electron/Python processes; see `final-cleanup.json`. No real profile, personal record, account or credential was modified.

## Implementation and acceptance map

All operations use the existing Electron/private protocol/Python runtime. The
native controller registers explicit tools with existing permission and
confirmation services; React never opens the database or routes natural language.

| Check | Working entry and implementation | Evidence and classification |
| --- | --- | --- |
| A Profile | All Spaces/Profile; profile.get/update/avatar; validated optional preferences, working hours, timezone and default calendar | Real forms and full Electron/backend restart in m3-language-live; corrupt optional settings/revisions in test_personal_recovery/core |
| B Contacts | Contacts list/detail/edit, bounded search/resolution, duplicates and explicit merge preview | Real UI merge/edit and delegated merge approval in m3-workflows; installed-model ambiguous James lookup and selected ID in m3-language-live; identifier/alias/link and conflict unit cases |
| C Calendar language | Home/Chat through shared interpreter; staged event and correction, actual approval, persisted ID/revision | m3-language-live installed qwen3:8b / gpt-oss:20b roles unchanged; actual saved time and restart asserted, not injected intent |
| D Calendar recurrence | Month/Week/Agenda/Day, event drawer, calendars, occurrence/series changes | Actual UI edits one of three occurrences; other instances unchanged. Real API all-day/overnight fixtures. DST/count/UNTIL/month/leap/exception unit cases |
| E Free time | calendar.free_busy and Tasks Schedule/Find slots/Save linked block | Deterministic controlled busy intervals plus real UI scheduling in m3-workflows; actual conversational date/duration output checked separately |
| F Personal Tasks | Today/Upcoming/Completed/Project; create/edit/complete/reopen/delete, optional links and scheduling | Real Electron/API completion/reopen/link persistence. Unit Agent-task link proves no Agent execution state changes |
| G Reminders | Persistent runtime scheduler, notification history, Snooze/Dismiss/Open | Real due delivery/snooze/dismiss/restart; controlled-clock tests cover catch-up, duplicate delivery, recurrence, edits, completion/reopen and recovery. No Windows time change |
| H Interchange | Native chooser -> preview -> exact selection -> approval -> transactional commit; CSV/vCard/ICS exports | Real parser/store and actual approval buttons; chooser return values are controlled fixture paths. Re-import retains IDs, malformed input rejected. Formula/unsupported-field/UID/stale revision unit cases |
| I Backup | Settings Backup & Data, SQLite backup API, staged restore and safety backup | Real separate profiles and native Restore confirmation under delegation. Actual restarted records/relationships/dismissed history checked. WAL/corruption/dangling-reference/rollback unit tests |
| J Composition | Shared Home/Chat/Agent context; contact -> event -> task -> reminder/project | Installed-model continuing conversation and Agent read. Independent compound proposals and stale old-record reference rejection use controlled semantic output, real runtime/controller |
| K Denial/cancel | Existing action-bound confirmation; direct forms still honour explicit Deny | Actual UI cancels delete with unchanged data. Unit deny, obsolete proposal revision, cancelled commit/export and import revision conflicts |
| L Offline | All manual native routes use local services without model calls | Real forms/workflows configure Ollama unavailable. No network-dependent native service or remote account; system networking untouched |

A proposed new record has no persisted ID. Save it before linking a dependent
reminder/task by conversational reference; DMDO asks for a valid target rather
than silently substituting an older selected record. Independent proposals stay
separate. This is a staged local workflow, not an automatic multi-record commit.

## Evidence classification

Unit/controller tests use temporary stores and controlled clocks/model replies.
They do not establish real language quality. Ordinary Electron tests include
controlled M2 fixtures; those are not new live desktop-control passes.
M3 forms/workflows/backup exercise actual Electron and Python. File chooser paths
are controlled; no fixture directly approves a database action. Matching actual
approval buttons and the scoped native Restore confirmation are exercised under
the user's explicit M3 delegation, not described as manually clicked by the user.
The separate installed-model test performs real interpretation and persistence.

Earlier failing runs remain in ignored `artifacts/ui-review/M3/`. In particular,
`final-live-03` selected calendar.search instead of availability; the capability
instructions now distinguish the operations. `final-live-04` passed its then-current
assertions, but manual result inspection found the seven-day default for a one-day
request. The backend range default and stronger output assertions now cover that
failure. No old result was edited to look successful.

`final-regression-03` had 26 ordinary Electron passes, 3 skips and one Restore
focus guard failure before approval. The test had not verified that its main
window was foreground before opening the native modal. The harness now verifies
that precondition, and still aborts on modal focus loss. `restore-focus-preflight`
passed the actual native restoration. The failed full run remains separate from
the later clean complete run; no production permission check was weakened.

## Visual self-review

Actual screenshots were opened with the image viewer: Profile; Contacts empty,
detail and merge; Calendar Month/Week/Agenda and occurrence editor; Tasks;
Reminders; Home Today; local import previews; native restore. Normal 1440x920 and
small 1366x768 outer windows, dark/light, in-app 125% enlargement and reduced motion
were checked. Native client dimensions are recorded in each forms result.
Keyboard focus, Enter/Escape dialogs and the command palette were exercised.
No blocking clipping or inaccessible primary controls remained in inspected views.
Long drawers scroll; imported technical fields remain verbose but inspectable.
Self-review is not independent human approval or accessibility certification.
Physical DPI variants, multiple monitors and GPU/combined-model resource use were
not measured. Event-driven screenshots do not establish frame rate.

## Scope and operating limits

Schema 4 is additive; old record IDs/relationships and existing DMDO stores remain.
Profile optional-setting recovery preserves valid fields and reports the issue.
The six pinned Python parser/timezone dependencies and licences are documented in
PERSONAL_CORE.md and requirements-personal.txt; no cloud/model dependency added.

Reminder history is persisted before UI delivery, so a crash can leave a history
entry without its popup. Restart catches up in a bounded summary; restore suppresses
old overdue work. No off-PC alerts, always-on service or exactly-once claim.
Common recurrence is supported; advanced series splitting and optional drag/resize
are not advertised. Unsupported interchange is reported; arbitrary extensions do
not have a lossless round-trip guarantee. Inputs/queries/exports are bounded.

Local model interpretation can still need clarification. The demonstrated workflows
are evidence for these fixtures, not universal language reliability. Read-only
Studio Output, no connected LSP/debugger, Qt style warnings, clean-machine packaging
and broader provider/performance validation remain documented release limitations.
Mail/SMTP/IMAP/vault expansion remain M4. Qt and the default launcher are preserved.

## Opening the features

In the built Electron application use All Spaces or Ctrl+Shift+P, then Profile,
Contacts, Calendar, Tasks or Reminders. Calendar Month/Week/Agenda controls and
New Event are on Calendar; personal task scheduling is on Tasks. Home shows real
Today data; Projects expose stable native links. Natural requests work from the
existing Home, Chat and Agent composers. No account registration is needed.
For repository development, the existing desktop `npm run build` and `npm start`
commands use the project toolchain; do not run Qt and Electron as simultaneous
writers against the same profile.

No real personal records, private accounts, credentials or external communications
were accessed or changed. Synthetic evidence/profiles stay local and out of Git.
Test app/backend processes are closed by the harness. No installer published,
default launcher changed, Qt removed, release tag created or M4 started.
