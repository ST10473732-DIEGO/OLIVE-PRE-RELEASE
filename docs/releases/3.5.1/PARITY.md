# OLIVE 3.5.1 - current identity

OLIVE was formerly named DMDO. M3 remains complete; M4 Mail action mappings are
in [M4_PARITY.md](M4_PARITY.md), with classified results in
[M4_COMPLETION.md](M4_COMPLETION.md). All 125 original M2 mappings remain below.
No existing feature or security gate is removed. Earlier checkpoint notices are
historical; current identity compatibility is in [the rebrand map](../../architecture/legacy-dmdo-compatibility.md).

# Action parity ledger

M3 implementation and internal acceptance complete. M2 remains accepted; Mail/transport remain M4. No release tag, Qt removal or default-launcher switch. See [M3_COMPLETION.md](M3_COMPLETION.md). Earlier checkpoint notices below remain historical.

## M3 native action ledger

These are new native actions, not replacements for the 125 original M2 mappings. Python dispatch is `olive/personal/controller.py`; persistence and validation remain in `service.py`, `store.py`, `calendar.py`, `reminders.py` and `interchange.py`. All calls use the active profile and existing permission/confirmation services. Evidence classification and specific live actions are in [M3_COMPLETION.md](M3_COMPLETION.md). A listed endpoint alone is not live evidence.

