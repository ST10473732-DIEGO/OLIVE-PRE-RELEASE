# C8 hosted portable repair

Scope: the two reported Ubuntu/Windows Connect failures on
`feature/olive-connect-c8`. No C9, new capability, toolchain installation, push,
merge, tag or release. The supplied hosted Linux portable success is separate
from the failing Connect matrix. No new hosted result is claimed here.

## Ubuntu: remote channel retirement raced immediate reconnect

The C7 rate-budget test disconnected A from B and immediately connected A to B
again. `LocalNetwork.disconnect()` already joined A's owning channel worker and
removed A's reconnect intent. That was not a completion barrier for B's worker:
B could still be finishing a request before observing the old socket's EOF.
Its old channel remained in B's map with `stop` unset.

The replacement connection could authenticate over fresh TLS and reach
`LocalNetwork.adopt()` before B observed EOF. Both the old and replacement
channels had the same direction, so the existing collision protection correctly
rejected the replacement with `connection_collision`. Depending on scheduling,
the caller could see the connection die before `connect()` finished its final
live-channel check, producing the reported
`connection_failed_check_pairing_certificate_and_firewall` wrapper. This was not
a certificate, firewall or Remote AI budget failure.

Evidence:

- The original test passed 50 unforced repetitions locally, demonstrating that
  repetition alone does not reliably expose the scheduling window.
- An event-gated real-TLS reproduction held B after sending a response. A's old
  disconnect returned while B's worker was alive and `stop` was false. B then
  rejected the fresh channel with `connection_collision`.
- Running the same controlled schedule with the transport source from the
  pre-C8 C7 commit `ab7f60a` also reproduced the exact public hosted error.
- The new peer-retirement regression fails against that pre-C8 transport and
  passes with this repair. `disconnect()` and `adopt()` were unchanged between
  C7 and C8. C8's Studio invalidation hook is inactive in the C7 fixture because
  no Studio runtime is attached. This is an inherited lifecycle race.

### Synchronization repair

`olive/connect/network.py` now makes ordinary, completed-channel disconnect a
worker-owned half-close barrier:

1. Remove local channel authority and reconnect intent, and reject pending work.
2. Finish channel-scoped authority/file/inference/Studio invalidation.
3. The socket's owning worker shuts down its write direction, notifying the peer
   reader of EOF. No TLS or application operation runs afterward on that worker.
4. Wait for peer transport closure, discarding only in-flight encrypted bytes.
   The peer publishes EOF after its authority cleanup, so the old live channel
   cannot collide with the subsequent explicit connection.
5. Close the descriptor, remove the worker from the registry and join the local
   worker before returning.

The peer wait uses the existing two-second `WRITE_TIMEOUT`; the existing
four-second disconnect join bound is unchanged. Missing peer closure produces
`disconnect_timeout` after local cleanup, never a false completion. Revocation,
shutdown, failed/incomplete handshakes and explicit `wait=False` retain abrupt
cancellation. Only the owning worker closes its descriptor. Worker registry
removal now follows descriptor closure, including exceptional cleanup paths.

No retry, sleep, larger timeout, relaxed collision rule, new wire message or
approval bypass was added. C2/C3 authentication and per-peer C3/C7 rate buckets
are unchanged. Immediate reconnect does not wait for the inference provider to
release its model; the strengthened C7 test checks rate rejection first, then
checks model ownership release separately.

Changed regressions:

- `tests/test_connect_network.py`: hold peer retirement with events; verify
  disconnect remains pending with local authority already removed; release the
  gate and immediately reconnect without polling or retry. Also prove a stalled
  peer returns `disconnect_timeout` with local worker/socket cleanup complete.
- `tests/test_connect_inference.py`: assert old local worker/socket retirement,
  target authority removal and identical admission/transport budget objects
  across reconnect, while still allowing only one provider invocation.
- `tests/test_connect_files.py`: its intentional peer-cleanup gate now runs
  disconnect in a future. Assert disconnect is pending and the file-admission
  lock is still held, release cleanup, then require disconnect completion. The
  previous synchronous harness could not release its gate under the stronger
  completion contract; its original admission-protection assertion is retained.

## Windows: universal-newline translation in the assertion

