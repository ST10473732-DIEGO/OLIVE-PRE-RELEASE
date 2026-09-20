# OLIVE Connect C6 portable reliability repair

Scope: C6 only. No C7, model routing, new capability, cloud dependency, push,
merge or tag. The matrix retains `fail-fast: false` and both required runners.

## Evidence and inherited repairs

Reviewed both `4997d2e` and `5434675`, their production and regression-test
changes, and the C5/C6 and portable-lock documentation. Read-only device
snapshots, transactional authority checks, bounded database waits, local
reconnect intent and owning-worker descriptor closure remain intact.

The supplied hosted runs are [Linux full suite](https://github.com/ST10473732-DIEGO/OLIVE/actions/runs/35505318148)
and [Connect Ubuntu/Windows](https://github.com/ST10473732-DIEGO/OLIVE/actions/runs/35505318153),
both at merge `da1b55e`. These logs contain assertions and bounded protocol
errors, not the original OS/SQLite exception from the channel worker. They
cannot retrospectively establish every underlying exception category.

### Linux full-suite root cause

C6 appended peer-wide file invalidation **after** `LocalNetwork.finished()`
removed the channel and released the network lock. A fresh channel/offer could
be admitted while old invalidation was still pending, and then be interrupted
by that old callback. The corrected C5 read-only snapshots permit connection
setup during old-worker cleanup; C6 must not assume that an empty channel map
means all peer cleanup finished.

`network.py` now serializes adoption, channel removal and transfer invalidation
using the existing file lock, with the consistent order file lock then network
lock. Explicit disconnect also invalidates before releasing file admission and
joins captured workers outside both locks. A stale worker cannot invalidate a
replacement channel's newly admitted file. Terminal receipts and UUID identities
are retained. The new admission/old-teardown event regression fails against the
pre-repair implementation. The retry regression additionally asserts a different
transfer ID and completes from zero.

### Ubuntu Connect root-cause boundary

A confirmed channel-scope leak existed in `files.py`: the exception handler for
a file operation opened a second database transaction to record failure, and
exceptions from that recovery transaction escaped `receive()` into the C3
worker. A cleanup unlink error could likewise escape recovery. C3 then treated
the exception as a transport failure and closed the shared authenticated socket.
Quota rejection also opened an unnecessary recovery write transaction even when
there was no transfer row to recover.

Recovery is now file-scoped: no recovery transaction for a nonexistent row;
bounded failure-receipt attempts; blocked transfer IDs while a receipt is queued;
retry of cleanup by the existing reaper; and startup reconciliation as before.
File-list snapshots use the repository's enforced read-only mode. An injected
failure-receipt database error now returns a file rejection and permits a real
C3 ping. Permission abort, quota, timeout/late reply and finalization failure
also keep the original channel usable in regressions.

**The original two Ubuntu assertions have not been reproduced locally without
fault injection.** All three reported cases passed 50 times each before repair.
The hosted logs lack the original channel exception, so the recovery leak is a
proved defect, not proof that it caused both particular hosted Ubuntu failures.
The channel now retains a transient exception-class diagnostic; file tests print
bounded local diagnostics on failure. Fresh hosted runs are still required.

### Windows pairing root cause

The single-process desktop-pairing test still waited for the remote side's
transient `offline` state after revocation. Its automatic reconnect intent was
still armed and could replace `offline` with `connecting`/`failed` before the
poll observed it. The earlier C5 process test already recognized this distinction;
the single-process case had not adopted it.

`network.disconnect()` now normally returns only after captured workers join,
using the existing four-second lifecycle bound. The pairing test observes the
original remote worker's completion and cleared latency, then explicitly ends
local reconnect intent before asserting stable offline. Local revocation also
asserts offline. Trust remains separate from live state. Existing event tests
that intentionally hold a worker mid-cleanup use the explicit `wait=False` test
path; their joins and assertions remain. A new event test proves ordinary
`disconnect()` cannot report completion before the worker exits.

### Windows file_io_failed root cause

The old completion path reopened the partial as `rb` and called `os.fsync`.
Windows flushing requires write access; [Microsoft's FlushFileBuffers contract](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-flushfilebuffers)
requires `GENERIC_WRITE`. All advertised bytes could therefore be received before
completion failed. This defect is reproduced with Windows-style descriptor rules
on Linux: the old implementation fails, the repaired implementation passes.
The original hosted protocol suppressed the native errno, so native confirmation
of that exception category remains pending. No evidence implicates antivirus.

`file_store.finalize_partial()` now flushes/fsyncs a writable descriptor, closes
it, verifies actual size and SHA-256 with bounded reads, closes that reader, and
exclusively publishes the opaque artifact using a same-directory hard link.
An existing destination is never replaced. The partial link is then removed
under the same transfer lock, and the completed receipt commits before any
success response or export is possible. Ordinary NTFS and POSIX filesystems
support this operation; a filesystem without hard-link support fails closed
with `finalize_failed`, rather than silently adopting overwrite semantics.

The Windows-semantics regression rejects read-only flush and publication while
any tracked owned partial/spool handle remains open. Other tests cover exclusive
collision, finalization failure, rollback after publication, cleanup exclusion,
and eventual removal after a synthetic sharing violation.

## Channel and artifact ownership

C3 owns the socket, TLS identity, reconnect intent and channel worker. A file
worker owns only its transfer and bounded requests. File quota/admission denial,
permission denial, cancellation, interruption, I/O failure and request timeout
are transfer-scoped. A late valid bounded file response is inert. Malformed
framing/response, source authentication failure, TLS failure and revocation remain
channel security/lifecycle concerns; no authority check is bypassed.

Only the transfer lock can mutate owned partial/spool files, finalize an artifact
or clean up failed receipt publication. It remains held through rollback and
failure recovery as well as successful receipt commit. Completed bytes are
exposed only through a completed incoming receipt. A final artifact published
before a failed commit is removed when failure is recorded; if storage remains
unavailable, the transfer is blocked and recovery is queued. Startup still
removes noncompleted artifacts and every leftover partial. A preexisting
exclusive-publication collision is not deleted by the failed operation.

Cleanup inability does not turn a verified, committed completion into a false
failure: a leftover partial link is queued for removal. Conversely, flush, hash,
publication and receipt failures never become fabricated success. A lost final
acknowledgement still means completed receiver / uncertain sender, without any
claim of distributed exactly-once delivery. Interrupted IDs never resume.

Internal diagnostics are a bounded 32-entry deque of stage and numeric errno,
including `open_failed`, `write_failed`, `flush_failed`, `hash_failed`,
`finalize_failed`, `receipt_failed` and `cleanup_failed`. Neither exception text,
private paths nor contents enter the protocol or persistent Activity. Process
fixtures expose the categories only through a test command.

## Validation

All Python execution uses `.venv/bin/python`. No new sleeps, timeout increases,
test retries, skips or CI exceptions were added. The new disconnect completion
uses the existing four-second worker-join budget; the file-timeout regression
shortens its test-only request deadline to 0.1 seconds with event-held work.

| Check | Result |
| --- | --- |
| Before repair, original three reported cases | 50 runs each passed; ordinary hosted timing was not reproduced |
| Before repair, event/Windows-semantics regressions | Old teardown admission and read-only flush fail deterministically |
| Before repair, failure-receipt regression | Old handler produces `ConnectError('connection_closed')` |
| Final targeted repetitions | 50/50 each: disconnect/new retry, active multichunk ping/permission abort, quota/control |
| Final complete FileTests repetitions | 3 runs × 20 tests = 60 passed |
| Exact Connect workflow command | 3 runs × 165 tests = 495 passed, no skips |
| Full Python discovery | 1,019 run: 1,008 passed, 11 existing platform/toolchain skips |
| Frontend unit tests | 43 passed in 13 files |
| Typecheck / lint / production build | Passed |
| Focused Linux desktop acceptance | 9 passed, including real C4–C6 Devices and owned shutdown |
| Repository Python source compilation | 630 files passed |
| Literal `compileall -q .` in installed workspace | Fails only on existing ignored PySide6 Android Jinja template |
| Literal `compileall -q .` in source-only tree | Passed for all 630 repository Python files |
| Diff / privacy review | No new user data, credentials, absolute personal paths or branding regressions |

Full discovery's skips are eight Windows-specific checks and three unavailable
C# debugger/OmniSharp integration checks. No skip was added. The existing
26-uncollectable-objects shutdown warning remains. Failed pre-repair regression
runs and the initial sandbox-denied socket attempt are not counted as successes.

New file regressions cover closed writable flush/publication, exclusive artifact
creation, failed flush/publication, receipt rollback after publication, delayed
failure-receipt persistence, cleanup/publication exclusion, deferred partial
cleanup, old-channel admission ordering and timeout/late-response isolation.
The new network regression proves disconnect completion joins its worker.
Existing transfer, permission, replay, third-peer, pairing and security assertions
remain. The two-process retry also explicitly checks distinct IDs.

Logs are kept outside the repository in `/tmp/c6-*.log`; they are not committed.
Native Windows and a fresh hosted Ubuntu matrix are not claimed from Linux
execution. Both hosted legs must finish independently after an authorized push;
no push or workflow dispatch was performed.
