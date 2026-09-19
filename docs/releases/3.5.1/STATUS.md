# OLIVE 3.5.1 - current identity

**Windows completion baseline:** `final/windows-stable-baseline` preserves the
latest combined workspace design and accepted OLIVE GO ancestry. The normal
Windows launcher now opens Electron. Current repairs, classified acceptance
results and limitations are in [WINDOWS_STABLE_BASELINE.md](../../WINDOWS_STABLE_BASELINE.md).
The notices below describe earlier checkpoints and do not supersede that record.

**Design branch `design/olive-complete-ui-refresh` (not merged): complete
post-entry interface redesign.** Presentation-only change to the Electron
renderer on top of the M4-complete baseline `b1fee22`: labelled navigation spine
with the live Core state, compact workspace headers, shared design tokens and
primitives, redesigned Home/Chat/Studio/Mail/Calendar/Contacts/Tasks/Settings
compositions, scrolling feature pages and honest empty/error states. The Welcome
screen, Core renderer, green desktop icon, Python services, contracts, permissions,
schemas and Qt fallback are unchanged. Two narrow backend corrections were made
separately with regressions (readable Ollama status wording; recipients in Mail
list summaries). Fresh on the branch: 733 Python, 25 frontend, 7 harness,
37 ordinary Electron with 4 documented opt-ins, plus the opt-in live local
streaming test; compilation/typecheck/lint/build pass. Evidence, measurements,
rationale, parity and limitations: [DESIGN_REFRESH.md](DESIGN_REFRESH.md) and
[PARITY_CHECKLIST.md](PARITY_CHECKLIST.md). No version, tag, launcher-default
or Qt change; the branch awaits the user's decision. Checkpoint notices below
are historical.

**M4 implementation and internal acceptance complete.** Native local Mail,
protected optional SMTP/IMAP connections, immutable submission/recovery and native
composition are implemented. Fresh: 732 Python, 25 frontend, 37 ordinary Electron
with 4 documented opt-ins, 7 harness, 49 Qt and 12 existing local-language cases;
separate real Mail language workflow passed. Compilation/typecheck/lint/build pass.
See [M4_COMPLETION.md](M4_COMPLETION.md) for actual local versus scripted evidence,
visual review, remaining server/packaging limits and exact artifact paths.
No real accounts/data, external delivery, release tag, Qt removal, launcher switch
or next milestone. Earlier checkpoint notices below are historical.

C# console starter is available in Studio's New Project menu and verified through real local create/edit/save/run (exit 0). Welcome footer slogan and Studio implementation captions are removed; save status remains. The .NET filtered environment now supplies project-local SDK settings/cache paths. Fresh checks: 699 Python, 23 frontend and 6 focused Electron passes; compilation/typecheck/lint/build passed. See [C# details and evidence](../../STUDIO_CSHARP.md). No M4/version/tag changes.

Welcome follow-up: removed the Play/Pause control at the user's request. Welcome now rotates automatically while visible regardless of motion preferences; native hidden/minimized suspension and compact activity semantics remain. See [Core behaviour](../../OLIVE_CORE.md). No backend/data/version/M4 changes.

Core follow-up: the olive now spins around its own fixed tilted axis. The static normal preview was traced to Windows reduced motion, which remains the default. Explicit Core-only Play/Pause is available without changing Windows settings. Ordinary startup rotation was verified after opt-in. Fresh follow-up checks: 697 Python, 23 frontend and 7 focused Electron scenarios; compilation/TypeScript/lint/build passed. See [Core diagnosis and evidence](../../OLIVE_CORE.md). Earlier full-suite totals below belong to their recorded checkpoints.

Animated dot-matrix Core implementation and internal acceptance complete: shared 3D Canvas geometry, real compact activity state, reduced-motion/native visibility handling and local fallback. Fresh validation: 697 Python, 23 frontend, 7 harness, 29 ordinary Electron passes with 3 documented opt-in skips; compilation/TypeScript/lint/build passed. See [Core evidence and limits](../../OLIVE_CORE.md). M4 has not started; no version/tag/default-launcher change. This supersedes the previous ring/orb presentation only.

OLIVE was formerly named DMDO. Rebrand implementation/local acceptance is complete at source `ebe737e`: 697 Python, 18 frontend, 7 harness, 28 ordinary Electron passes (3 opt-in skips), 49 Qt checks; compilation/TypeScript/lint/build passed. Separate live local identity answered OLIVE. Packaging remains blocked by the existing missing self-contained backend artifact. M3 remains complete; M4 has not started. See [the rebrand map](../../OLIVE_REBRAND.md). Historical checkpoint text below retains its original naming. New code uses `olive`, `OLIVE_*` and `window.olive`; compatibility profiles and identities remain documented.

# OLIVE 3.5.1 checkpoint

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

Branch: `development/3.5.1-electron-experience`, based on the clean Qt checkpoint `30cfdc9`. v3.4.1 still resolves to `7007fe9`; v3.4.0 and v3.4.1 tags are untouched. No v3.5.0/v3.5.1 tag exists.

**M0 boundary/scaffold and the real M1 visual prototype are implemented. The user has approved the M1 visual direction and requested revisions; see USER_REVISION.md. Full M1-related action parity and release acceptance are not declared complete.**

Read [M1_REVIEW.md](M1_REVIEW.md) for actual screenshots, recording, measurements and exact open scope. Native Personal Core remains planned. Remaining workspace migration and Personal Core interfaces have not been built ahead of approval. Qt remains the default.

Fresh baseline: 523 Python tests, 49 Qt checks, 37/37 original paraphrases, 145/145 expanded semantic cases, 4/4 compounds. Final checkpoint: targeted compile passed, **531 Python tests**, **49 Qt checks**, **5 frontend component/contract tests**, strict TypeScript/lint/production build, **4 Electron live-local tests** including explicitly enabled actual qwen3:8b streaming. No external sends. npm audit: zero known findings after the pinned DOMPurify override.

New shared profile ownership, private protocol, approval/deduplication tests, Monaco hash save/comparison, real validation/Run output and renderer-refresh Chat draft retention are verified. No hidden Qt GUI initializes Python. No data migration or default launcher switch occurred.

## Resume precisely

1. Obtain the user's approval or requested revisions to the actual M1 visuals. Do not infer approval from these tests or this document.
2. If revisions are requested, edit the prototype only, rerun affected checks and replace actual evidence.
3. After approval, record it separately in REQUIREMENTS/ACCEPTANCE; continue M2 action parity from PARITY.md. Carry all applicable native 3.5 obligations into M3. No scope reduction is agreed.
4. Before final release, complete the lifecycle/security/performance/packaging gaps in M1_REVIEW.md, all native domains, imports/exports/backups/NL composition, final visual approval and release checks.

Launch an isolated populated preview with `scripts/launch_electron_preview.ps1`. Build/test commands are in desktop/README.md. Repository-local Node 24.21.0 was checksum-verified; it does not change the system PATH. The packaging guard refuses a missing self-contained Python artifact.

## User-approved M1 direction and Studio revision

See [USER_REVISION.md](USER_REVISION.md): direct Studio consent, Java/local libraries and named project folders are implemented and live-local tested. 536 Python, 49 Qt, five frontend and five Electron tests pass. Broader natural-language autonomy, supported Discord delivery and full IDE/package workflows remain open. No release acceptance or final visual approval is inferred.