`StudioService.open_file()` already reads bytes, decodes UTF-8 without newline
translation and hashes the original bytes. The shared fixture's `write_text()`
can produce CRLF on Windows. The failing assertion used `Path.read_text()` with
universal-newline handling, which translated those bytes to LF before comparing
them to the exact remote text. A synthetic CRLF file reproduces this mismatch
on Linux as well; it is a test assertion defect, not a production normalization
defect.

Only `tests/test_connect_studio.py` changes for this failure. The permission
change between claim and effect now compares raw disk bytes to the remote text's
UTF-8 encoding and verifies SHA-256 over those exact bytes.

An additional real-TLS regression explicitly writes synthetic LF and CRLF UTF-8
files, including non-ASCII text. For each variant it verifies:

- read text re-encodes to the exact original bytes;
- the revision equals SHA-256 of those bytes;
- Ask followed by Deny leaves both bytes and the next read/revision unchanged;
- a successful revision-checked save writes exactly the intended editor bytes;
- the returned save revision and subsequent read match those exact saved bytes.

No production Studio read, save, hashing or newline behavior changed. Files are
not rewritten to the host's native newline convention.

## Validation

All Python commands used `.venv/bin/python`. Full discovery also put the already
installed .NET SDK on PATH; no toolchain was installed. Measured local results:

| Check | Result |
| --- | --- |
| Original unforced C7 rate-budget test before repair | 50/50 passed; deterministic gating was needed to expose the race |
| Pre-C8 C7 gated reproduction | Reproduced stale live channel, collision and exact hosted public error |
| New peer-retirement regression against pre-C8 C7 source | Failed as expected |
| Repaired C7 reconnect/rate-budget test | 50/50 passed |
| Event-gated peer-retirement/reconnect regression | 50/50 passed |
| C3 suite plus targeted C7 and exact-byte checks | 42 passed |
| Requested C7/C8 inference and Studio suites, including process tests | 55 passed |
| Exact `connect-portable.yml` unittest command | 222 passed |
| Full Python discovery | 1,076 tests: 1,068 passed, 8 platform skips |
| Frontend | 50 passed in 14 files |
| Typecheck / lint / production build | All passed |
| Repository Python source compilation | All 653 sources passed |
| Literal whole-tree `compileall -q .` | Existing ignored PySide6 Android Jinja template syntax error only |
| Diff whitespace / branding / secrets / user-data review | Passed |
| New hosted Ubuntu / Windows runs | Not performed; no push |

The full Python suite emitted the existing warning about 26 uncollectable objects
at shutdown. The whole-tree compilation exception remains the installed
`PySide6/scripts/deploy_lib/android/recipes/PySide6/__init__.tmpl.py` template,
which contains Jinja rather than valid Python. Vendor files were not changed.

Repair commits: `3933711` (transport and C3/C6/C7 regression synchronization),
`29f7a10` (test-only exact-byte and LF/CRLF repair). No CI test was skipped or
retried to mask a failure. The initial portable check identified the intentional
C6 gate's synchronous-call assumption; after repairing that harness, the complete
portable command passed with all original file-admission assertions retained.

The repair must still be pushed by an authorized user and verified on both
hosted runners before claiming Ubuntu/Windows hosted success. No push, merge,
tag, release or C9 work occurred during this repair.

## Final Ubuntu follow-up: EOF already consumed before disconnect

At the start of this follow-up, the user reported hosted Windows Connect green
and one Ubuntu failure in
`NetworkTests.test_malformed_request_unknown_capability_and_message_type`, during
`disconnect_and_join()`. All hosted C8 Studio tests passed. The changes below
preserve the active-peer retirement barrier from `3933711`.

### Exact failing transition

The first two test payloads are malformed JSON and an unknown capability. B's C1
receiver returns a rejection with no decoded request ID. A cannot correlate that
response and closes with `invalid_response`. Thus **A closes first** in these
cases; the test name does not imply B's worker closes first. The last payload, an
unknown frame kind, instead fails framing on B. Neither malformed path gains
authority or executes a request.

The failing cleanup schedule was reproduced with real TLS and Events:

1. A closes and joins its worker; its descriptor is closed and authority removed.
2. B's TLS receive has consumed A's EOF and raised
   `SSL.SysCallError(-1, 'Unexpected EOF')`, but B has not yet processed that
   exception in `Channel.run()`. The regression holds this exact boundary.
