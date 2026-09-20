# OLIVE Connect C6 — inert device-to-device file transfer

C6 transfers individual regular files between paired desktop peers over C3 TLS
1.3. It adds no filesystem RPC, directory synchronization, remote execution,
Mobile application, cloud service, model dependency, or automatic import.

## Authority and capabilities

`files.receive` and `files.send` are independent per-device Off / Ask / Allow
permissions, both Off by default. Pairing and C5 sync grant neither. Send means
permission for a **local user-selected** file to leave this desktop; it never
permits a remote peer to read a path. Receive means admission to OLIVE Inbox,
never authority to choose a destination outside application storage.

C3 pins the C2 certificate, supplies authenticated source identity, and rechecks
trust throughout the socket lifecycle. File envelopes must match that identity
and the local target. Transfer IDs are canonical UUIDs globally unique in the
local ledger; another paired peer cannot reuse or continue an existing ID.
Advertisements, display names, payload IDs and MIME labels grant no authority.

Ask uses the existing `ConnectApprovals` and Host local confirmation registry.
The prompt shows the authenticated peer, filename, size and MIME metadata.
Its binding includes the entire offer fingerprint (including SHA-256, transfer
ID, source, target, request UUID and expiry), pinned identity and device revision.
The remote protocol has no approve flag, approval response or permission setter.
Deny accepts no bytes; Allow once leaves policy at Ask. Sending Ask has a distinct
local-only operation/capability so an incoming offer cannot reuse that approval.
Cancellation withdraws just that transfer's prompt.

Every incoming chunk and completion checks current pairing, certificate binding,
capability policy and permissions inside the device repository write transaction.
The accepted permission rules must still match. Local permission changes
conservatively interrupt active file transfers for that peer, including Ask waits;
revocation also closes C3. An already executing bounded chunk transaction may
finish before a concurrent permission/revocation transaction commits; no subsequent
chunk or completion can use the old authority. Already completed files remain
local data and can still be saved after revocation.

## Local selection, review and export

Electron's existing file-action broker opens the native **Select one file to
send** dialog. The renderer supplies only the paired device UUID; it cannot
supply the source path through Connect's renderer-call schemas. The backend
private pipe receives the chosen local path and checks regular-file type before
opening. Directories, symlinks, FIFOs, devices and sockets are rejected. POSIX
nonblocking/no-follow open flags and a second descriptor type check defend the
selection/open race; regular selected file bytes are the only transferred object.

Preparation snapshots size, SHA-256, display name and filename-derived MIME into
an application-owned outgoing spool using bounded reads. The source path exists
only in transient local memory, never in a wire message, ledger or Activity.
**Send reviewed file** dispatches the snapshot. The source is rehashed and its
file identity, size, mtime and ctime checked after local review; its stat snapshot
is checked again after receiver Ask. Changes require a fresh selection/review.
Bytes transmitted after that point come from the immutable owned snapshot.

Incoming bytes land in `<resolved profile>/quarantine/connect-inbox`, extending
the existing DownloadQuarantine semantics with streaming storage. This uses the
ordinary resolved OLIVE/legacy profile; it does not choose another user-data root.
Artifacts have opaque UUID filenames and `.part`, `.out` or `.bin` suffixes.
The remote display filename is metadata only. Duplicate display names have
distinct UUID artifacts and never overwrite each other.

After writable flush/fsync and descriptor closure, exact length and SHA-256
verification close their reader before exclusive same-directory hard-link
publication of the completed inert artifact. The partial link is removed and
the completed receipt committed. Existing artifacts are never replaced. No
reader/export route accepts a partial record. Startup removes noncompleted artifacts left by a crash
between publication and receipt commit. Completed bytes are retained until an explicit
local **Dismiss from Inbox**; dismiss retains the replay receipt.

**Save** uses the native local save dialog via the same Electron file broker.
The backend streams and rechecks the completed artifact and uses exclusive `xb`
creation, matching DownloadQuarantine's no-overwrite policy. An existing path,
including a symlink, is refused even if the dialog's overwrite prompt was accepted;
the user must choose a new path. Export failures remove only the newly created
export. No remote message contains an export destination. Saving does not open
the result or confer execution permission.

## Connection and protocol

