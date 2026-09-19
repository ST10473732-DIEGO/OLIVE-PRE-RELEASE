# OLIVE 3.5.1 acceptance evidence

M4 Mail implementation, current fresh tests and classified local protocol/UI
evidence are in [M4_COMPLETION.md](M4_COMPLETION.md). SMTP independent loopback
acceptance and scripted IMAP coverage are distinguished; no live external account
or independent full security audit is claimed. Final release/packaging acceptance
remains separate. Historical checkpoint notices below retain their original scope.

M3 implementation and internal acceptance complete. M2 remains accepted; Mail/transport remain M4. No release tag, Qt removal or default-launcher switch. See [M3_COMPLETION.md](M3_COMPLETION.md). Earlier checkpoint notices below remain historical.

The owned-window readiness race is reproduced and corrected. The final narrow M2 desktop input check passed through real Electron/Python/generic UIA, with delegated one-action approvals, observed verification, Stop and verified cleanup. **M2 is ready for final user sign-off.** See [M2_OWNED_WINDOW_RESOLUTION.md](M2_OWNED_WINDOW_RESOLUTION.md). No M3 or release approval is implied. Earlier checkpoint notices below are historical.

The delegated Qt input session launched its target but stopped at owned-window resolution before UIA or input. Exact exception and cleanup are recorded in [M2_DELEGATED_INPUT.md](M2_DELEGATED_INPUT.md). Earlier successful read-only inspection remains accepted for its demonstrated target; full M2 input acceptance is still pending.

A standard-control Qt target and isolated capture setup are prepared for the final input check; live initiation/approval is pending. Accepted read-only inspection remains accepted. See [M2_ACCESSIBLE_INPUT.md](M2_ACCESSIBLE_INPUT.md). No input pass or M2 sign-off is claimed.

Live owned-target attachment and read-only UIA inspection passed; 12 accessibility records returned. Text/button verification and full M2 desktop acceptance remain pending because the intended controls were not semantically resolvable. See [M2_LIVE_INSPECTION.md](M2_LIVE_INSPECTION.md). Earlier blocked attempts remain historical evidence.

Attachment diagnostic/capture defects are corrected; the original attachment cause remains unknown pending a coordinated instrumented inspection. No new live target was inspected. See [M2_ATTACH_DIAGNOSIS.md](M2_ATTACH_DIAGNOSIS.md). No inspection/full desktop pass is claimed.

Latest user-authorised target-only inspection launched the target but failed during attachment before UIA observation. Stop and owned cleanup verified; see [M2_TARGET_INSPECTION.md](M2_TARGET_INSPECTION.md). This is not a live inspection pass; M2 desktop acceptance remains pending.

Narrow owned-launch corrections are implemented; the original desktop attempt remains blocked evidence. Target-only attachment and guarded child identity now have automated coverage. Live target interaction awaits new user initiation; see [M2_OWNED_LAUNCH.md](M2_OWNED_LAUNCH.md). No M3 or release approval.

Final desktop attempt: explicit single-session permission received; stopped on target PID mismatch before interaction. Owned child verified for cleanup only; actual Electron Stop latch passed. Live desktop acceptance remains BLOCKED, not awaiting initial permission. See [M2_DESKTOP_ACCEPTANCE.md](M2_DESKTOP_ACCEPTANCE.md). Research correction and ordinary Electron result accepted; no M3 or release approval.

M2 close-out visual corrections at cab8b76 are accepted. Final functional checks remain separate; see [M2_FINAL_CHECKS.md](M2_FINAL_CHECKS.md). Desktop live acceptance awaits explicit user initiation. No M3 or release approval.

M2 visual direction is accepted for continuation; functional sign-off is pending the focused [M2 close-out](M2_CLOSEOUT.md). The original action mappings and historical evidence below remain intact. No M3 interfaces or release tag.

> **M2 review checkpoint:** Implementation `b3554c3` is submitted for M2 user review. Fresh results, actual Electron captures, per-feature parity and remaining limitations are in [M2_REVIEW.md](M2_REVIEW.md). Stop before new Personal Core interfaces; no release tag, Qt removal or default switch. Earlier checkpoint notices below are historical.


