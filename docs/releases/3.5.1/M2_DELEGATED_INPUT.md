# Delegated local input session — blocked at attachment

Baseline `5f8ae2298a879a85e2eec0150956b09f5e75c469`, clean worktree on
`development/3.5.1-electron-experience`. The user expressly delegated matching
DMDO approval clicks for one isolated session and this exact Qt target.

**No input pass.** One target was launched in one isolated profile. Two matching
launch approvals were exercised by the assistant under delegation, not clicked
manually by the user. Attachment failed before inspection approval or UIA. No
text entry, Check text invocation, or result verification occurred.

## Captured underlying exception

- Request: `6ea13130-563c-4991-96fe-cfda0a71e581`.
- Launch: `cb3d05aab5764bf4aac1267a9f3a2086`.
- Error: `d64824ae54a84e608dd6b63bf4d4be6b`.
- Category: `LookupError`.
- Stage: `owned_identity_revalidation`; provider reached: **false**.
- Exact message: **Owned window is unavailable or ambiguous; no target selected**.
- Failing function: `dmdo/desktop/owned_launch.py`, `OwnedLaunch.resolve`, line 81
  at this baseline: the `len(matches) != 1` guard.
- Protected diagnostic saved: **true**. The redacted excerpt contains only this
  test's IDs, exception and stack frame names/locations. No raw encrypted log or
  unrelated application content is included in the compact review ZIP.

This identifies the failing guard but does not distinguish zero matching windows
from multiple matches. Attach began about 190 ms after the target launcher's
creation. Later cleanup found one verified visible owned window. Those timings
and later metadata do not establish the match count at failure. No readiness
sleep, identity relaxation or provider rewrite was added speculatively. The
historical attachment error remains separately unresolved; this is new evidence,
not proof of its original cause.

## Approval and harness evidence

The original fixture was re-inspected unchanged. The isolated profile enabled
Desktop Control/UIA with keyboard Ask, mouse Deny, screen/vision off and unknown
application Ask. No permanent Allow rule or real profile change was made.

The harness supplied only the reviewed script path to Electron's file-selection
callback; actual launch, approval buttons, backend dispatch and ownership checks
were real. The native chooser interaction itself was not live-tested.

An initial validator comparison rejected matching Windows path case aliases in
the launch hash map. It approved nothing and launched no target. Stop cancelled
that pending launch; the first result was preserved. The test-only validator was
corrected to compare Windows path keys case-insensitively, retaining exact hashes
and rejecting conflicting aliases, extra paths, changed arguments and wider
permissions. The same isolated Electron/profile session continued. It then
approved exactly `terminal.execute` and `system.open_application` through the
actual one-action buttons after checking arguments and fingerprint stability.
There was exactly one Attach request; it was not retried after failure.

No production permission engine, resolver, provider, database or target callback
was changed. The test validator is not a production authorisation provider.

## Stop and cleanup

Actual preload Stop returned stopped=true, active=false. This is latch evidence,
not active input interruption. No UIA controls were observed in this session.

Cleanup-only metadata verified target launcher PID 24420 and window child PID
13956, under this backend, with the exact script and process creation identities.
The sole later visible target window was HWND 19466690, title
`DMDO M2 accessible acceptance target`. PID filtering preceded window-title reads;
no unrelated titles or trees were inspected. WM_CLOSE closed only that target.

Playwright's process handle was cmd launcher PID 27900, not the Electron browser.
The first cleanup guard rejected that assumption without sending a close message.
The actual Electron child PID 27596 and its creation/parent identity were then
verified; its single window was closed. Target PIDs 24420/13956, backend PIDs
27904/7952, Electron PID 27596 and launcher PID 27900 all exited. The supervising
test harness also finished. Cleanup errors never replaced the attachment error.

The exact protected test log was read with a fixed normal-user local helper,
which refused administrator execution. No Codex sandbox configuration was
changed, and no decryption/secret API was added to Electron or the renderer.

## Status and next step

Evidence: `artifacts/ui-review/M2-delegated-input-nco7W9`. Earlier failed attempts,
the successful Tk inspection and its observed limitations remain separate.
Current Qt field/button accessibility and the final input criterion remain
untested because this attempt did not reach UIA.

Next: capture zero-versus-multiple matching-window evidence at the failing guard,
reproduce the demonstrated condition, and fix only that condition before another
input attempt. Do not claim M2 ready for sign-off. No M3, release tag, Qt removal,
default-launcher change, dependency installation or visual redesign.


## Fresh checks

626 Python tests passed (25.382 s); compileall passed. Seven Node harness tests
passed, including exact delegated scope and the observed Windows-case hash
regression. These are automated tests, separate from the blocked live session.
No production frontend/backend behaviour changed, so the full ordinary Electron,
frontend and Qt fallback suites were not unnecessarily repeated. Their previously
accepted results remain historical. This report is not an independent security
audit or a desktop input pass.