| Action | Electron access / language | Permission | State and evidence |
| --- | --- | --- | --- |
| `calendar.calendars` | Calendar views/editor; same registered backend capability for applicable natural intent | `calendar.read` | Bounded read; no mutation; domain tests and A-L acceptance map |
| `calendar.create` | Calendar views/editor; same registered backend capability for applicable natural intent | `calendar.write` | Validated local mutation; record revision where applicable; changes published to shared routes; domain tests and A-L acceptance map |
| `calendar.delete` | Calendar views/editor; same registered backend capability for applicable natural intent | `calendar.delete` | Validated local mutation; record revision where applicable; changes published to shared routes; consequential approval remains required; domain tests and A-L acceptance map |
| `calendar.delete_calendar` | Calendar views/editor; same registered backend capability for applicable natural intent | `calendar.delete` | Validated local mutation; record revision where applicable; changes published to shared routes; consequential approval remains required; domain tests and A-L acceptance map |
| `calendar.delete_occurrence` | Calendar views/editor; same registered backend capability for applicable natural intent | `calendar.delete` | Validated local mutation; record revision where applicable; changes published to shared routes; consequential approval remains required; domain tests and A-L acceptance map |
| `calendar.free_busy` | Calendar views/editor; same registered backend capability for applicable natural intent | `calendar.read` | Bounded read; no mutation; domain tests and A-L acceptance map |
| `calendar.get` | Calendar views/editor; same registered backend capability for applicable natural intent | `calendar.read` | Bounded read; no mutation; domain tests and A-L acceptance map |
| `calendar.range` | Calendar views/editor; same registered backend capability for applicable natural intent | `calendar.read` | Bounded read; no mutation; domain tests and A-L acceptance map |
| `calendar.save_calendar` | Calendar views/editor; same registered backend capability for applicable natural intent | `calendar.write` | Validated local mutation; record revision where applicable; changes published to shared routes; domain tests and A-L acceptance map |
| `calendar.search` | Calendar views/editor; same registered backend capability for applicable natural intent | `calendar.read` | Bounded read; no mutation; domain tests and A-L acceptance map |
| `calendar.update` | Calendar views/editor; same registered backend capability for applicable natural intent | `calendar.write` | Validated local mutation; record revision where applicable; changes published to shared routes; domain tests and A-L acceptance map |
| `contacts.create` | Contacts list/detail/merge; same registered backend capability for applicable natural intent | `contacts.write` | Validated local mutation; record revision where applicable; changes published to shared routes; domain tests and A-L acceptance map |
| `contacts.delete` | Contacts list/detail/merge; same registered backend capability for applicable natural intent | `contacts.delete` | Validated local mutation; record revision where applicable; changes published to shared routes; consequential approval remains required; domain tests and A-L acceptance map |
| `contacts.duplicates` | Contacts list/detail/merge; same registered backend capability for applicable natural intent | `contacts.read` | Bounded read; no mutation; domain tests and A-L acceptance map |
| `contacts.get` | Contacts list/detail/merge; same registered backend capability for applicable natural intent | `contacts.read` | Bounded read; no mutation; domain tests and A-L acceptance map |
| `contacts.merge` | Contacts list/detail/merge; same registered backend capability for applicable natural intent | `contacts.merge` | Validated local mutation; record revision where applicable; changes published to shared routes; consequential approval remains required; domain tests and A-L acceptance map |
| `contacts.merge_preview` | Contacts list/detail/merge; same registered backend capability for applicable natural intent | `contacts.read` | Bounded read; no mutation; domain tests and A-L acceptance map |
| `contacts.resolve` | Contacts list/detail/merge; same registered backend capability for applicable natural intent | `contacts.read` | Bounded read; no mutation; domain tests and A-L acceptance map |
| `contacts.search` | Contacts list/detail/merge; same registered backend capability for applicable natural intent | `contacts.read` | Bounded read; no mutation; domain tests and A-L acceptance map |
| `contacts.update` | Contacts list/detail/merge; same registered backend capability for applicable natural intent | `contacts.write` | Validated local mutation; record revision where applicable; changes published to shared routes; domain tests and A-L acceptance map |
| `personal.export` | Interchange / Home Today / Chat proposal review; same registered backend capability for applicable natural intent | `personal.export plus applicable Contacts/Calendar scope; file access only via native chooser` | Validated local mutation; record revision where applicable; changes published to shared routes; domain tests and A-L acceptance map |
| `personal.import_cancel` | Interchange / Home Today / Chat proposal review; same registered backend capability for applicable natural intent | `personal.read plus applicable Contacts/Calendar scope; file access only via native chooser` | Immutable preview and source fingerprint; explicit choices; atomic commit or cancellation; domain tests and A-L acceptance map |
| `personal.import_commit` | Interchange / Home Today / Chat proposal review; same registered backend capability for applicable natural intent | `personal.import plus applicable Contacts/Calendar scope; file access only via native chooser` | Immutable preview and source fingerprint; explicit choices; atomic commit or cancellation; domain tests and A-L acceptance map |
| `personal.import_preview` | Interchange / Home Today / Chat proposal review; same registered backend capability for applicable natural intent | `personal.import plus applicable Contacts/Calendar scope; file access only via native chooser` | Immutable preview and source fingerprint; explicit choices; atomic commit or cancellation; domain tests and A-L acceptance map |
| `personal.review` | Interchange / Home Today / Chat proposal review; same registered backend capability for applicable natural intent | `personal.write` | Exact proposal ID/revision; shared orchestrator commit/cancel and actual approval; domain tests and A-L acceptance map |
| `personal.today` | Interchange / Home Today / Chat proposal review; same registered backend capability for applicable natural intent | `personal.read` | Bounded read; no mutation; domain tests and A-L acceptance map |
| `profile.avatar` | Profile; same registered backend capability for applicable natural intent | `profile.write` | Validated local mutation; record revision where applicable; changes published to shared routes; domain tests and A-L acceptance map |
| `profile.get` | Profile; same registered backend capability for applicable natural intent | `profile.read` | Bounded read; no mutation; domain tests and A-L acceptance map |
| `profile.update` | Profile; same registered backend capability for applicable natural intent | `profile.write` | Validated local mutation; record revision where applicable; changes published to shared routes; domain tests and A-L acceptance map |
| `reminders.create` | Reminders history/schedule; same registered backend capability for applicable natural intent | `reminders.write` | Validated local mutation; record revision where applicable; changes published to shared routes; domain tests and A-L acceptance map |
| `reminders.delete` | Reminders history/schedule; same registered backend capability for applicable natural intent | `reminders.delete` | Validated local mutation; record revision where applicable; changes published to shared routes; consequential approval remains required; domain tests and A-L acceptance map |
| `reminders.dismiss` | Reminders history/schedule; same registered backend capability for applicable natural intent | `reminders.write` | Validated local mutation; record revision where applicable; changes published to shared routes; domain tests and A-L acceptance map |
| `reminders.get` | Reminders history/schedule; same registered backend capability for applicable natural intent | `reminders.read` | Bounded read; no mutation; domain tests and A-L acceptance map |
| `reminders.history` | Reminders history/schedule; same registered backend capability for applicable natural intent | `reminders.read` | Bounded read; no mutation; domain tests and A-L acceptance map |
| `reminders.search` | Reminders history/schedule; same registered backend capability for applicable natural intent | `reminders.read` | Bounded read; no mutation; domain tests and A-L acceptance map |
| `reminders.snooze` | Reminders history/schedule; same registered backend capability for applicable natural intent | `reminders.write` | Validated local mutation; record revision where applicable; changes published to shared routes; domain tests and A-L acceptance map |
| `reminders.update` | Reminders history/schedule; same registered backend capability for applicable natural intent | `reminders.write` | Validated local mutation; record revision where applicable; changes published to shared routes; domain tests and A-L acceptance map |
| `tasks.complete` | Tasks list/editor/scheduling; same registered backend capability for applicable natural intent | `tasks.write` | Validated local mutation; record revision where applicable; changes published to shared routes; domain tests and A-L acceptance map |
| `tasks.create` | Tasks list/editor/scheduling; same registered backend capability for applicable natural intent | `tasks.write` | Validated local mutation; record revision where applicable; changes published to shared routes; domain tests and A-L acceptance map |
| `tasks.delete` | Tasks list/editor/scheduling; same registered backend capability for applicable natural intent | `tasks.delete` | Validated local mutation; record revision where applicable; changes published to shared routes; consequential approval remains required; domain tests and A-L acceptance map |
| `tasks.get` | Tasks list/editor/scheduling; same registered backend capability for applicable natural intent | `tasks.read` | Bounded read; no mutation; domain tests and A-L acceptance map |
| `tasks.reopen` | Tasks list/editor/scheduling; same registered backend capability for applicable natural intent | `tasks.write` | Validated local mutation; record revision where applicable; changes published to shared routes; domain tests and A-L acceptance map |
| `tasks.schedule` | Tasks list/editor/scheduling; same registered backend capability for applicable natural intent | `tasks.write` | Validated local mutation; record revision where applicable; changes published to shared routes; domain tests and A-L acceptance map |
| `tasks.search` | Tasks list/editor/scheduling; same registered backend capability for applicable natural intent | `tasks.read` | Bounded read; no mutation; domain tests and A-L acceptance map |
| `tasks.update` | Tasks list/editor/scheduling; same registered backend capability for applicable natural intent | `tasks.write` | Validated local mutation; record revision where applicable; changes published to shared routes; domain tests and A-L acceptance map |