Architecture choice **A**: C3 adds frame types **7/8** for file request/response.
There is no second listener, unauthenticated socket, endpoint negotiation or
firewall modification. Existing opt-in selected-interface, same-LAN firewall and
C2 identity requirements apply. Both endpoints need C6; older peers reject the
new frames rather than downgrade identity or encoding.

`olive-files/1` packets use a four-byte network-order JSON metadata length,
strict bounded UTF-8 metadata, then raw bytes. The exact envelope fields are:

```
request_id, protocol_version, transfer_id, source_device_id, target_device_id,
operation, arguments, timestamp, expires_at
```

`offer` arguments are exactly `name`, `size`, `sha256`, `mime`; it has no bytes.
`chunk` arguments contain only the exact next `offset`, followed by 1–65,536
raw bytes. `complete`, `cancel`, and `status` have empty arguments and no bytes.
Responses contain the correlated request ID, protocol version, completed/rejected
request status, and either a strict transfer-state/received-size result or a fixed
error code. Request completion is distinct from a **completed transfer**.
Duplicate keys, unknown fields/types/versions, booleans used as lengths, invalid
UUIDs, non-finite values, oversized packets and impossible offsets fail closed.
There is no whole-file JSON/base64, pickle, marshal, eval or complex content parser.

The sender uses strict sequential stop-and-wait: one chunk per transfer in flight,
with a matching exact acknowledged byte count before reading the next. Incoming
chunks write at most 64 KiB in one handler. The existing C3 loop services control
traffic between frames; transfer lifetime is never one blocking request. A file
request timeout does not close the shared channel. Late bounded file replies are
inert. Ping during a real active multi-chunk transfer is tested. Slow/broken
filesystem I/O can still delay a single bounded operation; this is not a hard
real-time disk scheduler.

| Bound | Value |
| --- | --- |
| File size | 64 MiB, including a valid zero-byte file |
| Chunk size | 64 KiB |
| Metadata | 4,096 bytes |
| Request frame payload | 69,636 bytes maximum |
| File response | Existing 16,384-byte C3 bound |
| Inbox reserved + completed bytes | 256 MiB |
| Outgoing active snapshots | 128 MiB |
| Free-disk reserve | 16 MiB beyond the admitted size |
| Active local transfers | 4 total, at most 2 per peer |
| Durable transfer receipts | 10,000, fail closed without eviction |
| Display-name UTF-8 length | 180 bytes |
| C3 write queue / all pending requests | Existing 8 each |
| File frames per authenticated peer | 2,400 / minute, across reconnects |
| Ordinary C3 message budget | Unchanged, 60 / minute |
| File request response wait | 5 seconds |
| Offer/Ask lifetime | 120 seconds |
| Idle accepted transfer | 30 seconds |
| Absolute active lifetime | 10 minutes |

Quotas reserve the advertised full size **before admission**, including pending
Ask offers; no absurd preallocation occurs. Actual byte counts remain authoritative
and overshoot is rejected before writing. Quota exhaustion never evicts existing
files or trust/replay state. A malicious authorized peer can exhaust these finite
quotas; local dismissal and policy Off are the recovery controls. Ledger archival
is deferred rather than evicting replay protection.

## States, interruption and cleanup

The durable ledger uses additive `file_transfers_v1` storage behind FileStore in
the existing device repository. C1–C5 tables and schema versions are unchanged.
Records contain transfer/source/target/peer IDs, direction, immutable metadata,
received size, state, timestamps, opaque artifact reference and fixed errors.
Only offer metadata/permission binding is retained privately; no bytes or source
filesystem paths are stored in rows. The UI returns at most 100 recent records.

States: offered, awaiting_approval, accepted, transferring, verifying, completed,
declined, cancelled, failed, interrupted, dismissed. Completion requires both
exact byte count and SHA-256 agreement. Progress is acknowledged/received bytes,
not an elapsed-time animation. Receivers never report partial bytes as a file.

Resume is deliberately **not implemented**. Cancel, disconnect, authority changes,
idle expiry and shutdown remove partial/spooled bytes and preserve terminal
receipts. Startup interrupts unfinished receipts and removes owned partials.
A cancelled/failed/interrupted ID cannot be reused for writes. An identical offer
returns its existing terminal state; changed metadata is rejected. Completed or
dismissed replay cannot recreate bytes. Explicitly selecting and sending again
creates a new transfer reviewed from zero, never an automatic retry.

