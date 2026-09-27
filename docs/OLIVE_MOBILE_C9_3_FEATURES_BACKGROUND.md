# OLIVE Mobile C9.3 — companion features and background continuation

**Status: implementation delivered; real-device acceptance remains partial. The complete iPhone + CachyOS milestone gate has NOT passed.**

Native Today/selected Chat sync, Files, Remote Studio, capability status and
continued-processing coordination are implemented and installed on the physical
iPhone. Unit/UI/build checks do not establish real background execution. The
normal app has been launched with its existing production pairing for acceptance.
No simulator or Mac-hosted desktop is being substituted for CachyOS acceptance.

## Repository and machine reconciliation

- `BASELINE_HEAD`: `cf7fb0d5c72e5793927bfcddf337539be160633d`.
- `BASELINE_BRANCH`: `feature/olive-mobile-c9`.
- `WORKTREE_STATUS`: clean at baseline.
- `BRANCH`: `feature/olive-mobile-c9-3`, created from the Mac baseline to separate
  the new milestone from the completed C9.2 history. The Mac is canonical for C9.3.
- Local `origin/feature/olive-mobile-c9` matched the baseline; no fresh fetch or
  push was performed. No reset, stash, history rewrite, merge, tag or release.
- Deployed C9.2 desktop baseline: `698b002e13ba76aef8bcd1a391b33280764e1bad`.
  The owner confirmed its clean worktree and created
  `recovery/olive-mobile-c9-2-698b002`. Creating this branch printed nothing.
- All 24 affected desktop files from the retained C9.2 deployment patches were
  compared by content with the Mac and reconstructed desktop tree. The patches'
  digests matched C9.2 evidence. The owner reported the corrected desktop diff
  projection digest `da7d5a992fa3ad5b03c09c1d91162a5ce2863d15`. Commit IDs alone
  were not treated as proof of equivalent source.
- `FINAL_HEAD`: pending milestone acceptance. The current documentation checkpoint
  is resolvable with `git log -1 --format=%H -- docs/OLIVE_MOBILE_C9_3_FEATURES_BACKGROUND.md`.
- Latest implementation/test checkpoint: `347d0eb` (final validation below).

Local `COMMITS` to date:

| Commit | Change |
| --- | --- |
| `3c2edb5` | Background coordinator, protected persistence and interruption state |
| `2f49510` | C5/C6/C8 codecs and Python/Swift vectors |
| `a99886b` | Optional desktop read-only capability status |
| `d6da31a` | Today, selected Chat, signed sync and conflicts |
| `f72da9a` | C6 picker, snapshots, quarantine, receipts and explicit export |
| `a5cd798` | Scoped Studio editor and build/test/run/cancel |
| `5de9793` | Companion protocol and native navigation tests |
| `891c866` | Late completion fencing, metadata, conflict review and Chat ordering |
| `fc21ec0` | Durable Today drafts and actual per-workspace Studio permission labels |
| `e313830` | Unique system task IDs, stale callback fencing and iOS27 asynchronous submission |
| `0cc209f` | Stored-artifact C6 rehash, exclusive publication and exact offer checks |
| `dc8ec93` | Send C6 cancellation before releasing session; fence late admission; test interrupted-transfer recovery |
| `d181864` | Persist typed background failure diagnostics and clarify explicit-only draft retry |
| `d83e1b1` | Retain unresolved sync conflict warnings and expose both versions from the Today editor |
| `954fbe1` | Native calendar agenda, durable remote conflict markers, ordered Chat tombstones and protected sync recovery |
| `7f1ee4b` | Fence Studio cancellation/Ask retries and display authenticated revocation |
| `d84cefc` | Clean temporary app-owned export copies on launch |
| `347d0eb` | Calendar Python/Swift vectors, recovery/tombstone tests and verified-file/Studio UI fixtures |

## Background execution

`BackgroundWorkCoordinator` uses availability-gated
`BGContinuedProcessingTaskRequest` / `BGContinuedProcessingTask` on iOS 26+.
Each explicit user action registers one unique fully composed identifier under
the permitted bundle-prefixed wildcard. Grant/expiration callbacks bind to that
identifier and operation, preventing an old callback from affecting new work.
iOS27 uses `submitTaskRequest(_:)` asynchronously off the main actor to receive
submission errors; iOS26 uses the availability-gated original submission API. Requests start only with an
explicit Chat request, reviewed outgoing file, accepted incoming file, or Studio
build/test/run. Submission uses `.fail`; it never queues a later effect.
The iOS deployment target remains 17.

The system task's `Progress` and title/subtitle provide Apple's continued-task
visible progress. File units reflect verified receipt byte counts; incoming bytes
are staged until the final size/hash check. Unknown-length Chat and Studio work
stay indeterminate. Labels omit prompt, response, workspace and filename content.
No custom ActivityKit extension or invented percentage is used. Actual system UI
appearance is owner-confirmed on iOS 27 for both C6 directions, and system Live Activity cancellation propagated to the desktop in the test below.