> **M2 continuation:** The user explicitly approved corrected M1 at `d355f94` as the visual/interaction baseline and authorised M2 existing-feature migration. This supersedes the M1-awaiting-review notices below only. Full release and M3 interfaces are not approved. See [M2_PLAN.md](M2_PLAN.md), [M2_PARITY.md](M2_PARITY.md) and [M2_STATUS.md](M2_STATUS.md). All original requirement IDs remain in force.


> **Current M1 correction checkpoint, 10 September 2026:** The user recommended the Electron direction and requested focused corrections from `f4b107b`. See [M1_CORRECTIONS.md](M1_CORRECTIONS.md) for current implementation, stable M1C-01–09 obligations, fresh evidence and limitations. Updated M1 awaits user review; no M2/M3 work, Qt removal, launcher switch or release tag is authorised by this checkpoint. Historical evidence below remains historical.


> **Recovery checkpoint, 10 September 2026:** The material below is recovered
> historical documentation. Its test totals, security audit and approval claims
> are not fresh acceptance. See [RECOVERY_REPORT.md](RECOVERY_REPORT.md) for the
> current verified state. The latest brief requires a new visual-review stop.

Evidence classes: UNIT, MOCKED INTEGRATION, LIVE LOCAL, LIVE EXTERNAL, VISUALLY REVIEWED, NOT TESTED. User approval is separate.

## Fresh baseline

| Check | Evidence | Result |
| --- | --- | --- |
| Source/test compilation | `.venv/Scripts/python.exe -m compileall -q dmdo tests scripts main.py` | Passed |
| Python suite | `.venv/Scripts/python.exe -m unittest discover -s tests -v` | 523 passed |
| Qt smoke | `scripts/qt_desktop_smoke.py --output .experience-351/baseline-qt` | 49 passed |
| Original interpretation | `scripts/natural_language_evaluation.py --limit 37` | 37/37; no actions executed |
| Expanded / compound | Same harness `--broad --limit 145` / `--compound --limit 4` | 145/145 and 4/4; interpretation only |

## M1 required live evidence

Passed LIVE LOCAL: Electron launch/Enter/Home/All Spaces/Chat/Studio; actual Python/Ollama stream and cancellation from Home; route/draft retention and renderer refresh; approved temporary workspace; Monaco edit/hash save/conflict comparison; actual compile/unit-test/Run output; dark/light/reduced motion; keyboard entry/palette; screenshots and actual screencast recording. Four opt-in live-local tests pass. Detailed evidence and measurement limitations are in [M1_REVIEW.md](M1_REVIEW.md).

Final UNIT / existing integration regression: 531 Python tests; 49 Qt smoke checks; 5 frontend component/contract tests; targeted compilation, strict TypeScript, lint and production build pass. The original language evaluations were rerun at baseline, not misrepresented as new live action tests. npm dependency audit reports zero known findings after patching the transitive sanitizer.

NOT TESTED: hard backend/renderer crash during an active consequential action, full process-tree kill guarantees, complete offline native domains, actual OS DPI/multi-monitor accessibility, sustained GPU/VRAM/cold-machine performance, production packaging/clean-machine execution and final release parity. Native Personal Core remains unimplemented. Renderer-refresh draft retention does not prove complete crash recovery.

Use isolated profiles and synthetic content only. Screenshots of fixtures must say so. No external sends. A UI opening does not prove action parity. M1 user approval: **not given**. Final visual approval: **not given**. Packaging/clean-machine acceptance: **not tested**.

## User-approved M1 direction and Studio revision

See [USER_REVISION.md](USER_REVISION.md): direct Studio consent, Java/local libraries and named project folders are implemented and live-local tested. 536 Python, 49 Qt, five frontend and five Electron tests pass. Broader natural-language autonomy, supported Discord delivery and full IDE/package workflows remain open. No release acceptance or final visual approval is inferred.
