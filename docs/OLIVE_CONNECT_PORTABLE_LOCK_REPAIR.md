# Connect portable SQLite lock repair

## Cause and reproduction

The malformed-message test treated an empty `LocalNetwork.channels` map as
completed teardown. `LocalNetwork.finished()` removes the channel first, then
writes its closing audit, and only afterwards removes it from `workers`. The
test could start its next connection while that old worker owned the database
writer slot. `DesktopDeviceService.device()` unnecessarily requested the same
slot with `BEGIN IMMEDIATE` for a SELECT. After 0.25 seconds it could raise the
reported `sqlite3.OperationalError` before connection setup started.

The deterministic regression pauses the actual old channel worker inside its
closing audit, after an INSERT and before commit. Events coordinate the holder
and test thread. It proves the channel map is empty while the worker is alive
and the write transaction remains open. Before the production fix this fails at
`device() -> transaction() -> BEGIN IMMEDIATE`, matching the reported stack.
After the fix the device, paired-identity and paired-device reads all complete
while the audit remains held; releasing and joining teardown permits reconnect.

The hosted stack does not identify its lock holder, so the specific hosted
schedule cannot be proved retrospectively. The above sequence is reproduced,
not an assumption that Ubuntu is slow. Runner scheduling or commit I/O can
expose the existing overlap past the short lock bound; this explains why ordinary
local runs passed. No evidence establishes a Windows-specific failure.

## Transaction and ownership inventory

| Phase | Database access / ownership |
| --- | --- |
| Fixture setup | Three separate temporary profiles; repository initialization, local identity and pairing transactions finish before networking starts. |
| Network enable | Identity initialization completes on the calling thread; listener starts afterwards. |
| Listener | Accepts sockets; creates owning channel threads. No database transaction in the accept loop. |
| Connect / reconnect | Device and paired-identity lookup on the calling or reconnect thread; previously reserved the writer slot. |
| TLS setup / channel checks | Paired-device snapshots for certificate pins; repeated current paired-identity lookups on channel workers. Previously reserved the writer slot too. |
| Connection lifecycle | Started, authenticated and closing audit transactions write on channel workers. Each has the existing 0.25-second lock wait. |
| Malformed request | Decode rejection writes a rejection audit on the receiving peer. An unsolicited response closes the sending peer's channel; invalid message type closes at framing. `_execute` must never run. |
| Valid requests | Durable claim and execution each use `BEGIN IMMEDIATE`, with current authority checks in both. Execution serializes with permission/revocation writes. |
| Closing channel | Map removal precedes closing audit; worker removal follows audit completion. An empty map does not mean the database has been released. |
| Fixture teardown | Service close stops listener/reconnector and joins workers before temporary-profile cleanup. The missing synchronization was between operations inside the test. |

Each repository context creates, commits/rolls back and closes its own SQLite
connection on the invoking thread. No connection is shared across threads, and
there is no evidence of a leaked connection or a previous test's profile owning
this test's database lock. Automatic reconnect could introduce additional
workers during the malformed-message test; that test now clears reconnect
intent before deliberately breaking each channel.

## Fix and security boundaries

- Add an explicit repository read-only mode: `PRAGMA query_only=ON` plus `BEGIN`.
  Use it only for `device()` and `devices()` snapshot lookups. Connections still
  close at context exit; there is no persistent snapshot or permission cache.
- Keep the default `BEGIN IMMEDIATE` for mutations, audit, durable claims,
  execution and C5 authority transactions. Request authorization is rechecked
  inside the writer transaction. Reading committed state during an uncommitted
  revoke cannot authorize execution outside that serialization.
- Join both fixture-owned channel workers, under an aggregate monotonic
  four-second budget, before the next malformed-test connection. Joins occur
  outside network locks. Production disconnect and reconnect semantics are
  unchanged.
- Keep the 0.25-second database wait unchanged. Exclusive locks still fail
  boundedly. No retry, sleep, timeout increase, journal/schema change, skipped
  test or relaxed authority check is introduced.
- Set portable matrix `fail-fast: false`; Ubuntu and Windows remain mandatory
  independent jobs. No push, merge, tag or release is part of this repair.

Three regressions cover the live closing-audit overlap, bounded `SQLITE_BUSY`
under an exclusive second connection, and read-only enforcement plus visibility
of committed revocation and rejected subsequent dispatch.

## Local verification

Python 3.14.7, repository virtual environment, real loopback TLS. Socket tests
need interface/socket access outside the restricted execution sandbox.

| Check | Result |
| --- | --- |
| Before fix: targeted test | 20/20 passed without injected contention |
| Before fix: NetworkTests | 3 runs, 78/78 passed |
| Before fix: deterministic closing-audit regression | Failed with the reported SQLite lock stack |
| After fix: targeted test | 100/100 passed |
| After fix: NetworkTests | 10 runs, 280/280 passed |
| Constrained: one CPU shared with a busy process | Targeted 30/30; class 3 runs, 84/84 passed |
| Exact portable Connect workflow command | 135 passed |
| Full Python discovery | 989 run, 978 passed, 11 existing environment/platform skips |
| Frontend Vitest | 41 passed in 13 files |
| TypeScript / ESLint | Passed |
| Vite renderer and Electron main/preload builds | Passed |
| Repository source compilation | Passed |

The full suite's three additional skips relative to the supplied baseline are
the installed C# debugger, netcoredbg and OmniSharp integration checks: those
toolchains are unavailable in this execution environment. No skip was added.
Node 24.21.0 bundled with Playwright runs the package scripts' equivalent entry
points because `node`/`npm` are absent from the shell PATH.

The literal `python -m compileall -q .` was attempted and fails solely on the
pre-existing PySide6 Android Jinja `__init__.tmpl.py` under `.venv/site-packages`.
Compilation excluding third-party `.venv` and `desktop/node_modules` passes.
The source-only checkout compilation also runs the exact `compileall -q .`
command without installed dependencies inside the source tree.

These are local Linux results, not a claim that a new hosted Ubuntu/Windows run
has completed. Hosted matrix confirmation remains for the next authorized push.
C6/file transfer and C5 record-sync semantics are unchanged.