3. B still has `stop == false` and owns its old channel-map entry. Explicit
   disconnect captures this exact worker and sets `graceful_disconnect`.
4. B processes EOF, removes its authority and finishes cleanup. Before this fix,
   it did not retain the observed EOF in `peer_closed`.
5. Its redundant `shutdown(SHUT_WR)` returns Linux `ENOTCONN` (107). Instrumented
   real sockets confirmed this native error. `drain_disconnect()` classified it
   as failure, leaving `peer_closed == false` even after B's worker joined.
6. Disconnect therefore raised `disconnect_timeout`. This was a false timeout
   caused by discarded terminal state, not an elapsed wait for a live peer.

Both the malformed-response and remote-close event-gated regressions failed on
the previous implementation with that exception. Unforced baseline repetitions
did not reliably expose the scheduling window.

### State repair and generation safety

Only `olive/connect/network.py` changes production behavior. EOF, TLS close and
known native disconnect/reset errors now latch `peer_closed` on the exact
`Channel` object. After authority cleanup, an already-observed terminal state
satisfies the peer-retirement barrier without trying to obtain another EOF.
`ENOTCONN` also counts as terminal state if the kernel retired the established
socket before TLS observed it. Other socket errors still fail; a live peer that
does not retire still produces `disconnect_timeout`.

No timeout changed. No sleep, reconnect retry, catch-and-ignore, protocol
exception downgrade or unconditional success path was added. The existing
worker join remains the completion signal. EOF state is never shared by peer ID:
a fresh channel starts with `peer_closed == false`. Existing exact-object checks
in `finished()` still prevent an old worker from removing a replacement channel.
Concurrent repeated disconnect callers join the same graceful retirement rather
than issuing another local read shutdown, which could masquerade as peer EOF.
Malformed frames continue to close their channel, and C2/C3 security, explicit
disconnect intent, revocation and C6–C8 invalidation remain unchanged.

`tests/test_connect_network.py` adds real-TLS regressions for consumed EOF during
malformed cleanup, consumed EOF after remote close, repeated post-retirement
disconnect, concurrent repeated disconnect, and delayed old-worker cleanup while
a replacement is already live.
The existing live-disconnect/reconnect and genuinely-stalled-peer tests remain
unchanged. Events and worker joins select the failing transitions.

Final local checks use the project venv and the already-installed toolchains:

| Check | Result |
| --- | --- |
| Malformed cleanup test repetitions after final repair | 100/100 passed |
| Live-disconnect/immediate-reconnect repetitions | 50/50 passed |
| Genuinely stalled peer timeout repetitions | 50/50 passed |
| Concurrent repeated disconnect repetitions | 20/20 passed |
| Complete network module | 43 passed: 39 NetworkTests and 4 wire/budget tests |
| Exact portable Connect workflow command | 226 passed |
| Full Python discovery | 1,080 tests: 1,072 passed, 8 platform skips |
| Frontend | 50 passed in 14 files |
| Typecheck / lint / production build | All passed |
| Repository Python source compilation | All 653 sources passed |
| Literal whole-tree compileall | Same existing ignored PySide6 Jinja-template syntax error |
| Diff whitespace / branding / secrets / user-data review | Passed |

Production changes are confined to `olive/connect/network.py`; regressions are
in `tests/test_connect_network.py`, and this document records the evidence.
Full discovery emitted the same existing 26-uncollectable-object shutdown warning.
This repair is not a claim of hosted Ubuntu success; a later authorized push
must verify that result. No push, merge, tag, release or C9 work is included.

## Windows unexpected close investigation after 7f27d41

**Status: diagnosis remains incomplete; this change adds evidence collection and
regressions, not a claimed Windows transport fix.** The supplied failures occur
before inference/Studio dispatch. Their public `connection_closed` errors do not
identify the original worker exception. Neither failure reproduced in 100 local
runs each. The configured origin's accessible Connect Actions history contains
C7 and earlier runs, but no C8 run for `7f27d41`; the failing run URL was requested.
Native Windows validation remains outstanding. No speculative behavior change,
timeout increase, retry, or suppression of a failure is included.

### Established state and ownership facts

