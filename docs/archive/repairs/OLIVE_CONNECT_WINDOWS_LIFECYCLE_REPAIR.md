# Windows portable three-process lifecycle repair

## Root cause and evidence

The failing three-process acceptance calls **B.revoke(A)**, then waits for
**A.snapshot().devices[0].live.state == 'offline'**. B's revoke clears B's local
reconnect intent, not A's. A's original authenticated channel exits and publishes
offline, but A's existing reconnect worker may already be eligible to retry.
The retry is rejected by B's committed revocation and publishes `failed`. That
state is accurate telemetry, with no authenticated channel and no latency; it
is not a cached online channel. The test was waiting for an intermediate state
that its process-pipe/snapshot round trip could miss entirely.

A deterministic real-TLS regression chooses this order without sleeping:
connect/ping, remote revoke, join original worker, verify offline, execute the
eligible automatic reconnect, join its rejected worker, verify failed with no
encryption/latency and retained local reconnect intent. This establishes why
waiting longer for offline cannot repair the assertion.

Two related cancellation races were found while tracing that path:

1. Local disconnect removes the channel and publishes offline; the finishing
   worker then takes `finished()`'s no-current-channel branch and overwrites it
   with failed. An event-held completion regression failed before the fix with
   `AssertionError: 'failed' != 'offline'`.
2. Disconnect between an authenticated ready result and `connect()` returning
   could be followed by the caller re-arming reconnect. A gated Future regression
   covers that ordering, including an explicit retry allowance. Without the
   cancellation guard in the exception/retry branch, all five repetitions of
   that regression failed because the cancelled call retried successfully.

Native Windows is not available on the development host. The reported hosted
failure is evidence of the missed-state race; its original snapshots/thread
schedule were not captured, so no native reproduction or specific Windows
socket defect is claimed. Different process scheduling and snapshot/pipe costs
can put observation after the reconnect transition. This order is reproduced
explicitly on Linux, including with spawned processes under CPU contention.

## Component and lifecycle audit

- The temporary C2 pairing listener is a separate socket/thread. The test waits
  for both durable completions and listener removal before starting C3. C3 ping
  succeeds before revocation, so the failed predicate concerns C3 telemetry,
  not the earlier pairing listener.
- C3's channel worker owns final socket close. `Channel.close()` first sets stop
  and calls `shutdown(SHUT_RDWR)`; authenticated TLS uses nonblocking sockets
  and bounded select waits. This implementation and its descriptor-reuse
  protection remain unchanged. No cross-thread final-close workaround is added.
- `DevicesWorkspace.snapshot()` obtains telemetry through the current
  `LocalNetwork.status()`. It does not retain a cached channel; stopped channels
  have no encrypted flag or latency. Trust metadata stays in the repository and
  online/offline telemetry remains in memory.
- An inbound remote revoke cannot edit the other desktop's trust/reconnect
  settings. Ordinary loss still permits the existing three bounded automatic
  retries. No reconnect policy is disabled globally.
- Local disconnect/revoke immediately remove channel authority and local retry
  intent and publish offline; completion is asynchronous. Pending requests fail
  during owning-worker cleanup. At worker completion, socket close, pending
  settlement, audit release and worker removal have all happened.
- Disable/close retain their existing bounded joins of owned workers. The
  three-process fixture now sends a successful shutdown acknowledgement only
  after service close returns, and requires child exit code zero. Forced cleanup
  after failure is not counted as a passing shutdown.

## Changes

Product: `olive/connect/network.py` records explicit local cancellation on each
affected channel under the network lock. Late cleanup cannot overwrite the
local offline/revoked state. Authentication-state publication rechecks stop while
holding that lock. Connect completion cannot re-arm a stopped channel; a locally
cancelled attempt cannot proceed to its allowed explicit retry.

Fixture: `tests/test_connect_desktop_pairing.py` captures the actual connected
worker and exposes a test-only `await_closed` command that joins its natural
exit without signalling it. Disconnect/revoke commands join the affected workers
before replying and verify retry intent was removed. The parent first proves
remote revoke closed A's original worker and fresh authentication fails; only
then does it explicitly disconnect A to require stable offline telemetry.
It also runs three disconnect/reconnect cycles, immediately checks three
snapshots per cycle, checks disable, and validates shutdown acknowledgements.
Only fixed lifecycle flags are included in timeout diagnostics; no identity,
pairing code, certificate, key or payload is logged.

Regressions: `tests/test_connect_network.py` adds four tests for remote revoke
followed by rejected reconnect; late worker completion after explicit disconnect;
cancelled connect completion with retry allowance; and raw channel close followed
by snapshot/disable/worker joins. Existing collision, automatic reconnect,
permission/revocation, replay and SQLite contention tests remain enabled.

No existing timeout increased and no sleep/retry/skip was added to mask failure.
Fixture joins use the existing four-second aggregate channel shutdown budget and
monotonic timing. `4997d2e` read-only lookups, 0.25-second database bounds and
writer-serialized authority are untouched. The workflow retains both Ubuntu and
Windows and `fail-fast: false`. C5 behavior and C6/file transfer are unchanged.

## Validation

Local Linux, Python 3.14.7; real loopback TLS and multiprocessing `spawn`:

| Check | Result |
| --- | --- |
| Original three-process baseline | Passed once; no native Windows reproduction claimed |
| Deterministic pre-fix local disconnect regression | Failed: worker cleanup overwrote offline with failed |
| Three-process target repetitions | 30 normal + 10 with one CPU shared with a busy process |
| DesktopPairingTests + DesktopProcessAcceptance repetitions | 10 normal runs (100 tests) + 3 constrained runs (30 tests) |
| NetworkTests repetitions | 5 normal runs (160 tests) + 3 constrained runs (96 tests) |
| Complete portable Connect command | 139 passed |
| Full Python discovery | 993 run: 982 passed, 11 existing platform/toolchain skips |
| Frontend | 41 passed across 13 files |
| TypeScript / ESLint | Passed |
| Renderer / Electron main and preload builds | Passed |
| Source compilation | Passed |

The full Python skips include three unavailable C# toolchain checks in addition
to the eight platform/environment skips in the supplied earlier baseline. No
skip was added or changed. Node 24.21.0 bundled with Playwright executes the
package scripts' entry points because Node/npm are absent from shell PATH.

As in the previous repair, literal repository-wide `compileall -q .` encounters
the pre-existing PySide6 Android Jinja `__init__.tmpl.py` inside `.venv`. Source
compilation excludes installed dependency trees; the exact command also passes
in a tracked-source snapshot without those trees.

Hosted Ubuntu/Windows confirmation requires a subsequent authorized push. This
repair does not push, merge, tag or release.
