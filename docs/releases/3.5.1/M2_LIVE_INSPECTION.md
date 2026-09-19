# Live target attachment and inspection

**Attachment and read-only inspection passed. Full desktop acceptance remains
pending.** The historical attachment exception did not recur; its original
cause remains unproven. No speculative resolver, permission or UIA fix was made.

Baseline: `0a0c24abfcfa85e75bfadc743adeca77bc2f0043`, clean branch
`development/3.5.1-electron-experience`. The user explicitly initiated this
isolated session. Later they delegated handling the test approvals; by the next
read, the inspection approval had already completed and a real observation was
present. The assistant did not click any DMDO approval in this attempt.

## Actual result

| Item | Evidence |
|---|---|
| Request | `89cc3f42-021c-4aa5-b968-c84d61c2d976`; exactly one Attach request in captured activity |
| Owned launch | `acfdf312f40640638fd70172c181525a` |
| Inspection approval | `534187e8-c0be-48d3-ad68-5e44064ceb7b`, `desktop.inspect_application`, no remember/Allow rule |
| Target | DMDO M2 local acceptance target; window PID 4856; HWND 10946754; process creation 1789128882.8555706 |
| Ownership | Backend PID 15500 → reviewed launcher PID 22200 → window child PID 4856; exact script and creation identities checked |
| Terminal outcomes | First capture: approval pending. Existing observe-pending capture: observation. Attach was not replayed. |
| Provider | Real `windows_uia` observation, 12 accessibility records, not truncated |
| Error | None in this attempt; no failure event/error ID/exception or diagnostic file expected |
| Diagnostics | Actual owned Python runtime environment confirmed enabled with the correct isolated profile; no protected file was decrypted or exposed |
| Policies at Attach | enabled/UIA on; keyboard/mouse Deny; screen/vision off; unknown application Ask |
| Stop | stopped=true, active=false. This proves a latch, not interruption of active input. |
| Cleanup | Verified owned target received WM_CLOSE; target launcher/child, isolated Electron and both backend redirector/runtime processes exited |

The first preflight found screen observation on and unknown-app Allow. It set
Stop without submitting Attach; the user corrected the settings. A subsequent
preflight found two historical launch records, but only one target process tree
alive and the newer reference selected in Electron. The helper's single-record
assumption was corrected to use that explicit selection. Unknown, duplicate or
wrong-script selections fail closed. Product ownership and authorisation checks
are unchanged; no record or observation was injected.

## Observed limitation

The returned tree contains a named top-level window and system controls, two
unnamed panes, two unnamed Image records and an unnamed Button with Invoke.
No accessible Edit control or named `Check text` control was returned. The
selected TkChild pane has no supported actions. The TitleBar reports set_text,
which is not evidence of an editable acceptance field. No target text or button
action was attempted, and no coordinate fallback or other application was used.

This is evidence about this target/provider observation, not a universal claim
about Tk or UIA. The next useful work is an accessibility-compatible acceptance
fixture or a demonstrated, narrowly scoped provider correction, followed by the
separate text/button verification. Do not infer full M2 sign-off from inspection.

## Evidence and validation

Ignored evidence: `artifacts/ui-review/M2-attach-live-20260911-bf68110e`.
The compact review ZIP includes redacted structured results, cleanup, and two
actual Electron screenshots (inspection result and observed-control details).
Earlier failed packages remain unchanged and retain their blocked status.

Fresh: four harness unit tests passed, including selection with historical
launches, rejection cases and observe-pending. Node syntax passed. Python
compileall and the full 625-test suite passed. No frontend/product implementation
changed, so the previously accepted 24-pass/two-opt-in-skip Electron suite,
12 frontend tests and 49 Qt checks are historical, not newly rerun totals.
The live Electron Attach/observe-pending route above is separate actual evidence.

The initial cleanup call in the tool sandbox could not validate the recorded
window and stopped before sending WM_CLOSE. The same guarded cleanup succeeded
in the normal interactive Windows session, explicitly refusing administrator
execution. No Codex sandbox configuration was changed, and this did not involve
protected-log access. No raw private diagnostics are included in the review ZIP.

No release tag, M3 work, Qt removal, default-launcher change or visual redesign.
