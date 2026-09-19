# User-authorised target-only inspection — 11 September 2026

Baseline verified clean at `a829732fbdfed5acf47e6f1f4535bf62913c1526`. The latest user authorisation selected the local acceptance target for process/title/accessibility inspection only, with no text entry, button invocation or input-permission broadening. Notepad was not launched; the later target-specific instruction steered this check.

**Result: blocked during target attachment, before any UI Automation observation. Not an inspection pass or full M2 acceptance.** No production changes or further target attempts were made to obtain a pass.

The unchanged target script was inspected again: it creates an entry/button/label and performs no file, account, network or communication operations. An isolated Electron profile was created; only its Desktop Control enabled switch changed. Keyboard and mouse remained Deny, screen/vision off, UIA on and unknown-app policy Ask. No Allow rule was added; the real profile was untouched. The harness refused an administrator token.

The actual Electron launch button/native file-action route supplied the specifically authorised script path. File-picker selection was automated by the harness; the Python launch, approvals and subsequent attachment request were real. No backend launch record or target result was injected. The harness never invoked DMDO approval controls. Two real launch approvals were presented (script execution and application launch); the backend subsequently returned launch reference `ceeb3580e76e4efca7b065d935adab5b` and created the target process tree.

`Attach launched target` failed before an inspection approval/observation appeared. The captured Electron state has no desktop session, an empty observation and no active operation. Its alert reads: “The request could not complete. Review its inputs, permissions, or current file version.” The exact underlying exception is not exposed by this public error; the cause remains unresolved. Do not attribute this to unsupported Tk controls: UIA compatibility was not tested. The harness initially waited for observation rather than detecting that alert; a second connection to this same owned Electron test instance captured the alert and invoked Stop. Closing the instance later produced a secondary harness page-closed error, which is preserved separately from the original attachment failure.

| Item | Evidence |
|---|---|
| Target identity for cleanup | Exact script arguments; launcher PID 30524 under this session's backend; child PID 13000 under that launcher; creation identities checked; target HWND 2163462, title `DMDO M2 local acceptance target`. This is owned-process cleanup evidence, not DMDO UIA evidence. |
| Accessible controls | None observed through DMDO. |
| Text/button actions | None; the verification label was not invoked or inspected. |
| Stop | Actual preload Stop path set `stopped=true`, `active=false`. No in-flight input existed, so this is latch evidence, not active-input interruption. |
| Cleanup | WM_CLOSE sent only to the exact owned target after ancestry/script/window checks. Both target processes exited, no remaining target process. Owned Electron and Python backend closed; relevant PIDs absent. |

Ignored evidence: `artifacts/ui-review/M2-target-inspection-live/result.json`, `attach-diagnostic.json`, `attach-state.png`, `stopped.json`, `stopped.png`, `cleanup.json`. Only the owned Electron page was captured; no unrelated windows were enumerated for content or screenshot. The original earlier blocked attempts remain unchanged in their separate directories.

The final M2 desktop gate remains pending. Prior accepted visual/Research work and automated results remain accepted; this live failure is separate. No tag, Qt removal, default switch, framework/model change or M3 work.
