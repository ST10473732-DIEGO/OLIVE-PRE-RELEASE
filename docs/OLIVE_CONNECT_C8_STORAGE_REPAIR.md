# C8 SQLite contention and transport retirement repair

Scope: `feature/olive-connect-c8`, following diagnostic commit `9d3d4d5`.
No C9, capability expansion, newline conversion, package installation, push,
merge, tag, or release is included.

## Evidence and limits

[Hosted run 35521515027](https://github.com/ST10473732-DIEGO/OLIVE/actions/runs/35521515027)
ran `9d3d4d5`: Ubuntu succeeded; Windows failed the CRLF subtest's reread and
subsequent shutdown. Its target terminal category is `storage_unavailable`,
`error_kind=storage`, `error_code=5`, during dispatch. The requester is still
alive and eventually times out waiting for its response.

That diagnostic branch accepts only `sqlite3.Error` and obtains the number from
`sqlite_errorcode`. Thus **5 is `SQLITE_BUSY`**, not `ERROR_ACCESS_DENIED`.
Real SQLite contention reproduces `sqlite3.OperationalError`,
`sqlite_errorcode=5`, `sqlite_errorname=SQLITE_BUSY`; there is no filesystem
`errno` or `winerror` on this exception.

The old snapshot did not contain a storage component, request operation, stack,
or competing transaction owner. It cannot uniquely establish whether the first
failure belonged to the preceding save commit or the next read, nor identify
the precise hosted lock-holding thread. In particular, a dispatch terminal event
does not prove the source-file read raised the exception. The defects below are
established from code and deterministic reproductions, not a claim to have
recovered missing hosted thread history.

## Dispatch trace and reproduced failure chain

The exact-byte test does the following for LF, then CRLF:

1. Write explicit UTF-8 bytes; read and hash them remotely.
2. Set Edit Ask; request a save; deny it through C4; verify unchanged bytes.
3. Reread; set Edit Allow; save against the exact original hash.
4. Verify intended disk bytes and returned revision; immediately reread.

Immediately before the reported failing reread is a successful save response.
Previously that response was sent **inside the effect/receipt transaction**,
before SQLite commit. A commit failure could therefore occur after the requester
had already received success and queued its reread.

The target read path is C3 `Channel.process` → `RemoteStudioService.receive` →
device identity/permission lookup → shared-workspace lookup → receipt lookup →
workspace/permission JSON lookup → bounded Studio file read → Activity audit →
TLS response. Device records, Connect permissions, shares, receipts, and
Activity occupy the same Connect SQLite database. Workspace metadata and local
Studio permissions are JSON stores; editor bytes and checkpoints are files.
C4 approval state is in memory, but approval decisions also write Connect
Activity to that SQLite database.

Three defects were reproduced:

* Even read-only Studio requests used `BEGIN IMMEDIATE`, unnecessarily competing
  for the single writer reservation with an Activity transaction.
* On failure, `receive()` opened another audit writer outside the protected
  handler. Its second `SQLITE_BUSY` escaped into C3 and closed the authenticated
  channel. Replaying the previous commit's `receive()` and `invalidate()` with
  a real Activity writer held by Events captured `OperationalError / 5 /
  SQLITE_BUSY` at the recovery-audit transaction's `BEGIN IMMEDIATE`.
* `LocalNetwork.finished()` then invalidated file receipts using the ordinary
  ten-second transaction timeout. The same writer prevented that reservation.
  The worker had set its stop flag but had not closed its socket. The existing
  four-second network shutdown join correctly reported `shutdown_timeout`.
  Releasing the writer let the original worker finish, proving the dependency.

The competing writer in the reproduction is a real C4-style Activity insert
held on its own connection. A separate regression holds a real read snapshot
through save-receipt commit, proves `SQLITE_BUSY` at commit, and prevents a false
success acknowledgment. These do not mock SQLite, TLS, authority, or file bytes.
The hosted Windows log shows longer setup/operation intervals. Timing can expose
this contention window, but its exact lock duration was not captured. The defects
reproduce on Linux and require no Windows access-denied condition.
No evidence attributes the hosted failure to antivirus, CRLF, or handle reuse.

## Repair and authority policy

Studio read/tree/list/status admission uses enforced read-only transactions.
Consequential claims and effect receipts retain write transactions and durable
replay protection. Receipt commit now precedes success acknowledgment.

A fresh read-only transaction rechecks peer identity, permission revision,
workspace scope, and policy before returning a result. That snapshot pins
permission commits through the existing bounded TLS write. `Channel.check()`
reuses this exact transaction only inside a thread-local context; it still checks
stop/shutdown, pairing, fingerprint, and certificate validity. Opening a second
reader here can deadlock behind a pending writer waiting for the first snapshot
to finish. A real SQLite PENDING-writer regression proves reuse works, another
thread cannot borrow it, and no snapshot survives its transaction or revocation.

No writer transaction is held over response transmission. The bounded read-only
transmission snapshot is intentionally retained to prevent a permission commit
from racing source disclosure; it is not a cached authorization grant. Existing
save/launch effect reservations remain authoritative. No new awaits, retries,
sleeps, WAL migration, or busy-timeout increase were introduced.

Ordinary read/denial Activity writes happen separately, after releasing the
authorization transaction, with the existing quarter-second storage budget.
Their failures enter bounded private diagnostics and cannot escape into C3.
Consequential receipts and their audit remain atomic. Failure to claim or consult
workspace authority returns a bounded failure and performs no effect or source
disclosure. A failure of C3's current paired-identity check still fails closed
and closes the channel. This separates non-authority audit availability from
authority decisions without permitting an operation on stale authority.

If a file-receipt invalidation cannot acquire storage, it uses the same bounded
quarter-second budget and immediately fences that peer's file admission in
memory. The existing file cleanup worker settles the pending invalidation after
storage becomes available. Receipt commit precedes clearing the fence, under the
same file lock. Replacement channels cannot resume old transfers or admit new
ones while fenced. At most 256 peer entries are retained; overflow conservatively
fences all file peers. Shutdown stops the cleanup worker; remaining inert state
is handled on reactivation or by existing startup reconciliation. Completed
Inbox artifacts are preserved. C3 can remove authority, close its socket, and
join independently of a blocked receipt writer. Genuine worker/peer retirement
timeouts remain errors.

## Private diagnostics

Storage failures record fixed component/operation labels, namespace
(`sqlite`, `win32`, `posix`, or `application`), an allowlisted exception class,
`sqlite_errorcode`, allowlisted `sqlite_errorname`, `errno`, and `winerror`.
Provenance is attached at transaction, share, receipt, Activity, permission,
workspace-file, and checkpoint boundaries. Each channel retains at most four nonterminal
storage failures as well as its first terminal cause. No SQL statement, error
message, absolute path, file/prompt content, or credential is recorded.
Tests explicitly distinguish simulated WinError 5 from SQLite code 5, including
a failing checkpoint operation that leaves the target source unchanged.

## Validation

All Python checks use the project venv. Existing repository Node and .NET
toolchains are used; no missing tools were installed. Repetitions are independent
executions, not retries counted as passes.

| Check | Result |
| --- | --- |
| Exact LF/CRLF read, denied save, valid save, revision and reread | 100/100 passed |
| Real held Activity writer / exact remote read | 100/100 passed |
| Malformed EOF retirement | 50/50 passed |
| Remote EOF retirement | 50/50 passed |
| Live disconnect / immediate reconnect | 50/50 passed |
| Old worker / replacement isolation | 50/50 passed |
| Repeated disconnect | 50/50 passed |
| Genuine disconnect timeout | 50/50 passed |
| Audit failure preserves channel | 50/50 passed |
| Authority storage failure diagnostics | 50/50 passed |
| Dispatch storage failure / socket retirement with writer still held | 50/50 passed |
| Deferred file invalidation / replacement admission fence | 50/50 passed |
| Network module | 49 passed: 45 NetworkTests, 2 WireTests, 2 DiscoveryTests |
| C7/C8 focused suites | 62 passed |
| Exact portable Connect workflow command | 240 passed |
| Full Python discovery | 1,094 tests: 1,086 passed, 8 platform skips |
| Frontend | 50 passed in 14 files |
| Typecheck / lint / production build | Passed |
| Repository Python compilation | 656 sources passed |
| Literal whole-tree compileall | Existing ignored PySide6 Jinja-template syntax error |

The Ubuntu EOF and immediate-reconnect fixes remain covered locally. Hosted
Windows success requires a later authorized push and is not claimed here.
Full discovery emitted the existing 26-uncollectable-object shutdown warning.