If the final acknowledgement is lost, the receiver may have a completed file
while the sender reports interruption. The peer's durable receipt remains
queryable by protocol `status` or an identical offer; the UI currently does not
automatically reconcile that uncertainty. Check the receiving Inbox before
explicitly starting a new send. There is no claim of distributed exactly-once
user intent or automatic retry after an uncertain outcome.

Both sides can cancel the transfer they participate in. Remote cancellation is
bound to its authenticated peer and transfer ID; terminal completed artifacts
are never deleted by it. Other transfers and C3 sessions remain available.
Shutdown closes admission, interrupts file state, joins bounded sending/cleanup
workers, and then uses C3's existing shutdown. No network worker is created just
by ordinary application startup.

## Content handling, filenames and privacy

Unsafe names are rejected: separators, traversal, absolute/drive/UNC/URL syntax,
Windows device names, control/format characters, empty/oversized names and
ambiguous trailing dots/spaces. Names never participate in Inbox path construction.
MIME is display metadata inferred from a sender filename, not a safety decision.

Executables, scripts, AppImages, desktop files, archives and malicious documents
remain inert byte artifacts. There is no execute bit addition, automatic shell
open, extraction, installation, indexing, Chat attachment, Studio import, Calendar
import, Mail send or onward transfer. Hash verification establishes integrity
relative to advertised content, **not malware safety**. The UI says **Transfer
verified**. A compromised paired peer can still deliberately send malicious bytes
when granted permission; manual use after export remains a separate local choice.

Generic Activity retains only peer/transfer IDs, known file capability, timestamp
and bounded state events: file_offer, file_accepted, file_declined,
transfer_started, transfer_completed, transfer_failed, transfer_cancelled.
Chunks, content, filenames, hashes and absolute paths are not logged there.
Dedicated Devices transfer records show names, sizes, types, real progress and
fixed errors. The UI only shows Encrypted · Local when C3 reports authenticated
transport. Permissions and the workspace layout follow C4; Files is a small panel.

C5 record frames, stores, signed revisions and sync permissions remain separate.
Natural-language file sending is deferred: there is no safe selected-file transfer
reference in the existing router contract. No path guessing or ambiguous device
resolution was added. Use explicit file selection and the selected paired device.

## Threat model and platform boundaries

| Threat | Defense / remaining boundary |
| --- | --- |
| Giant offer / disk fill | Size, active count, Inbox/outbox, disk reserve, frame/rate and durable-ledger quotas; authorized quota exhaustion remains possible |
| Traversal / hostile names / duplicate names | Strict metadata validation and opaque generated paths; exclusive local export |
| Special file / symlink | Regular-file checks before and after open; no symlink filesystem objects |
| Tampered bytes / wrong hash / size lie | Sequential length accounting and incremental SHA-256 before completion |
| Overlap / conflicting duplicate chunk | Exact next offset; fail and discard partial |
| Transfer replay / changed ID metadata | Durable global-ID receipt; immutable metadata comparison; no completed replay writes |
| Third-peer takeover | C3 identity, target, ledger peer/direction binding on every operation |
| Permission/revocation race | Repository transaction boundaries, per-chunk authority, local invalidation and C3 revocation |
| Disconnect / lost final acknowledgement | Terminal interruption and cleanup; durable completed receipt, no automatic duplicate send |
| Slow sender/receiver | C3 read/write deadlines, per-request wait, idle/absolute expiry and bounded workers/queues |
| Executable / archive / document malware | Inert storage only; no scan/safety claim and no automated use |
| Compromised paired peer | Narrow permissions and quotas limit authority, not the malicious content of allowed bytes |
| Compromised local profile / OS / rollback | Outside C1–C6 trust boundary; no hardware anti-rollback or same-user filesystem isolation claim |

Shared protocol/core uses Python's standard library and existing C2/C3 dependencies.
No platform-specific socket identity or filesystem RPC exists. Windows gets the
same conservative filename rules, opaque filenames and exclusive export.
Chunk file handles close between writes and cancellation so Windows file locking
does not depend on POSIX unlink-open behavior. POSIX no-follow/nonblocking flags
are used when available; Windows still checks actual descriptor type. Native
Windows and physical-LAN/firewall acceptance are not inferred from Linux tests.

