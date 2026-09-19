# Attachment diagnosis checkpoint

Baseline verified clean on `development/3.5.1-electron-experience` at
`61ec19db2d3d12fcd6a1fb56498d8f18e70c21c4`. Original evidence remains in
`artifacts/ui-review/M2-target-inspection-live`, unchanged. A SHA-256 manifest
of its six requested evidence files is in `artifacts/ui-review/M2-attach-diagnosis`.

**The original attachment exception is still unknown.** This checkpoint fixes
the demonstrated diagnostic and harness defects so the next coordinated live
inspection can establish the cause. It does not claim a corrected resolver or
an inspection pass. No new target has been launched or inspected in this pass.

## Confirmed failure-capture defects

The actual path is `LaunchTarget.tsx` → renderer `call` → preload UUID and
`dmdo:call` → main sender/contract validation → `Backend.request` → Python
`serve.process` → `Host.handle`/desktop routes → `DesktopController.attach_launch`
→ `LaunchTargets.attach` → `OwnedLaunch.resolve` → `inspect_target` → gateway
inspection permission/confirmation → observation tool/provider.

`serve.process` caught the exception and called `public_error`, replacing its
message with generic guidance without saving the original traceback. Main's
`Backend.receive` then retained only the public message. Backend stderr was
deliberately drained without persistence. The retained profile has no original
attachment traceback. These facts establish **why the cause was lost**, not
which ownership/Win32/permission function originally failed.

The old harness waited solely for an observation or a session review state.
The actual failure had neither a session nor an observation, so its visible
alert did not terminate that wait. Later page-close handling replaced the
primary stage/error. The original failed result is not edited or relabelled.

## Narrow changes

- Request-scoped diagnostics retain the protocol UUID through asynchronous
  dispatch and the ownership worker thread. Stages distinguish process identity,
  owned-window resolution, identity revalidation, attachment, inspection policy,
  approval and provider dispatch. The provider-reached flag changes only at the
  actual provider call boundary.
- A `request.failure` event carries safe method/stage/category/request/error IDs
  and log availability. The same error ID survives the normal error message into
  Electron. Desktop Control exposes a collapsed Attachment error details section.
- With explicit `DMDO_ATTACH_DIAGNOSTICS=1`, Windows DPAPI protects the original
  exception text and stack frame locations under the active isolated profile's
  `developer-diagnostics`. No request arguments, locals, observations or window
  contents are serialised. At most 32 encrypted files are written; existing
  files are not overwritten. No decryption/secret API is exposed to the renderer.
  Logging failure leaves the operation error intact and reports no saved log.
  This is user-bound Windows protection, not protection from every same-user
  process. The tool sandbox cannot access the normal DPAPI protection context.
- `scripts/capture_desktop_attach.cjs` replaces the old ad-hoc observation wait
  for the next attempt. It uses the actual Electron Attach button and stops at
  observation, approval pending, failure, cancellation or bounded timeout.
  First operation failure is immutable; screenshot/teardown failures remain
  separate. It neither approves requests nor invokes target controls. An
  `--observe-pending` follow-up reads the existing operation without replaying
  Attach. Stop latch evidence is not active-input interruption evidence.

Ownership rules, UIA implementation, launch hashes, permission decisions and
input policies have not been weakened or changed to obtain a pass. No evidence
yet justifies a readiness delay or a Tk/provider change.

## Coordinated inspection-only next step

The latest live scope remains inspection only. Coordinate with the user before
starting; do not interpret this document as authorisation to click approvals.

1. Start `scripts/launch_desktop_acceptance.ps1 -AttachDiagnostics` as the normal
   Windows user. This creates an isolated profile and opens Electron only. The
   optional diagnostic launcher enables a temporary loopback developer capture
   port, never the default launcher. Close this instance after review.
2. In this isolated profile only, the user enables Desktop Control if disabled.
   Keep keyboard/mouse Deny, screen/vision off. Open Developer Details, choose
   Python script, and select the inspected `scripts/m2_desktop_acceptance_window.py`
   through the native chooser. The user reviews legitimate launch approvals.
3. After the actual launch is recorded, invoke the capture helper with the
   printed isolated profile, a **new** output directory, and `--user-initiated`.
   It requests target-only attachment through the actual Electron control.
4. On approval pending, the helper records and returns without auto-approval or
   Stop. The user reviews the scoped inspection request. A subsequent capture
   with `--observe-pending` records the existing request, not a new attachment.
5. On explicit failure, inspect only that error ID's protected local diagnostic.
   Reproduce the demonstrated cause in a focused test before changing the
   failing layer. Do not repeat the same failing request unchanged.
6. On observation, verify the owned target and actual accessible controls; no
   text entry or invocation. Capture only Electron, request Stop, then close only
   the verified owned test processes and record cleanup separately. The helper
   intentionally leaves windows for this explicit review/cleanup step.

Typing, Check text, full desktop acceptance and M2 sign-off remain pending.
Accepted visuals/Research remain accepted; no M3, tag, Qt removal or default switch.

## Fresh validation

Results and classifications are recorded in the ignored diagnosis package.
The new Python tests exercise controlled exceptions and real user-context DPAPI;
the new ordinary Electron scenario exercises a real disabled-policy bridge
rejection, not target inspection. Harness state-machine tests are unit tests.
Live inspection and the complete new capture workflow remain untested pending
coordination. Historical target Stop and cleanup evidence remains historical.

The first complete ordinary Electron run had 23 passes, two opt-in skips and a
recording-helper failure in the Studio scenario: an outstanding
`Page.screencastFrameAck` rejected after CDP detached. The helper now removes its
frame listener and awaits outstanding acknowledgements before detaching, and
reports acknowledgement failures instead of leaving an unhandled rejection.
The focused Studio rerun passed with its original functional assertions intact.
One preceding targeted command used the wrong working directory and failed at
fixture setup before Electron launched; it is not application failure evidence.

This work is not an independent security audit. Existing read-only Output,
unconnected LSP/debugger, Qt style warnings, clean-machine packaging, unmeasured
GPU/combined-model performance and broader provider limitations remain in scope
for later acceptance, not newly claimed passes.

Final fresh results: 625 Python tests passed (25.114 s); compileall exit 0;
12 frontend tests passed; TypeScript, lint and production build passed;
3 harness unit tests passed; 49 controlled Qt fallback checks passed.
Final complete ordinary Electron run: **24 passed, 2 skipped, exit 0** (3.2 min).
The opt-in skips are live Ollama Chat (`DMDO_LIVE_AI`) and actual Agent/public
Research (`DMDO_M2_LIVE`), neither requested for this narrow diagnosis pass.
The earlier failed full run and focused rerun remain separately reported above.
No live external test, target observation, typing, button invocation or full
Desktop Control acceptance pass is claimed.