Reference: [Apple: performing long-running tasks on iOS and iPadOS](https://developer.apple.com/documentation/backgroundtasks/performing-long-running-tasks-on-ios-and-ipados).
The installed Xcode 27 SDK declarations were also inspected.

If submission is unavailable, denied or not yet granted when backgrounding,
short `beginBackgroundTask` cleanup cancels/interrupts active work. This is also
the iOS 17–25 fallback. There is no real-time BGProcessing/BGAppRefresh promise,
HTTP carrier, URLSession replacement, idle keepalive, audio/location/VoIP/VPN mode,
APNs dependency, or claim that a custom TCP socket remains alive indefinitely.

With a granted active task, Bonjour scanning stops and only the required existing
Connect session remains. Without work, the session closes for suspension.
Foreground return restarts discovery and exact-pin connection as needed. Lifecycle
states distinguish foreground connection/connecting, active background work,
expected suspension, offline, reconnecting, revoked and unpaired. Explicit
authenticated C7/C8 revocation errors now set Revoked for the exact peer and stop
session retries. Network EOF never implies revocation. This observed revocation
flag is session-local; after relaunch the normal exact-pin handshake determines
availability again, without replaying work or changing stored trust.

A bounded protected journal stores operation ID, capability, peer, label,
protocol ID, request digest, start time, verified progress, state and required
file/Studio scope metadata. Optional v1 fields now retain an allowlisted typed
failure and finish timestamp when known; older records decode with these absent.
Settings → Advanced connection diagnostics shows the latest recorded result. No
provider text, Chat content or new authority is stored in this journal. Late updates are bound
to the operation ID. Cancellation persists its state before asynchronous cleanup;
new work is blocked while cleanup runs. Returning to foreground during cleanup
cannot mark the new foreground state suspended.

Force quit and system termination cannot be assumed to deliver a final callback.
On relaunch, running records become interrupted; no message, upload, download,
save, sync mutation or Studio operation is automatically replayed. C6 has durable
receipt querying for an explicit check. Current C7/C8 work is channel-owned;
C8 disconnect or missed polling cancels it, and status cannot migrate to a new
channel. All operation records therefore set independent desktop continuation
false. No successful result is inferred from a saved running state.

Opt-in local completion notifications use generic labels. Permission is requested
only from the Settings notification control. Synced-reminder scheduling is not
implemented or claimed. No hidden reasoning or unrelated desktop context is saved.

## C5: Today and selected Chat

Swift maps the existing `olive-sync/1` signed envelopes, native payloads,
Ed25519 provenance, revision vectors, tombstones, revision receipts, cursors,
acknowledgements and conflicts. Batches retain the existing eight-record and
payload bounds. Cursors and applied records commit atomically. Invalid signatures,
changed revision bytes, missing dependencies and concurrent edits are rejected or
held as conflicts; there is no destructive automatic merge.

Today exposes native tasks, calendars/events and reminders, with create/edit,
task completion and tombstone deletion. Reminders retain the native task/event
relationship; task completion remains on the task. Records stay read-only offline.
Online authoring creates a pending signed revision; sharing requires explicit
Sync. There is no automatic mutation replay after reconnect. The editor stores bounded protected drafts separately from committed records,
including the original revision. Draft restoration never commits or sends an edit;
a changed original revision is refused on Save.

Sync is initiated on the phone and exchanges records in both directions through
existing C5. Unsolicited desktop-initiated C5 requests are denied; pairing does not
grant inbound sync authority. Existing desktop Off/Ask/Allow is authoritative.
Ask retries retain the same request envelope while awaiting desktop confirmation.

Selected Chat uses the sender's explicit peer-scoped selection. Unselected local
conversations are never exported. Conversation/message IDs and immutable message
predecessors survive revisions; tombstoned predecessors do not hide later messages.
Completed C7 turns are stored with stable IDs and imported once into a deliberately
selected mobile conversation. C7 context still includes only mobile-owned turns,
not private desktop context. Conflict review shows incoming/local field values and
binds resolution to the local revision reviewed by the user. Remote-only conflict
receipts now persist across relaunch and empty exchanges, clearing only on a
strictly dominating revision. Today labels pending revisions and conflicts;
an editor refresh adopts a new synced revision only when it has no unsaved edit.
Explicit shared-conversation deletion signs message tombstones before the parent
conversation in one atomic local commit; sharing still needs Sync Chat. Imported
C7 turn IDs remain recorded, so later selection cannot resurrect deleted turns.

Today now includes a native day agenda over stored signed records: due/overdue
tasks, calendar instances and linked reminder times. It does not create flattened
sync records. The bounded Swift calendar engine covers the existing C5 daily,
weekly, monthly and yearly rule keys, ordinal weekdays, counts/until, local time
transitions, moved/cancelled exceptions and half-open intervals. It preserves the
desktop's invalid-local-time/count behavior and task reminder default of 09:00 in
the task timezone. Python's production validator/expander generates 27 valid and
7 rejected canonical cases; Swift checks validation and exact occurrence fields.
Physical unit tests also cover DST, invalid exceptions and reminder suppression
for completed/cancelled targets. Agenda work runs off the main actor and honours
cancellation; expansion is bounded and reports failure without changing records.
Advanced recurrence editing stays on the desktop; these vectors establish their
covered cases, not every possible dateutil input or historical timezone rule.

Contact/project relationships outside this milestone remain held as missing
dependencies, rather than dropping those fields or claiming nonexistent records.
Real selected/unselected, duplicate, Chat tombstone and remaining domain conflict
acceptance is still pending.

## C6: Files

The system document picker supplies outgoing authority. A regular-file check and
security-scoped access produce an immutable protected app-owned snapshot; scope
is released promptly. The user reviews it and explicitly sends to the paired
computer. SHA-256 metadata, bounded raw chunks and exact received offsets use the
existing C6 carrier on authenticated C3. Success requires the final C6 receipt.
Late admission/chunk responses cannot restart cancelled work. Cancellation first
fences producers and discards partial local bytes, retains the session for the
exact C6 cancel exchange, then releases background resources. If the computer's
immutable receipt proves the upload completed before cancellation arrived, the
phone records that verified completion rather than falsely claiming it was undone.

Incoming offers require explicit foreground acceptance. Bytes enter protected
app-owned staging, then verified size/SHA-256 and a durable receipt publish the
quarantined file. The completion response is written before releasing the
background session. The UI shows **Ready to Save**. Only explicit Save/Export
opens the system document exporter; it does not silently write to Files/iCloud.
The export copy retains the reviewed safe filename.

Existing bounds remain: **64 MiB per file**, 64 KiB chunks, 4 KiB metadata, bounded
queues/storage and immutable metadata. The requested approximately 100 MB test is
outside C6's limit; the large-transfer acceptance must use at most 64 MiB.
C6 has no offset resume and no existing HTTPS carrier. Interrupted transfers
require a fresh explicit picker/send; no unsafe offset resume or parallel mobile
file protocol was added. Explicit receipt checks reconcile uncertain outgoing
completion without sending data again. Abandoned app-owned UUID staging files are
cleaned on launch; unrelated selected/exported user files are never deleted.
Temporary copies inside the dedicated app-owned Exports folder are now cleared
on launch and before another export. Cleanup skips symlinks/directories, retains
verified inbox bytes and does not access the user's chosen Files destination.

Off/Allow, invalid hash, oversize, cancel, collision, quarantine/export, revocation,
disconnection, both transfer directions, >=60 seconds of background use, and
force-quit behavior remain real-device acceptance requirements.

## C8: Remote Studio

Native navigation exposes shared workspaces, bounded tree/read, a monospace editor,
revision-safe save, build/test/run, bounded results and cancel. Save binds the
shared workspace, share revision, relative path and original content hash;
returned content hashes are verified. Stale edits remain drafts and are not
blindly overwritten. Protected drafts are bounded and tied to peer/workspace/path.

Jobs persist their exact request IDs and scope before starting, poll the original
channel at bounded intervals, and cancel according to C8. Reconnect does not
restart jobs or pretend to query an operation on a replacement channel. The
existing 15-second missed-poll and disconnect behavior remains authoritative.
UI cancellation now sends run_cancel for the exact request ID immediately, fences
subsequent Ask retries, and prevents a late cancellation failure from closing a
replacement job's session. If the original session ends without a terminal
receipt, the result stays unconfirmed/interrupted, not fabricated as cancelled.

No mobile terminal, PTY, debugger, package installation, arbitrary command,
unrestricted filesystem or Owner Mode authority exists. Shared/unshared, read,
save/stale save, all job operations and active background behavior still require
real CachyOS + iPhone acceptance.

## Architecture, navigation, storage and permissions

Home / Chat / Devices and separate Settings remain. Home cards open Today,
selected Chat, Files and Studio. Home displays actual active operation progress;
no fake activity counts or records are inserted. Devices consumes an optional
read-only capability query over the existing C7 envelope and displays real C5/C6
permission/support state; Studio permissions remain per shared workspace.
Older desktops retain the old status response shape. An unsupported capability
probe results in one exact-pin reconnect without the optional probe and an unknown
status display; this is not a protocol downgrade or a permission grant.

Protected Codable repositories use schema version 1, atomic replacement, explicit
size/count bounds and backup exclusion. Complete-until-first-user-authentication
protection permits user-started background work after unlock. Keys remain in
Keychain, outside ordinary stores. Unreadable/unknown-version files are preserved
and writes fail closed. Optional operation scope/message-predecessor fields allow
additive v1 decoding; corruption recovery does not erase or silently overwrite data.
Today offers explicit recovery only when its sync store cannot be opened. It
preserves the exact original bytes in protected, backup-excluded recovery storage
before atomically creating a fresh empty store. Up to four recovery archives are
retained; existing copies are never evicted. Oversized/nonregular sources fail
closed. The UI explains unsynced edits remain in the preserved file; desktop data
returns only through explicit domain sync. Drafts, receipts and Keychain identity
are not reset. Recovery does not authorize replay of an uncertain operation.

The app/Core boundary remains: native views/models orchestrate existing Connect
contracts; desktop inference, persistence, shared-workspace execution and capability
authority remain in their current services. Persistent listener ports, TLS 1.3,
exact certificate pins, two-sided pairing and durable trust were not weakened.
No firewall/trust mutation was made for C9.3.

## Validation evidence — 2026-09-27

Physical device reported by `devicectl`: **iPhone 15 Pro Max, iOS 27.0 (24A437)**.
Device identifiers, signing credentials and personal acceptance data are not
committed.

| Check | Observed result |
| --- | --- |
| `xcodebuild -list` | Passed with installed Xcode selected via `DEVELOPER_DIR` |
| Simulator SDK build-for-testing | Passed; no simulator runtime execution claimed |
| Generic iOS Release build | Passed |
| Signed physical build/install/test | Passed: 67 unit cases, 2 opt-in LAN skips, 0 failures; **65 passed** |
| Physical UI tests | Passed: 11 cases, 1 opt-in LAN skip, 0 failures; **10 passed** |
| Normal production-identity launch | `devicectl` normal launch succeeded after tests; observed C6 results below |
| Python ↔ Swift interop | Existing C2/C3/C7 vectors/TLS pairing plus new C5/C6/C8 vectors passed |
| Mac `python -m compileall -q .` | Passed |
| Mac full Python | 1,456 cases, 58 skipped, 2 failures + 2 errors; NOT green |
| Mac Connect | 254 cases; C8 descendant-reaping timeout remains; NOT all green |
| Mac desktop typecheck/unit/build | Passed; 101 tests across 20 files |
| Diff review | No personal fixture data, secrets, branding downgrade or unrelated data changes |

Mac failures match the C9.2 documented platform/environment categories: C8 owned
subprocess reap timeout, Linux readiness/non-ELF inspection, selected workspace
run outcome and detected Java toolchain expectation. No blanket Mac regression
pass is claimed. Using a canonical `/private/tmp` test directory removed additional
macOS `/var` vs `/private/var` alias failures from the first run.

Latest local evidence: `/tmp/olive-c93-device-tests-11.xcresult`,
`/tmp/olive-c93-device-tests-11.log`, `/tmp/olive-c93-simulator-completion-final.log`,
`/tmp/olive-c93-release-completion-final.log`, `/tmp/olive-c93-interop-completion-final.log`,
`/tmp/olive-c93-compile-completion.log`, `/tmp/olive-c93-python-completion-native.log`,
`/tmp/olive-c93-connect.log`, `/tmp/olive-c93-desktop-tests-2.log`.
These are local logs, not portable committed artifacts. Earlier physical failures
in strict decimal parsing and a Stop/background race were repaired before the
passing runs. Unit tests also cover version preservation, expired cleanup,
no-replay launch, stale progress fencing, immutable Chat order, tombstones,
signed conflict handling, durable uncommitted Today drafts, file bounds, Studio
hash rejection and private labels. The C6 follow-up adds a physical stored-byte
tamper/collision test. The latest full unit/UI run is `olive-c93-device-tests-11.xcresult`, including
the new conflict persistence, calendar, recovery, Chat tombstone, file cleanup and Studio cancellation tests. UI coverage includes verified quarantine/export and offline Studio conflict/actions. Simulator-SDK and Release
builds passed, and normal production-identity launch was restored. The recovery test
seeds a partial and a verified transfer, relaunches the store, and checks interrupted
state, partial cleanup, no replay and preservation of verified/unrelated files.
A sandboxed build attempt could not run Swift macro plugins; the same final build
passed with Xcode services available.

## Deployed CachyOS regression

The owner ran the guarded, desktop-only three-file patch on the preserved clean
C9.2 tree. The installer checked expected HEAD/recovery ref, SHA-256 and
`git apply --check`, then made one local commit. No push, firewall edit, trust
change or desktop redesign occurred.

- Exact deployed commit: **`fd63db203a56ab2c8f4d3b26d93a1d20363e3f5c`**.
- Patch SHA-256: `a31b053f51b926b49ee60348e7efface84e8ad465d624d50bccefd8fcaffa264`.
- Owner-reported fresh native results: **254 Connect tests passed**;
  **1,443 Python cases OK, 8 skipped**; typecheck passed;
  **101 frontend tests across 20 files passed**; production build passed.
- Final desktop worktree: **clean**.
- Literal `compileall -q .` failed on a vendored PySide6 Android
  `__init__.tmpl.py` in `.venv` containing Jinja placeholders. This is not OLIVE
  source; it was not edited. The owner subsequently reported `SOURCE_COMPILE_OK`
  with `.venv`, `node_modules` and `.git` excluded. `./run_olive.sh` rebuilt
  successfully; the normal application connection is the next live check.

Desktop code changes only add the optional authenticated read-only capabilities
operation and strict response tests. Existing status bytes and authority remain
compatible. The desktop's native suite does not include the new Mac-side mobile
fixture tests because only the minimal desktop patch was deployed.

## Live acceptance observations

The owner reports that the normally launched iPhone is **Connected** after the
CachyOS restart and that permission rows show Off/Ask/Allow rather than unknown
capability status. Individual permission values were not supplied; no broader
Off/Ask/Allow operation matrix is inferred from that report.

The owner completed the first 5 MiB desktop-to-phone transfer and explicitly
exported/saved the file to the phone. The app-owned receipt was read independently:
transfer `7d80c8a0-598a-45ff-b3a2-6c21c5dabc1b`, incoming, completed, 5,242,880
received bytes and the expected 5 MiB SHA-256 below. This foreground check ran on
the earlier `fc21ec0` build; subsequent C6 integrity changes are installed for
the return-transfer and background checks. Expected fixtures use repeated byte values 0...255:

| File | Bytes | SHA-256 |
| --- | --- | --- |
| `olive-c93-5MiB.bin` | 5,242,880 | `2e7cab6314e9614b6f2da12630661c3038e5592025f6534ba5823c3b340a1cb6` |
| `olive-c93-64MiB.bin` | 67,108,864 | `281e519df3077b557c6b03f5da83c4e8d397219259615dd7c3308f89cae8f2a6` |

The owner also reports sending the exported file back from iPhone to CachyOS
and explicitly saving the desktop copy. The phone's outgoing receipt
`0982bac0-21d8-46a5-840f-d090bd0b9377` independently records completed,
5,242,880 acknowledged bytes and the same expected SHA-256. The owner pasted
the matching `sha256sum` for the exported desktop copy, independently closing
the foreground round-trip integrity check.

Both 64 MiB C6 directions subsequently completed on the physical iPhone and real
CachyOS desktop, using mobile implementation `0cc209f`:

- Desktop → phone: the owner saw the Receiving file Live Activity while using
  another app/Home, returned and explicitly exported the file. Independently read
  receipt `bd80e735-c7af-489f-8b9c-9b989276f3d3` records completed, 67,108,864
  bytes and the expected hash. Journal start to receipt completion was about
  81.6 seconds; this is not a measurement of time spent outside OLIVE.
- Phone → desktop: the owner used Instagram for about 60 seconds and saw the
  Sending file activity. The saved desktop copy's owner-reported SHA-256 exactly
  matches the fixture. Independently read phone receipt
  `4d5c4bd1-f8a8-4e62-92a3-153f52e1a6ec` also records completed, 67,108,864
  acknowledged bytes and the expected hash.
- The owner noticed the desktop showing Offline around the outgoing transfer but
  could not recall whether bytes were still increasing or completion had already
  occurred. This observation remains open for a timed recheck. The implementation
  deliberately closes the connection after background work completes; that fact
  does not establish the timing of the reported label.

The next outgoing 64 MiB transfer was cancelled using mobile implementation
`dc8ec93`. The independently read phone receipt
`85966622-9a4a-46e6-9f68-23536397a863` records cancelled at 16,842,752
acknowledged bytes. The owner confirms that the desktop also cancelled, the phone
then appeared disconnected while the owner remained in another app, and reopening
OLIVE reconnected. This establishes cancellation propagation and the expected
post-cancellation release/reconnect behavior. The owner separately confirmed using
Stop/Cancel in the system Live Activity while remaining outside OLIVE. The earlier
ambiguous Offline observation is not retroactively treated as proven.

For the next outgoing 64 MiB transfer, the owner disabled iPhone Wi-Fi for about
40 seconds while bytes were transferring. The desktop reported Interrupted ·
partial data removed and a transfer timeout; the phone reported request timeout
and interrupted. The owner observed the Live Activity disappear about 3–5 seconds
after disabling Wi-Fi. After restoring Wi-Fi and reconnecting, the transfer did
not resume or restart. The independently read phone receipt
`8321b4bc-588a-47d9-8bc6-8f8c4fe93d96` records interrupted at 6,750,208
acknowledged bytes. This passes the tested outgoing network-loss/no-replay path;
the reported timings are owner estimates, not instrumented measurements. Desktop
partial removal is established here by its reported UI state, not filesystem
inspection. Force-quit behavior was tested separately below.

In the separate force-quit check, the owner swiped OLIVE away from the iPhone App
Switcher during another outgoing 64 MiB transfer. The system activity immediately
showed Task failed (owner observation), CachyOS showed the phone disconnected and
Interrupted · partial data removed, and the phone showed Interrupted on reopening.
The independently read receipt `cc812251-050b-4171-9ad2-94cbae7e328b` records
interrupted at 7,208,960 acknowledged bytes. The owner separately confirmed that
reopening OLIVE left the transfer Interrupted and did not restart it. This passes
the tested outgoing force-quit/relaunch/no-replay path. No continued execution
after force quit is claimed.

For the first C7 background Chat check, the owner requested the synthetic garden
response, observed the system loading activity followed by a completion tick, and
reported desktop disconnection after completion followed by reconnection on
returning to OLIVE. The independently read operation journal records
`bb53a1ee-b623-474d-8c66-efab1c52236b` (`models.remote`) completed with 7,471
verified answer bytes and no fabricated total; the journal contains zero running
operations. The owner subsequently confirmed the single completed response and
about 20 seconds spent in another app. This is a real completed C7 background run;
it is not evidence of 60 seconds away. The separate active-response Stop check is
recorded below.

A second explicit garden request (`14bdcbf6-c2c7-490d-a406-f57358e35bb2`)
stopped around item 115 after roughly 10–20 seconds, with an incomplete answer and
restored draft. The journal records interrupted with 8,623 answer bytes, not system
expiration. The owner confirmed the precise composer error was Response size
limit. C7 already limits requests to 2,048 output tokens, 64,000 bytes and 120
seconds; the 120-sentence test prompt can reach the token limit. This is the
observed C7 output-limit failure path, not proof of denied background execution.
The prompt remains a draft for explicit user action; no automatic resend is
performed. Bounds were not increased. Follow-up `d181864` preserves future typed
failure reasons/finish times, and the draft message explicitly says nothing was
resent. New physical tests cover old v1 decoding, persisted failure diagnosis,
late-completion fencing, retained partial output and exactly one start on failure.

During the requested system Chat Stop check, the owner reported that text stopped
growing and OLIVE showed Interrupted · connection closed. The independently read
journal has no running tasks; request `6f9a41a0-855d-4a3e-ae00-c47b67aed793`
ended after 744 received answer bytes via the continued-task expiration handler
(`expired`, `backgroundTaskExpired`). That callback also handles the system Stop
control, so this code alone cannot distinguish a person cancelling from an iOS
resource expiration. The owner subsequently confirmed using the system Live
Activity Stop control and that the active job ended on CachyOS. Together these
observations pass the tested system-initiated C7 cancellation/release path. The
phone intentionally uses an interruption label because the system callback does
not itself distinguish user cancellation from resource expiration.

The owner also reported an older activity still visible and clarified that it
says Task failed. This is a terminal failure display; no running operation remains
in OLIVE's journal. Apple's DTS explains that the system manages this UI
independently and cancelling scheduler requests does not remove already-failed
tasks: [BGContinuedProcessingTask failure behavior](https://developer.apple.com/forums/thread/808756).
The installed SDK exposes progress, title updates and completion, with no public
failed-activity dismissal method on BGContinuedProcessingTask. OLIVE does not
claim it can clear that system UI, and does not relabel a failed transfer successful
or publish invented progress to suppress it. The exact dismissal behavior on this
iOS27 device remains a UX observation to check.

The first real C5 Today Tasks check passed with Sync tasks set to Allow: the owner
created the synthetic task C93 phone task on iPhone, saved locally, requested Sync
tasks, and confirmed that the exact task appeared in desktop OLIVE Tasks. This is
owner-observed phone → CachyOS creation, not an inferred protocol-fixture result.
The owner then completed the bidirectional edit sequence: a desktop rename to
C93 desktop edit reached iPhone after explicit Sync tasks, followed by a phone
rename to C93 phone edit and Completed toggle. After Save locally and Sync tasks,
the desktop showed the final title and completed state. This verifies the tested
Tasks revisions and completion path under persistent Allow. In the concurrent-edit
check, the phone saved C93 conflict phone without syncing and the desktop saved
C93 conflict desktop from the shared revision. The owner initially saw Sync
complete on the phone and did not see both versions there. A read-only review of
desktop Devices → Sync → Review conflicts then showed task conflict / concurrent
edit with both distinct titles, while the phone retained C93 conflict phone.
Thus the real C5 conflict was preserved instead of overwriting the desktop; the
phone presentation was misleading. After the installed fix and requested resolution,
the owner confirmed the phone now displays the desktop title. Desktop conflict-list
clearance was not separately confirmed; no further questions were requested.
Tasks tombstone acceptance remains open.

The follow-up UI fix keeps a conflict warning when the current peer/domain still
has unresolved local conflicts, clears a stale editor save notice before showing
the sync result, and adds Review conflict inside the record editor. It changes no
wire format, signatures, authority or merge policy. A signed-record regression
covers conflict survival through duplicate exchange/relaunch and clearance only
by a revision descending from both edits. A separate offline UI fixture checks
both versions can be reviewed from the editor; it is isolated from production
trust/data and is not substituted for real-device sync acceptance.

The retained C6 maximum is 64 MiB, so a 100 MB acceptance file is prohibited by
the existing protocol. These results prove the tested supported background file
flows, cancellation/reconnect, outgoing network-loss/no-replay and observed
force-quit/relaunch/no-replay, not indefinite connectivity or other capabilities.

## Completion gate and limits

Still pending: selected Chat, remaining Today bidirectional changes and conflict
cases; C6 negative cases and the observed desktop presence timing; further Chat
interruption cases; shared Studio save/revision/jobs/cancel and background
behavior; remaining direction-specific failure cases, permission Off/Ask/Allow,
and C9.2 real-device regression.

The owner asked to stop the per-case question loop and finish implementation
without more prompts. Remaining implementation work was completed in the local
commits above; available build/unit/UI/interop/regression checks were run as one
autonomous batch. Unperformed real CachyOS + iPhone checks remain recorded here,
not converted to passes or silently deferred to declare C9.3 complete. Synthetic
UI fixtures establish rendering/error states only and never stand in for a real
peer, real sync or a real Studio job. No additional desktop code patch is needed
for this batch; deployed CachyOS remains at the validated commit above.
Reminder notification scheduling is optional and currently omitted.

C9.4 remains deferred: share extension, advanced notification polish, transfer
soak, second-device readiness, additional accessibility, final battery/performance
tuning and distribution preparation. C10 remains deferred: different-network
access. No cloud account, relay or APNs infrastructure has been introduced.


## Recommended source synchronization (not executed)

Review the clean Mac branch and push `feature/olive-mobile-c9-3` only when desired:
`git push -u origin feature/olive-mobile-c9-3`. No push has been executed. Retain
the CachyOS C9.2 recovery branch and deployed `fd63db2` checkout. This follow-up
changes mobile code, test fixtures and documentation, so no further desktop patch
or divergent-branch merge is required. If future desktop changes become necessary,
prepare another expected-HEAD guarded desktop-only patch; do not blindly pull,
reset or cherry-pick the complete Mac mobile history into the deployed checkout.

## Final acceptance run — 2026-09-27, still in progress

This run starts from `BASELINE_HEAD=22dad8729153ddab38412d4728c250ff44f095e8`,
`BASELINE_BRANCH=feature/olive-mobile-c9-3`, `WORKTREE_STATUS=clean`. Later commits
after the old `347d0eb` checkpoint are preserved. The original implementation
baseline above is historical and is not replaced. Final closure HEAD and complete
gate results remain pending. CachyOS is unchanged at
`fd63db203a56ab2c8f4d3b26d93a1d20363e3f5c`; no deployment, recovery-ref, trust or
firewall changes were made.

Local commit `40d6f5c` adds explicitly opt-in physical acceptance probes and an
owned fixture/timing utility. These are acceptance tooling, not new product
features. The normal Release app and Connect protocols are unchanged. The DEBUG
test shell avoids opening a competing channel while XCTest uses the existing
production identity on-device; keys and private profiles are never exported.

**New real C6 evidence:** `RealCompanionEdgeTests` passed on the connected physical
iPhone against its existing authenticated CachyOS peer (one test, zero failures;
`/private/tmp/olive-c93-closeout-edges.xcresult`). Synthetic transfer
`cc444e48-e841-404f-b4ef-8c8d32a68a7b` advertises the hash of four owned bytes and
sends four different bytes. Complete returns `content_integrity_failed`, Status
returns `failed`, and another Complete remains failed. This proves remote hash
rejection and an immutable failed receipt, not a desktop artifact inspection.
The read-only owner timing utility separately checks that this exact synthetic
receipt has neither a `.bin` nor `.part` artifact. The phone's production metadata
validator rejects 64 MiB + 1 with `fileTooLarge` before transfer. Closing the test
channel then attempting an offer returns `peerOffline`, without queuing it. These
last two assertions cover the device codec/transport, not system picker UI or a
malformed oversized remote offer. Permission was already Allow and was not changed.

The opt-in `RealStudioAcceptanceTests` passed for the owner-created and explicitly
shared **C93 Acceptance Shared** workspace. It restricts mutation to exact owned
`notes.txt` fixture content, verifies read/save/hash/stale refusal, restores with
the verified revision, and checks real build/test jobs. Build
`1221a71b-d822-4d33-ac5e-739a1b17bd75` and Test
`17972169-f31a-4911-8648-8fa838c0c769` completed; the test result contained one passed
owned Python case. Its prohibited-operation assertions exercise the
production Swift encoder; those alone are not remote adversarial acceptance.

The remaining owner actions are grouped in
[the acceptance checklist](OLIVE_MOBILE_C9_3_ACCEPTANCE_CHECKLIST.md). Following a
request for simpler instructions, fixture creation and workspace sharing were
completed first. The owner then set sync domains to Allow, created the two named
synthetic Chat conversations, selected only Shared, and opened the separate
Unshared fixture without sharing it. Timing
capture uses only synthetic receipt metadata and matching ordered connection
audit events. Audit timestamps have one-second resolution and cannot by themselves
establish when desktop UI changed; the owner observation is still required.
The fixture utility was run locally and its observer checked against a disposable
synthetic SQLite database. Those utility checks are not CachyOS acceptance.

**New real C5 evidence:** `RealSyncAcceptanceTests.testOwnedTodayAndSelectedChat`
passed against CachyOS with the production phone sync model/store. Synthetic task,
calendar, recurring event and linked reminder were created, acknowledged by the
desktop, explicitly synced repeatedly and reloaded with stable IDs/revisions.
Selected desktop conversation `1d20bcdd-bb21-497e-88df-9d43933f78e4` arrived with
four ordered messages and stable IDs across repeated sync. The named unselected
Private conversation did not appear. A real completed C7 turn
`8bfc77d2-1fde-4c24-aa68-a7c8a05ffca0` was imported using only that synthetic turn,
without selecting historic mobile turns, and repeatedly synced with stable user
`00e757a2-c5ab-4039-a15d-56babb6a90bb` and assistant
`063c6ae5-d8ef-404f-a6c5-54ea7f83f1ee` IDs. The owner confirmed it appears exactly
once on desktop, and confirmed the Today records and three daily event dates.

The owner edited Task/Event titles and the Reminder time on desktop. The first
automated pull did not find an expected title and stopped before writing phone
edits. A later explicit sync passed with the exact desktop titles/time; no product
change was made. Phone title/time edits then received desktop acknowledgements.
Unsent phone changes were prepared for all four domains for the next owner batch.
Real conflict preservation/resolution and tombstones are still pending.

**Studio background chronology:** the first UI attempt overlapped requested
desktop permission changes and ended with `remotePermissionDenied`
(`19283035-3ff6-4fed-b0ae-835f40f5f925`). This is not used as a background completion
pass. The next run, `74db8ee8-18e1-4c91-93ff-30103a3f5be3`, had a real visible iOS
continued-processing grant, remained backgrounded for at least 65 seconds, and
the journal records completed after about 75.4 seconds. Its actual UI showed
`completed · 0 passed, 0 failed, 0 skipped`; the test incorrectly expected only
`completed` and timed out. That assertion was corrected without a product change.
A subsequent attempt (`44a4f20e-5b12-41f2-998a-b50c10ce384a`) instead interrupted
after about 5.3 seconds with `peerOffline`; its cause remains under investigation.
An opt-in DEBUG trace now records only bounded connection phases/typed failure
codes in eight protected slots, with no content, endpoint or key material.
The full background-plus-cancel UI test remains open despite the independently
verified completed run. A separate deliberate-disconnect test observed a fresh
connection retiring before its first later read; its test reconnection now requires
a real read-only admission response, matching normal session setup. No protocol
timeout or authority rule was weakened to make these checks pass.

Fresh automated results for this run:

- Xcode listing, signed device build-for-testing, simulator-SDK build-for-testing
  and generic iOS Release build passed. No simulator runtime execution is claimed.
  Full physical unit/UI execution remains pending; the prior 67/11 case results
  above are retained as prior evidence, not relabelled fresh. Normal production
  identity launch was restored after the real C6 test so owner setup can proceed.
- Python/Swift interop passed, including C5/C6/C8 and calendar fixtures.
- Repository-scoped source compilation passed with dependencies excluded.
- Mac Connect: 254 cases, one existing owned-descendant cleanup timeout.
- Mac full Python: 1,456 cases, 58 skips, **2 failures and 3 errors**. In addition
  to the four previously documented Mac failures, the injected SQLite-lock receipt
  test reported `connection_closed` with `SQLITE_BUSY`. An immediate focused rerun
  also failed. A baseline archive at `22dad872` and a later current-source focused
  rerun both passed after concurrent builds finished. Desktop/test source is
  identical across that comparison. This is recorded as intermittent, not erased
  from the failed full-suite result or established as a product regression.
- Desktop typecheck, 101 frontend tests across 20 files, and production build
  passed. No additional desktop patch is justified by current real-device evidence.

Logs use `/private/tmp/olive-c93-closeout-*.log`. C9.3 remains PARTIAL until the
remaining real cases, final physical suite and any required fixes are complete.
Independent iOS resource expiration has not been observed; prior system Stop
uses the same callback and is not proof of resource expiration. C9.4/C10 and
optional reminder notification scheduling remain deferred.

### Further live acceptance and connection fix — 2026-09-27

The four synthetic concurrent edits (Task, Event, Reminder and selected Chat)
were retained as conflicts through repeated sync and protected-store reload.
The owner resolved all four through desktop **Keep this device** and confirmed
that those conflicts disappeared. The physical phone then verified strictly
dominating revisions, cleared conflict state, the desktop titles, and daily
recurrence with October 2 moved to October 4 and October 3 cancelled. Linked
Task completion received a desktop acknowledgement. Deleting the first shared
message preserved the later message and ordering indexes. A real UI test
relaunched the production app twice, explicitly synced and read only the owned
conversation: FIRST stayed absent and SECOND remained visible. Whole-record
Today/conversation deletion remains a separate pending phase.

A bounded transport trace reproduced the Studio disconnect as incoming C7
request frame **9**, previously rejected by the mobile response-only dispatch.
Desktop Chat polls paired-device model availability, so this valid duplex probe
could close the shared authenticated connection during unrelated companion work.
The mobile transport now strictly validates the existing C7 request, including
pinned-channel source/target binding, protocol, IDs, time bounds, fields and
arguments. Status reports all presets unavailable, permission `deny`, and not
busy. Other valid incoming operations return correlated `permission_denied`;
expired requests return `expired_request`. Malformed or mismatched frames still
close the channel. No mobile inference provider or additional authority exists.

Validation after that fix:

- 18 protocol unit tests plus the real resolved-conflict/tombstone test passed
  (19 cases, zero failures). Python decodes the independently produced Swift
  status/denial replies; full existing C5/C6/C8 interop also passed.
- Real C8 read/save/hash/stale refusal, Build and Test passed. A started Run
  (`4fc342d3-1302-4f13-a972-5f2cf8b318d8`) was deliberately disconnected. The
  replacement channel could not adopt it; 80 seconds of bounded read-only
  observation found neither late DONE nor replay in the owned fixture log.
- Real UI background Run/Cancel and selected-message tombstone/relaunch passed
  (two cases, zero failures). Studio had a visible actual continued-processing
  grant and spent at least 65 seconds backgrounded before completed status;
  a fresh explicit Run was then cancelled through the mobile UI.

Evidence: `/private/tmp/olive-c93-incoming-fix-{unit-sync,studio,real-ui}.xcresult`
and matching logs; `olive-c93-incoming-fix-interop.log`. These supersede the open
outcomes above without erasing their failed attempts. Final whole-suite regression,
remaining permission/file edges and independent expiration are still open.

The owner subsequently confirmed the completed desktop Task and cancelled linked
reminder delivery. Desktop Chat retained the bot's FIRST reply while removing
only the deliberately tombstoned user prompt; SECOND remained. This is the
expected individual-message deletion, not deletion of the entire first turn.

The post-fix full physical regression passed: **75 unit cases, 66 passed and
9 explicit live-test skips; 13 UI cases, 10 passed and 3 explicit live-test skips**.
The separately enabled real cases above are reported independently of those
skips. Xcode listing, signed device build-for-testing, simulator-SDK
build-for-testing and generic iOS Release build passed. No simulator runtime
execution is claimed. Logs: `olive-c93-current-{device-build,full-unit-ui,list,
simulator,release}.log`; full physical bundle `olive-c93-current-full-unit-ui.xcresult`.

The subsequent real tombstone phase passed: Task, Event, linked Reminder,
selected Conversation and all its remaining messages were deleted using the
production authoring path, acknowledged by CachyOS and retained as tombstones
after cold-store load and repeated explicit sync. The unselected Private
conversation stayed absent. Evidence: `olive-c93-real-sync-delete.xcresult`
(one case, zero failures). Final desktop deletion UI confirmation is requested
in the updated five-part owner checklist. The normal signed app was explicitly
installed and launched under its existing production identity successfully.

Post-fix Mac regression finished against implementation/test checkpoint
`296a2ee7765c3550edfcfcc6e7723bfa31dc4032`:

- Source compile, Python/Swift interop, desktop typecheck, all 101 frontend tests
  in 20 files, and desktop production build passed.
- Connect: 254 tests, one previously documented Mac owned-descendant cleanup
  timeout. Full Python: 1,456 tests, 58 skips, two failures and two errors:
  owned-descendant cleanup, Linux process-readiness on macOS, selected-workspace
  project run, and the detected-JDK availability expectation. The intermittent
  SQLite-lock receipt case passed in this full rerun; its earlier failure above
  remains recorded. This is not an all-green Mac Python result.
- CachyOS remains at `fd63db203a56ab2c8f4d3b26d93a1d20363e3f5c`; no desktop code,
  recovery ref, firewall, identity or permissions were changed by these fixes.
  The earlier native 254/1,443/101 validation remains the deployed evidence.

Local implementation/test commits after this run's baseline `22dad872`:
`40d6f5c` (real-peer probes/owned fixture tooling), `92e416d` (duplex C7 fix and
interop), `296a2ee` (C5 conflict/tombstone and C8 lifecycle acceptance). A docs-only
checkpoint follows. No push, merge, tag or release was performed. Status remains
**PARTIAL**, awaiting the remaining batched physical results, including permission
matrix, file collision/revocation/presence timing, real Studio draft retention,
final C9.2 Chat recovery and independent system expiration. The current checklist
marks passed checks and requests only the remaining owner actions.

### Owner file-permission acceptance follow-up

On the real paired iPhone and CachyOS desktop, the owner tested desktop
**Receive files** with the owned 5 MiB fixture and reported:

- Off: phone send blocked.
- Ask: completed after exactly one desktop approval.
- Allow: completed without approval.

This establishes the phone-to-desktop admission matrix for those policies. It
does not establish the reverse-direction policy, an active-transfer revocation,
existing-destination collision or instrumented presence timing; those remain open.

The owner then completed the reverse-direction **Send selected files** batch
with the same owned 5 MiB fixture: Off blocked desktop sending; Ask completed
after one desktop approval and explicit phone acceptance; Allow reached Ready
to Save with phone acceptance and without another desktop permission approval.
Both directional file admission matrices now have real-device owner evidence.
Mid-transfer capability revocation, collision and presence timing remain open;
these successes do not substitute for those edge checks.

### Failed instrumented 64 MiB transfer — 2026-09-27

The next owner-run timed upload did **not** pass. Transfer
`6f2c9eaf-c481-426d-bc4c-318f6fd95345` started at 14:32:54 UTC. The desktop
observed 48,037,888 of 67,108,864 bytes (71.58%) before `transfer_cancelled`, then
`connection_closed`, both at 14:33:46 UTC. Re-authentication followed at 14:33:56.
This was an unfinished transfer followed by session closure, not normal release
after a completed receipt. The owner reported no deliberate cancellation during
this timed attempt and saw inconsistent compact/expanded system activity UI.
The tick is not accepted as completion evidence.

The bounded phone operation journal records `expired` / `backgroundTaskExpired`
52.277 seconds after start, with 47,972,352 bytes acknowledged before cancellation.
The extra desktop chunk is consistent with an acknowledgement in flight; neither
side records completion. The old journal cannot distinguish the system expiration /
Stop callback from the app's no-grant/submission-failure fallback. Therefore this
is not yet labelled a proven independent iOS resource-expiration event or assigned
a specific system cause. The observer also confirmed the earlier invalid-hash
transfer's `.part` and `.bin` artifacts were absent.

A demonstrated UI defect was corrected: file cleanup after background execution
ends now retains **interrupted** and explains that background execution ended,
instead of labelling it ordinary user cancellation. A late send-loop failure
cannot overwrite that explanation. Background operation v1 receives additive,
optional fields for grant time, stop source, final system progress and the success
value reported to iOS. Existing records remain readable without those fields.
The system activity subtitle is explicitly changed to Completed/Cancelled/
Interrupted before completion is reported; unsuccessful work still reports false.
No timeout, file bound, authority or retry behavior was relaxed.

Optional DEBUG per-frame trace observations are now buffered in memory; only
connection milestones/errors persist the bounded trace. This removes unnecessary
per-chunk diagnostic disk writes from the installed acceptance build, without
assuming they caused the observed expiration. Existing C6 receipts and operation
journals retain their durable semantics. A synthetic 64 MiB selection/background
UI probe is opt-in: it stages only known owned bytes, bypasses only the system
file picker, then taps the real Send action once against the pinned CachyOS peer.
It neither simulates a background grant nor automatically retries a failed send.

Apple documents that continued processing can end under changing system resource
conditions and that the expiration handler also handles system-UI Stop:
[BGContinuedProcessingTask](https://developer.apple.com/documentation/BackgroundTasks/BGContinuedProcessingTask)
and [long-running tasks](https://developer.apple.com/documentation/BackgroundTasks/performing-long-running-tasks-on-ios-and-ipados).
These API limits do not explain this particular run without further evidence.

The first automated diagnostic retest (`625dac91-1faa-4ddb-a067-b9ef0f53c477`)
received an actual background grant and completed the full 67,108,864-byte C6
transfer in 58.077 seconds. Its journal records matching system progress totals
and `systemReportedSuccess: true`; no expiration source is recorded. The UI
runner spent at least 65 seconds on the Home screen, but its post-return tap
opened Selected Chat instead of Files and the completion assertion failed on
that wrong screen. The test now waits for foreground reconnection and reacquires
its navigation target. The successful protocol result and failed UI attempt are
recorded separately; this is not a claim that the earlier other-app failure is
fixed or that the first UI case passed.

A bounded trace from the intervening owner file tests also records three incoming
C7 probes answered on a channel that subsequently carried C6 file frames. This
confirms that the earlier duplex-probe fix is active in the installed app; it
does not assign a cause to the later background expiration.

The corrected physical UI retest (`e3a390ac-cab2-4b51-9a99-b977ec95ce0a`)
passed against the real CachyOS peer: 67,108,864 bytes completed in 57.786 seconds,
with a real continued-processing grant and at least 65 seconds on the iPhone
Home screen. The bounded trace records receipt decoding at 812213510.455722,
journal completion at 812213510.464964, then local connection closure at
812213510.487039 (Apple reference-date seconds). System progress totals matched
the full file size and success was reported true. Thus this run released its
session after the verified receipt. This does not establish the desktop UI's
exact presence-update timing or reproduce resource use inside another app.
An owner repeat in another app remains required; the earlier failure stays open.

Validation after code/test commit `813e3b8b45105442ac9a0cd8cca24bf8c2808a2b`:

- Physical unit tests: 77 cases, 68 passed, 9 opt-in skips. This includes the new
  interruption-versus-user-cancellation regression and owned fixture preparation.
- Physical UI tests: 14 cases, 11 passed, 3 opt-in skips, including the successful
  real background file transfer. The first failed navigation attempt above remains
  part of the record.
- Xcode list, simulator-SDK build-for-testing, generic iOS Release and signed
  device build-for-testing passed. No simulator runtime execution is claimed.
  The signed app was installed and launched with its normal production identity,
  without acceptance launch arguments, after testing.
- Mac repository-scoped compilation, Python/Swift interop, desktop typecheck,
  101 frontend tests across 20 files and production build passed.
- Mac Connect: 254 cases, one previously recorded owned-descendant cleanup error.
  Full Python: 1,456 cases, 58 skips, two failures and two errors, retaining the
  same owned-descendant, Linux executable-readiness, selected-workspace run and
  JDK-discovery expectations recorded above. This is not an all-green result.
- CachyOS remains at `fd63db203a56ab2c8f4d3b26d93a1d20363e3f5c`, with the earlier
  native regression evidence unchanged. No desktop patch, permission/trust change,
  push, merge, tag or release was performed.

This investigation started at `40042c6b55c7f1ea0ddee0bb9ad7516e675b38ed` on
`feature/olive-mobile-c9-3`; the only code/test commit is `813e3b8`, followed by a
documentation checkpoint. C9.3 remains **PARTIAL**. Remaining acceptance is not
waived by these successful diagnostic runs.

### Fresh send rejected before bytes — 2026-09-27

The owner next reported that explicit new sends immediately displayed “Transfer
interrupted. Check its receipt before explicitly sending again.” The bounded
operation journal shows three distinct new operation IDs, each ending at zero
bytes within about 40 ms. These are separate user attempts, not automatic replay
of the earlier expired transfer. They do not establish another background timeout.

Inspection found that the Swift C6 decoder collapsed `inbox_quota_exhausted`,
`unknown_transfer`, capacity and ledger rejection codes into the same interruption
message. It now preserves typed storage/receipt errors and the existing busy/ledger
errors, while retaining strict response identity and error-format validation.
The added regression covers these codes, permission/hash rejection, unknown
failure fallback, mismatched request ID and malformed error text. No protocol,
quota, permission, cleanup policy or retry behavior changed.

The desktop's existing 256 MiB inbox bound counts retained completed incoming
files, including saved files until explicit **Dismiss from Inbox**. Dismissal
removes only the app's inbox artifact and retains the receipt; separately exported
copies remain. Accumulated test files are a suspected admission blocker, pending
the owner's read-only desktop count. No inbox files have been removed by the agent
and the previous other-app background repeat remains pending.

Code/test checkpoint `6cba75e` passed physical unit tests (78 cases: 68 passed,
10 opt-in skips) and UI tests (14 cases: 10 passed, 4 opt-in skips). No real file
send was triggered by this regression batch. Xcode list, signed physical build,
simulator-SDK build-for-testing and generic Release build passed; the tested app
was installed and launched normally without acceptance flags. Source compilation
and Python/Swift interop passed. Full Mac Python again ran 1,456 cases with 58
skips and the same two failures/two errors listed above. Desktop source was not
changed; native CachyOS evidence remains at the recorded checkpoint. This follow-up
started at `3cab8a199d82ee7744848c089da5e9e2cc83f21b` on the same C9.3 branch.
No push or destructive inbox cleanup occurred; C9.3 stays PARTIAL.

The owner then confirmed six completed inbox files totaling 217,055,232 bytes
(207 MiB). Adding the requested 64 MiB would exceed the unchanged 256 MiB bound
by 15 MiB. This confirms insufficient inbox quota for that offer, separate from
the earlier background expiration. The owner was directed to Save if needed and
explicitly Dismiss from Inbox one completed owned 64 MiB test transfer, which
would reduce retained usage to 143 MiB, before choosing and sending the file again.
Dismissal and the subsequent timed transfer are not yet reported as completed.
