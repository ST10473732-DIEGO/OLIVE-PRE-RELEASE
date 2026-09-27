# OLIVE Mobile C9.3 — companion features and background continuation

**Status: IN PROGRESS. The real iPhone + CachyOS completion gate has NOT passed.**

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
- Latest validated mobile implementation: `dc8ec93`.

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
expected suspension, offline, reconnecting, revoked and unpaired.

A bounded protected journal stores operation ID, capability, peer, label,
protocol ID, request digest, start time, verified progress, state and required
file/Studio scope metadata. It stores no new authority. Late updates are bound
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
binds resolution to the local revision reviewed by the user.

Remaining C5 limits: recurrence/exception data is preserved, but full parity with
the Python dateutil recurrence/exception validator and recurring agenda expansion
is not yet established. Contact/project relationships outside this milestone are
held as missing dependencies. Real selected/unselected, duplicate, tombstone and
conflict acceptance is pending. Do not describe all C5 edge cases as complete.

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
A guided recovery/resync UI is still outstanding.

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
| Signed physical build/install/test | Passed: 57 unit cases, 2 opt-in LAN skips, 0 failures; **55 passed** |
| Physical UI tests | Passed: 9 cases, 1 opt-in LAN skip, 0 failures; **8 passed** |
| Normal production-identity launch | `devicectl` normal launch succeeded after tests; observed C6 results below |
| Python ↔ Swift interop | Existing C2/C3/C7 vectors/TLS pairing plus new C5/C6/C8 vectors passed |
| Mac `python -m compileall -q .` | Passed |
| Mac full Python | 1,455 cases, 58 skipped, 2 failures + 2 errors; NOT green |
| Mac Connect | 254 cases; C8 descendant-reaping timeout remains; NOT all green |
| Mac desktop typecheck/unit/build | Passed; 101 tests across 20 files |
| Diff review | No personal fixture data, secrets, branding downgrade or unrelated data changes |

Mac failures match the C9.2 documented platform/environment categories: C8 owned
subprocess reap timeout, Linux readiness/non-ELF inspection, selected workspace
run outcome and detected Java toolchain expectation. No blanket Mac regression
pass is claimed. Using a canonical `/private/tmp` test directory removed additional
macOS `/var` vs `/private/var` alias failures from the first run.

Latest local evidence: `/tmp/olive-c93-device-tests-6.xcresult`,
`/tmp/olive-c93-device-tests-6.log`, `/tmp/olive-c93-simulator-cancel-final.log`,
`/tmp/olive-c93-release-cancel.log`, `/tmp/olive-c93-interop-final.log`,
`/tmp/olive-c93-compile-final.log`, `/tmp/olive-c93-python-2.log`,
`/tmp/olive-c93-connect.log`, `/tmp/olive-c93-desktop-tests-2.log`.
These are local logs, not portable committed artifacts. Earlier physical failures
in strict decimal parsing and a Stop/background race were repaired before the
passing runs. Unit tests also cover version preservation, expired cleanup,
no-replay launch, stale progress fencing, immutable Chat order, tombstones,
signed conflict handling, durable uncommitted Today drafts, file bounds, Studio
hash rejection and private labels. The C6 follow-up adds a physical stored-byte
tamper/collision test. The last full UI run is `olive-c93-device-tests-4.xcresult`;
the C6/background follow-up reran all unit tests plus simulator/Release builds
and normal launch, without claiming another full UI run. The latest recovery test
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
inspection. Force-quit behavior remains a separate acceptance check.

The retained C6 maximum is 64 MiB, so a 100 MB acceptance file is prohibited by
the existing protocol. These results prove the tested supported background file
flows, cancellation/reconnect and outgoing network-loss/no-replay paths, not indefinite connectivity,
force-quit recovery or other capabilities.

## Completion gate and limits

Still pending: actual selected Chat/Today bidirectional records and conflict cases;
C6 negative cases and the observed desktop presence timing; active
Chat continuation/Stop; shared Studio save/revision/jobs/cancel and background
behavior; force quit and its recovery path, remaining direction-specific failure
cases, permission Off/Ask/Allow, and C9.2 real-device regression.

Additional implementation/coverage gaps above (recurrence parity, guided corrupted-store recovery, feature conflict/error UI acceptance)
remain C9.3 work. They are not silently deferred to declare the milestone complete.
Reminder notification scheduling is optional and currently omitted.

C9.4 remains deferred: share extension, advanced notification polish, transfer
soak, second-device readiness, additional accessibility, final battery/performance
tuning and distribution preparation. C10 remains deferred: different-network
access. No cloud account, relay or APNs infrastructure has been introduced.
