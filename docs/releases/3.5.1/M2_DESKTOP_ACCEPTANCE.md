# Final M2 desktop attempt — 11 September 2026

The user accepted the M2 visual corrections, specific Research evidence/scope correction and complete ordinary Electron result (22 passed, two documented opt-in skips, native exit 0). Only live desktop acceptance remains. Baseline verified clean on `development/3.5.1-electron-experience` at `40d83423ef366efbe67f24f08728a3a4c41da26c`.

**Result: blocked, not a live interaction pass. M2 is not ready for final functional sign-off.** Explicit user permission was received for this single target/session; approval is no longer merely awaiting user initiation. No additional scope or permanent permission was inferred.

The target script was read before launch. It creates a Tk entry, `Check text` button and verification label; it performs no file, account, network or communication operation. The isolated Electron profile left Desktop Control disabled, UIA enabled, keyboard/mouse denied and unknown-app policy Ask. These defaults were observed through the real bridge and were not broadened. No DMDO approval was requested or clicked.

| Check | Actual observation |
|---|---|
| Launch | Real Electron and target script launched in an isolated profile, with a non-administrator token. Initial sandboxed Playwright launch failed before target launch; no Electron process remained from that attempt. The subsequent sandbox exception did not elevate Windows privileges. |
| Target identity | Launcher PID 19596; target HWND 55314860, title `DMDO M2 local acceptance target`. Window PID 29368 differed from launcher PID, so the harness stopped immediately before UIA inspection. |
| Ownership/focus for cleanup | PID 29368 was subsequently verified as the launched virtual-environment Python redirector's child, running the exact target script. The exact-title window was foreground at cleanup. This read was only to verify safe cleanup, not permission to resume the test. |
| Accessible controls | Not observed through DMDO. Tk source widget declarations are not accessibility evidence. UIA compatibility remains untested. |
| Actions/result | No text entry, button invocation or manufactured target state. `Verified: DMDO local acceptance` was not observed. |
| Stop | Reopened the same isolated Electron profile solely to invoke Stop after the abort. Actual Desktop Control button set backend `stopped=true`, `active=false`; screenshot recorded. This verifies the latch, not stopping in-flight input. |
| Cleanup | Sent WM_CLOSE only after verifying exact title and membership in the owned process tree. Both target child and launcher exited; no owned target remained. Both Electron instances closed. Temporary logs/profile retained for evidence; real profile untouched. |

There is also a product scope blocker found before launch: `desktop/src/features/desktop/Inspector.tsx` requires `desktop.list_windows` before selecting a window. `DesktopController.list_windows` calls unfiltered `enumerate_windows`, reading titles and process metadata for other visible windows. The user forbids reading unrelated windows. The list was never invoked, no hidden cache was seeded, and no provider was called directly to bypass the actual Electron route. No target-only attachment entry exists in this inspector. Resolving that limitation would require a separately agreed narrow change or test scope; none was implemented here.

Evidence is under ignored `artifacts/ui-review/M2-desktop-final`: initial failure/result, owned-process cleanup, actual Stop state/screenshot, and review note. The original failure log remains intact rather than being rewritten as a success. PID/foreground observations came from an owned-launch identity guard, not DMDO accessibility inspection. No model inference, unrelated window enumeration, blind coordinates, external action or administrator token was used.

No UI/product behaviour changed. All earlier passing checks remain classified as their original runs. The 125 M2 action mappings remain intact. No release tag, default switch, Qt removal, model change or M3 work. Stop here with live desktop acceptance blocked; do not infer full M2 sign-off.