Narrow owned-launch corrections are implemented; the original desktop attempt remains blocked evidence. Target-only attachment and guarded child identity now have automated coverage. Live target interaction awaits new user initiation; see [M2_OWNED_LAUNCH.md](M2_OWNED_LAUNCH.md). No M3 or release approval.

M2 close-out visual corrections at cab8b76 are accepted. Final functional checks remain separate; see [M2_FINAL_CHECKS.md](M2_FINAL_CHECKS.md). Desktop live acceptance awaits explicit user initiation. No M3 or release approval.

M2 visual direction is accepted for continuation; functional sign-off is pending the focused [M2 close-out](M2_CLOSEOUT.md). The original action mappings and historical evidence below remain intact. No M3 interfaces or release tag.

> **M2 review checkpoint:** Implementation `b3554c3` is submitted for M2 user review. Fresh results, actual Electron captures, per-feature parity and remaining limitations are in [M2_REVIEW.md](M2_REVIEW.md). Stop before new Personal Core interfaces; no release tag, Qt removal or default switch. Earlier checkpoint notices below are historical.


> **M2 continuation:** The user explicitly approved corrected M1 at `d355f94` as the visual/interaction baseline and authorised M2 existing-feature migration. This supersedes the M1-awaiting-review notices below only. Full release and M3 interfaces are not approved. See [M2_PLAN.md](M2_PLAN.md), [M2_PARITY.md](M2_PARITY.md) and [M2_STATUS.md](M2_STATUS.md). All original requirement IDs remain in force.


> **Current M1 correction checkpoint, 10 September 2026:** The user recommended the Electron direction and requested focused corrections from `f4b107b`. See [M1_CORRECTIONS.md](M1_CORRECTIONS.md) for current implementation, stable M1C-01–09 obligations, fresh evidence and limitations. Updated M1 awaits user review; no M2/M3 work, Qt removal, launcher switch or release tag is authorised by this checkpoint. Historical evidence below remains historical.


> **Recovery checkpoint, 10 September 2026:** The material below is recovered
> historical documentation. Its test totals, security audit and approval claims
> are not fresh acceptance. See [RECOVERY_REPORT.md](RECOVERY_REPORT.md) for the
> current verified state. The latest brief requires a new visual-review stop.

All entries below retain their working Qt location. Electron M1 implements the subset recorded after this table; other actions remain pending. Native domains have no completed Qt implementation to migrate.