## Validation

Portable tests use real C3 loopback, synthetic vaults, owned temporary files and
ordinary services. `test_connect_files_process` runs two independent backends and
the actual Host Ask registry: Off, deny, allow once, exact binary data/hash/size,
Inbox, no source-path disclosure, policy still Ask, explicit Save, mid-transfer
disconnect/restart-from-zero, active revocation, rejected reconnect and shutdown.
`test_connect_files` covers malformed framing/metadata, unsafe names, size/hash/
offset tampering, duplicate replay, a third peer, source changes, special files,
quota denial, cancellation, disconnect, live authority changes, final-ack loss,
restart/dismiss replay, empty files, expiry and active-transfer ping responsiveness.

The Linux/Windows portable Connect CI command includes both C6 test modules.
Electron's Devices acceptance uses the real backend fixture and second C3 process
for Off, native selection, review, Ask/Deny/Allow once, progress, cancel, receive,
Save, changed-source failure, active-transfer revocation and sent/received verified states. Dialog responses are controlled to owned
temporary paths; this is not native dialog focus/overwrite certification.
C1–C5 pairing, permissions, sync/conflict and revocation remain exercised.

Final Linux verification, 2026-09-20, on `feature/olive-connect-c6`:

| Check | Result |
| --- | --- |
| Full portable Python suite | 1,002 run: **994 passed**, 8 platform skips, no failures |
| Portable Connect CI command | **148 passed**, including 16 C6 tests |
| Frontend unit tests | **43 passed** in 13 files |
| TypeScript / ESLint / production build | Passed |
| All repository Python source compilation | **630 files passed** |
| Exact `python -m compileall -q .` | Existing ignored PySide6 Android `__init__.tmpl.py` Jinja syntax failure; not marked passed |
| Focused Linux Electron acceptance | **9 passed**: GO, Devices/C4–C6, Linux startup and reminder restart, Studio, REIMAGINE and owned shutdown |
| Diff / privacy review | No user data, credentials, sender source paths or branding regressions introduced |

The full Python suite also covers Chat and shutdown. The pre-existing warning
about 26 uncollectable Python objects remains. The first Electron run caught a
Files/Sync duplicate React key, fixed before the final complete run. A Save test
was corrected to wait for actual file creation, and the two-process interruption
assertion now matches the exact new transfer ID rather than a prior completed
transfer. An earlier reminder navigation timeout passed on the focused rerun and
on the final complete nine-case run. These earlier failures are not counted as
successful acceptance.

Reproduction uses the existing repository toolchains:

```sh
python -m unittest discover -s tests -v
# The full Connect command is in .github/workflows/connect-portable.yml.
npm --prefix desktop test
npm --prefix desktop run typecheck
npm --prefix desktop run lint
npm --prefix desktop run build
python -m compileall -q .
cd desktop
npx playwright test browser.spec.ts connect.spec.ts linux-l1.spec.ts linux-l3.spec.ts studio.spec.ts media.spec.ts
```

Configure the existing `DOTNET_ROOT` for unrelated Studio fixtures. Local logs
are `/tmp/olive-c6-python-final.log`, `/tmp/olive-c6-connect-final.log`,
`/tmp/olive-c6-desktop-final.log`, `/tmp/olive-c6-frontend.log`,
`/tmp/olive-c6-typecheck.log`, `/tmp/olive-c6-lint.log`,
`/tmp/olive-c6-build.log` and `/tmp/olive-c6-compile.log`; these are not committed.
This is local execution of the portable CI command, not a claim that hosted
GitHub runners or native Windows were run. No physical LAN, wallet, model/GPU,
Internet relay, mobile or installer re-certification is inferred.

Resume, automatic uncertain-receipt reconciliation, natural-language sending,
batch/directory transfer, automatic imports, ledger archival and remote AI remain
explicitly deferred. The next roadmap stages are C7 Remote AI, C8 Remote Studio,
C9 OLIVE Mobile and C10 Internet direct / relay.

C6 hosted reliability repair and its evidence/remaining hosted verification are
documented in [the portable repair report](OLIVE_CONNECT_C6_PORTABLE_REPAIR.md).