* `Channel.check()` emits `connection_closed` when that channel's stop event or
  its network's shutdown event is set. It does not consult EOF, descriptor values,
  retirement history, or a peer-level retirement marker. The supplied traceback
  cannot distinguish which stop event was set or what originally caused it.
* A worker's exception/finally path sets its own stop event before removing
  authority. The EOF additions in `7f27d41` run after a read has failed or returned
  empty, and only satisfy that same channel's retirement. They do not themselves
  initiate fresh-channel shutdown.
* EOF and graceful-disconnect state belong to individual `Channel` instances.
  Registration/removal use strong object references and `is` comparisons. There
  is no retirement lookup keyed by `fileno()`, port, numeric `id()`, or peer alone.
  Only the owning worker closes its socket descriptor, after its last TLS call.
  No handle-reuse defect was found. Distinct channels with simulated equal OS
  handles retain independent stop/EOF state and identity in a regression.
* Delayed old target cleanup was forced while a replacement TLS channel admitted
  inference and Studio Run requests. Releasing that cleanup did not remove the
  replacement, stop its job, or share its EOF. This checks the suspected ordering;
  it does not establish what occurred in the inaccessible Windows run.
* Both fixtures create independent services, identities, and profiles. Teardown
  already awaited service shutdown and network worker joins. Added assertions
  require no owned workers, listener, reconnect thread, or open captured socket
  after shutdown returns.
* Audit failure is caught, emits the existing fixed warning, and does not close
  the channel. A real-TLS regression forces audit failure then successfully pings.
  Separately, an event-gated exclusive SQLite lock proves a failed authority read
  closes the worker and is distinguishable in diagnostics. That is an injected
  diagnostic test, **not proof of the reported Windows cause**. Authority checks
  and their fail-closed behavior are unchanged.

### Private diagnostics

`olive/connect/network_diagnostics.py` assigns each channel an immutable UUID
generation for observation, unrelated to OS handle reuse. It retains a first
terminal category, phase, whitelisted error kind, and bounded numeric OS/SQLite
error code. No exception messages, payloads, paths, credentials, or source/prompt
text are retained. Channel snapshots include stop/EOF/local-intent/worker/socket
flags. A network retains at most 16 retired snapshots, returns at most four for
the requested peer, and caps its audit-failure counter at 65,535.

`tests/connect_channel_fixture.py` attaches snapshots of the requested channel
and both networks to raised C7/C8 test errors before teardown can obscure the
state. Public errors, wire frames, Activity, and Devices status are unchanged.
These diagnostics grant no authority and do not participate in connection
selection or retirement synchronization. Existing exact-object synchronization
remains authoritative; no generation-based synchronization replacement was
needed or justified by the available evidence.

### Local validation

All Python checks use the project venv; Node and .NET use the already-installed
repository toolchains. Repetitions are independent test executions, not retries.

| Check | Result |
| --- | --- |
| Reported inference test | 100/100 passed |
| Reported Studio disconnect test | 100/100 passed |
| Consumed EOF after malformed protocol | 50/50 passed |
| Consumed EOF after remote close | 50/50 passed |
| Live disconnect / immediate reconnect | 50/50 passed |
| Old worker / replacement isolation | 50/50 passed |
| Concurrent repeated disconnect | 50/50 passed |
| Genuinely stalled peer retirement timeout | 50/50 passed |
| Network module | 47 passed: 43 NetworkTests, 2 WireTests, 2 DiscoveryTests |
| C7/C8 focused suites | 57 passed |
| Exact portable Connect workflow command | 232 passed |
| Full Python discovery | 1,086 tests: 1,078 passed, 8 platform skips |
| Frontend | 50 passed in 14 files |
| Typecheck / lint / production build | Passed |
| Repository Python compilation | All 655 sources passed |
| Literal whole-tree compileall | Existing ignored PySide6 Jinja-template syntax error |

The Ubuntu EOF regression and genuine `disconnect_timeout` remain covered and
passing locally. Hosted Ubuntu/Windows success is not claimed. No push, merge,
tag, release, or C9 work was performed.
Full discovery emitted the existing 26-uncollectable-object shutdown warning.

The next hosted run captured SQLite contention during Studio dispatch. See the
[C8 storage repair](OLIVE_CONNECT_C8_STORAGE_REPAIR.md) for the deterministic
failure chain, bounded retirement repair, and exact-byte regression evidence.