| Feature | Actions to preserve | Electron milestone / status |
| --- | --- | --- |
| Chat | New/select/search/rename/delete; streaming/stop/regenerate/branches/copy; model/project selection; attachments/remove; sources; draft persistence | M1, pending |
| Studio | Open/create workspace; explorer/tabs; save/save-all/hash conflicts; selections/dirty buffers; search/replace; diagnostics; diff/checkpoints/rollback; run/stop/restart/tests/output; Git; assistant | M1 core, M2 full action parity; pending |
| Home | Same orchestrator; clarifications/approvals/cancel/results; exact Continue context; All Spaces; preferences/context clearing | M1, pending |
| Agent | Create/history/inspect; pause/cancel/resume; timeline; changed files/validation; permissions | M2, pending |
| Desktop Control | Objective; observations; focus/takeover; emergency stop; approval; UIA/provider/manual details | M2, pending |
| Research | Start/depth/history/cancel; findings/sources/provenance; website learning; project save | M2, pending |
| Projects | Create/search/open; workspace/files/chats/tasks/research/knowledge relationships | M2, pending |
| Knowledge | Add/search/filter; health/index status; re-index/relink/remove; jobs/retrieval inspection | M2, pending |
| Memory | CRUD/search/filter/export; suggestion approval/rejection; provenance | M2, pending |
| Settings | Every current validated setting; permissions; diagnostics copy/export; backups/export/restore; searchable categories | M2/M4, pending |
| Personal Core | Identity; Contacts; Calendar; Tasks/Reminders; Mail/Connections; domain CRUD and all imports/exports/NL workflows | M3, not implemented |

Individual carried obligations in REQUIREMENTS.md remain authoritative; this compact action inventory is not a substitute for their acceptance evidence. Qt-only tests stay until equivalent frontend checks exist. Default launcher stays Qt.

## M1 action locations and evidence

| Action | Electron location | Evidence / remaining gap |
| --- | --- | --- |
| Enter/Home/All Spaces/search/pin | Welcome, rail, Home cards, All Spaces search/pin control | Live local navigation; ordering follows pin sequence, dedicated reorder control remains |
| Natural request and stream/stop | Home and Chat composer | Actual qwen3:8b stream/cancel; same Python orchestrator |
| Chat new/select/search/model/regenerate/copy/draft | Conversation sidebar, header, message actions, composer | Core stream/draft flow live tested; remaining individual actions need broader parity acceptance |
| Workspace/open/file tabs/edit/save | Studio empty state, explorer, tabs, toolbar and Ctrl+S | Real approved fixture save with expected hash |
| Dirty editor/view retention | Studio model cache | Navigate away/back demonstrated; Python retains buffers for refresh recovery, broader multi-file/restart matrix pending |
| Conflict comparison/rebase | Studio Compare; side-by-side Monaco panel | Stale save blocked and versions preserved; rebase hash guard unit-tested |
| Test/Run/Stop/Restart/output | Studio toolbar and read-only xterm output | Compile/unit test/Run live; Stop/Restart routes use existing services, broader UI coverage pending |
| Approval/cancel | Human-readable dialog plus expandable arguments | Actual local approval path exercised; generic communication-specific rich previews still need M2/M3 migration |
| Emergency stop | Activity centre; Ctrl+Alt+Escape main fallback | Boundary implemented; live physical desktop-loss scenario not tested |
| Appearance/palette | Rail theme control, activity sheet, Ctrl+Shift+P | Light/reduced motion/keyboard tested; full Settings and creation commands pending |

## User-approved M1 direction and Studio revision

See [USER_REVISION.md](USER_REVISION.md): direct Studio consent, Java/local libraries and named project folders are implemented and live-local tested. 536 Python, 49 Qt, five frontend and five Electron tests pass. Broader natural-language autonomy, supported Discord delivery and full IDE/package workflows remain open. No release acceptance or final visual approval is inferred.

## Focused review correction parity

Available Electron prototypes: Home/Welcome/All Spaces, Chat, Studio; connection management remains its existing limited interface. Temporary Qt workspaces: Agent, Research, Desktop Control, Projects, Knowledge, Memory, Settings. Not implemented native spaces: Contacts, Calendar, Tasks, Mail (and unfinished Identity/Reminders obligations). Planned cards are disabled; Qt cards explain the fallback rather than pretending to open a migrated workspace.

M1C-02/03 now cover retained output after save/navigation, hierarchical file navigation and validation Stop. M1C-06/07 cover readable backend approvals, exact argument binding and connected local cancellation evidence. These do not close full Studio/Agent/domain parity. All applicable original requirement IDs and unfinished native requirements are retained.
