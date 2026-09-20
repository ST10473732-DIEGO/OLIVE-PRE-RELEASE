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
