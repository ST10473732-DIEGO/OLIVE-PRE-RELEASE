# Owned-window readiness diagnosis and bounded correction

Baseline: `03c7268218fcb4046ca8aacad3b893372a5bd95c`, clean worktree on
`development/3.5.1-electron-experience`. Prior evidence and tags are preserved.
This work does not establish the cause of the original historical attachment
error, which remains unproven.

## Actual diagnostic reproduction

One isolated session, using the unchanged reviewed
`scripts/m2_accessible_acceptance_window.py`:

- Request `1612d003-fb89-43e4-af89-a56744e23b05`.
- Launch `8de633c1944d42c9ae86494a370d012a`.
- Error `49322d75011b4b19ba676ade43ab96c1`.
- Stage `owned_identity_revalidation`, `OwnedLaunch._resolve` selection guard.
- Exact exception: `NoOwnedWindow: No eligible owned window; no target selected`.
- At 178.78 ms since the launch record, **zero** eligible windows. The two owned
  processes passed both identity checks; no executable, command or lifetime
  rejection. Three owned handles were found, all invisible. No enumeration
  exception; UIA provider reached **false**.
- Later cleanup found exactly one visible window on the same verified child:
  PID 29380, creation 1789133227.7625241, HWND 92539000. Its launcher was PID
  10344. This later observation is Win32 ownership/cleanup evidence, not UIA.

The reproduced defect is a launch-readiness race: a one-shot resolver treated
normal pre-visible startup as terminal attachment failure. This is not evidence
of a PID mismatch, incorrect visibility filter, keyboard denial or UIA defect.

The runtime handling this request had diagnostics enabled. Its protected log
was saved and the correlated file was read through the normal Windows user
procedure. The review excerpt omits private paths and contains no unrelated
window titles, text or UI trees. No raw protected file is included in the ZIP.

## Correction and guards

`OwnedLaunch` now distinguishes no window, multiple windows, process exit,
identity rejection and enumeration failure. Bounded diagnostic fields retain
request/launch correlation, elapsed time, owned filter counts and eligible
owned HWND/PID/lifetime metadata. Enumeration errors propagate; they do not
become empty results.

`owned_window_wait.py`, called by the existing `LaunchTargets.attach`, waits
within **one request**, up to five seconds, sampling at most every 50 ms.
Only an absent eligible window with no identity rejection qualifies for retry.
Each sample repeats process ownership/lifetime checks before and after
PID-filtered enumeration. Ambiguity, identity failure and process exit stop
immediately. A query deadline and readiness timeout are distinct; a provider's
own exception is preserved. Stop cancels the controller's actual attachment
task. No approval or action is replayed. First/latest resolution evidence stays
bounded in the existing launch record/diagnostic path.

Controlled tests reproduce zero-then-unique readiness, no-window timeout,
ambiguity, query exceptions, process exit/reuse, owned-only filtering and
cancellation through `DesktopController.stop`. Existing permission, focus,
unrelated-process and stale-target regressions remain.

## Delegation and evidence boundary

The diagnostic session used two reviewed one-action launch approvals, clicked
by the assistant under the user's explicit delegation. Keyboard Ask; mouse
Deny; UIA enabled; screen/vision off; no permanent Allow or real-profile change.
Stop latch was set after failure with no active input to interrupt. Both target
processes and the isolated Electron/backend/launcher lifetimes exited.

The test harness supplies the exact reviewed path to Electron's native dialog
selection callback. Chooser interaction itself is not live-tested. Launch,
actual approval buttons, bridge/controller and generic provider paths are real.
No target internals or fabricated observation are used.

Evidence: ignored `artifacts/ui-review/M2-owned-resolution-Y30yQA` (first failure,
safe diagnostic excerpt, Electron screenshot, Stop and verified cleanup).

## Actual verification: passed

Exactly one additional isolated session, recorded in
`artifacts/ui-review/M2-owned-resolution-TlFXWi`. Attach request
`72bce285-9f5a-4617-b84d-cb1476e3c120`, launch
`75e526398cd344c682f92b8d64827642`. No request failure occurred.

The first sample again had zero eligible windows, three invisible owned handles,
and two accepted process identities (186.93 ms since recording launch). The same
Attach request resolved exactly one eligible window on sample six (610.61 ms
since launch recording; 454.24 ms total resolution wait). Both process identities
still passed; five other owned handles were invisible. No repeated Attach and
no approval replay occurred.

Actual target: **DMDO M2 accessible acceptance target**, launcher PID 27124,
owned child PID 22676 / creation 1789133743.8357244 / HWND 81135706. The real
generic Windows UIA path returned 11 accessibility records, including:

| Intended control | Actual observed identity | Operation used |
| --- | --- | --- |
| Acceptance text | Edit / QLineEdit / `acceptance_text` | `set_text` |
| Check text | Button / QPushButton / `check_text` | `invoke` |
| Result | Text / QLabel / `acceptance_result`, initially Not checked | Read observation only |

DMDO entered **DMDO local acceptance** and read it back from the actual Edit
value. The status was still **Not checked** before invocation. After the actual
button invocation, the observed result element's name became
**Verified: DMDO local acceptance**. Backend session
`8a88b560-70e1-4342-952e-fbe63f107fb9` reports `completed`,
`Expected state observed`, with separately verified `set_text` and `invoke`
history. The target callback was not called by the harness.

Six actual one-action approvals were reviewed/clicked under explicit delegation:
script execution, launch, scoped inspection, keyboard input, text control and
button control. Arguments, owned identity, file fingerprints, profile and
non-remembering scope were checked. No broad Allow rule was created. Keyboard
remained Ask; mouse Deny; screen/vision off.

Stop was available and its latch was set after completion (`active: false`).
This is **not** evidence of interrupting active input. Actual attachment-task
cancellation is separately covered by the controlled controller regression.
All six recorded launcher/Electron/backend/target process lifetimes exited;
only the owned test windows received close requests.

Screenshots show the actual Electron inspection and selected invocation UI.
The scrolled invocation screenshot does not itself display the observed result
label; `verification/result.json` contains its real UIA observation and backend
verification. The expected-text input in that screenshot is not treated as proof.
No full desktop/screen capture or synthetic success image was used.

## Fresh validation and acceptance boundary

- Python: **635 passed**, including permissions, focus, ownership, bridge/security,
  diagnostics and nine new controlled resolver/readiness tests.
- `python -m compileall -q .`: passed.
- Approval/capture harness: **7 passed**.
- Frontend: **12 passed**; TypeScript, lint and production build passed.
- Ordinary Electron: **24 passed, 2 skipped, exit 0** on the final corrected code;
  two intentional opt-in
  skips are live Ollama streaming (`DMDO_LIVE_AI`) and live Agent/public Research
  (`DMDO_M2_LIVE`). Neither is relabelled as a live pass in this task.
- Qt fallback: **49 checks passed**, isolated fixture smoke harness, exit 0.
- The restricted runner could not save a DPAPI test diagnostic; the complete
  normal-user Python run passed that test. No administrator access or sandbox
  configuration change was used.

**M2I-01's narrow input criterion is passed; M2 is ready for final user sign-off.**
This demonstrates Electron → Python → generic UIA text/invocation → observed
verification for this accessible external target. It does not establish universal
application control, original Tk compatibility, all natural-language desktop
tasks or vision reliability. The historical original attach cause remains unknown.
Existing M2 visual/Research approvals and all 125 action mappings remain intact.
Read-only Output, no connected LSP/debugger, Qt style warnings, clean-machine
packaging, GPU/combined-model measurements and broader provider compatibility
retain their documented limitations. No M3, tag, Qt removal or launcher switch.
