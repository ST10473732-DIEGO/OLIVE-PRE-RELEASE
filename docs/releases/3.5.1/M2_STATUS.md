# M2 status ? awaiting user review

The owned-window readiness race is reproduced and corrected. The final narrow M2 desktop input check passed through real Electron/Python/generic UIA, with delegated one-action approvals, observed verification, Stop and verified cleanup. **M2 is ready for final user sign-off.** See [M2_OWNED_WINDOW_RESOLUTION.md](M2_OWNED_WINDOW_RESOLUTION.md). No M3 or release approval is implied. Earlier checkpoint notices below are historical.

The delegated Qt input session launched its target but stopped at owned-window resolution before UIA or input. Exact exception and cleanup are recorded in [M2_DELEGATED_INPUT.md](M2_DELEGATED_INPUT.md). Earlier successful read-only inspection remains accepted for its demonstrated target; full M2 input acceptance is still pending.

A standard-control Qt target and isolated capture setup are prepared for the final input check; live initiation/approval is pending. Accepted read-only inspection remains accepted. See [M2_ACCESSIBLE_INPUT.md](M2_ACCESSIBLE_INPUT.md). No input pass or M2 sign-off is claimed.

Live owned-target attachment and read-only UIA inspection passed; 12 accessibility records returned. Text/button verification and full M2 desktop acceptance remain pending because the intended controls were not semantically resolvable. See [M2_LIVE_INSPECTION.md](M2_LIVE_INSPECTION.md). Earlier blocked attempts remain historical evidence.

Attachment diagnostic/capture defects are corrected; the original attachment cause remains unknown pending a coordinated instrumented inspection. No new live target was inspected. See [M2_ATTACH_DIAGNOSIS.md](M2_ATTACH_DIAGNOSIS.md). No inspection/full desktop pass is claimed.

Narrow owned-launch corrections are implemented; the original desktop attempt remains blocked evidence. Target-only attachment and guarded child identity now have automated coverage. Live target interaction awaits new user initiation; see [M2_OWNED_LAUNCH.md](M2_OWNED_LAUNCH.md). No M3 or release approval.

Final desktop attempt: explicit single-session permission received; stopped on target PID mismatch before interaction. Owned child verified for cleanup only; actual Electron Stop latch passed. Live desktop acceptance remains BLOCKED, not awaiting initial permission. See [M2_DESKTOP_ACCEPTANCE.md](M2_DESKTOP_ACCEPTANCE.md). Research correction and ordinary Electron result accepted; no M3 or release approval.

M2 close-out visual corrections at cab8b76 are accepted. Final functional checks remain separate; see [M2_FINAL_CHECKS.md](M2_FINAL_CHECKS.md). Desktop live acceptance awaits explicit user initiation. No M3 or release approval.

M2 visual direction is accepted for continuation; functional sign-off is pending the focused [M2 close-out](M2_CLOSEOUT.md). The original action mappings and historical evidence below remain intact. No M3 interfaces or release tag.

Implementation checkpoint **b3554c3** preserves approved M1 **d355f94**. The remaining existing workspaces and Chat/Studio actions are connected in Electron. See [M2_REVIEW.md](M2_REVIEW.md) for the per-feature report, current evidence, placement differences and limitations; [M2_PARITY.md](M2_PARITY.md) tracks individual actions.

Fresh results: **597 Python tests**, **12 frontend tests**, **21 ordinary Electron scenarios passed** (one opt-in local-model scenario skipped in that ordinary run), **49 Qt legacy smoke checks** and **17 Qt experience checks**. Compilation, TypeScript, lint and build passed. The separate opt-in live Ollama stream/cancel/retention scenario also passed on the current build. Qt experience printed two existing style-order warnings. No M3 interface, release tag, default launcher switch or Qt removal.

Actual Electron screenshots and a 22.04-second navigation/save/test/retention recording are under ignored `artifacts/ui-review/M2/`; the review ZIP and exact final commit are identified in its review note. Stop at the M2 review gate. The material below is historical evidence for earlier increments, not the current outstanding-work list.

## Historical increment reports

# M2 implementation status — connected increments

## Studio increment — 2026-09-11

Studio now has a compact secondary-action menu, save-all, explicit dirty-tab choices, workspace search/line navigation, Git tools, RunSession diagnostics and Monaco markers, checkpoints/IDE handoff, reviewed command output/cancellation, and isolated local app previews. Its assistant uses the same NaturalLanguageOrchestrator/CapabilityRouter as Home and Chat, with bounded untrusted file selection context. Save/test output and Monaco buffers retain the corrected M1 behaviour. Chat project metadata also updates the shared context entity rather than leaving a stale project name.

Fresh full Python check: **588 passed**, compilation passed. The updated frontend TypeScript, lint, component tests and build pass. The full ordinary Electron regression passed **16 scenarios**, with **1 opt-in live AI scenario skipped**. Component tests: **11 passed**. No live model claim is added by this increment. Studio tests include cancelling a real approval with no file creation, approving a harmless print/sleep command then stopping it before its final fixture write, and retaining output across Home/Studio. Preview tests launch a real temporary Python HTTP server, verify its owned listener, reject privileged bridge/Node access and unrelated requests, and close the view/run. Screenshot capture uses the actual DMDO window because renderer capture excludes WebContentsView. This is local fixture evidence, not external-account or arbitrary-code sandbox certification.

Preview implementation follows Electron's [WebContentsView](https://www.electronjs.org/docs/latest/api/web-contents-view) lifecycle; the view is explicitly destroyed on close, renderer/backend loss, resize, minimise or an approval. A reusable isolated in-memory session is cleared between previews. No CDN, preload, model-generated frontend code, default launcher change or Qt removal. Capture uses [desktopCapturer](https://www.electronjs.org/docs/latest/api/desktop-capturer), retaining only the DMDO window artifact. Remaining limits include child-process-tree handling inherited from native execution, full Git/rollback UI acceptance, large-snapshot stress, all feature handoffs and final M2 visual/action review.


## Task workspaces and Chat increment after 43b83f7

Chat now adds options for title/notes/project, full-message search, summaries/cancellation, branches, attachment import/removal, image removal, source inspection, export and deletion. Real isolated Electron checks passed for branches/search/draft retention/metadata/project/export/document import/removal/deletion, and Python tests passed for project/pending-context guards and summary cancellation preserving the previous summary. The native picker alone is stubbed to fixture paths. Drag/drop, additional attachment variants and live summary generation remain pending.

Desktop Control is also connected as an M2 preview: natural objective through the shared language core, real status/verification, Stop/reset, and the existing UIA/application/browser/media/clipboard/visual/consequence tools under Developer Details. Native upload/export dialogs retain path authority. Capture previews accept an owned capture ID, never a renderer path, and return a bounded image. The application does not enumerate or inspect the desktop merely by opening the route.

Migration audit found the old Qt process-ID assumption in focus handoffs. The pipe runtime now binds the supervising Electron ancestor (including Windows venv launcher ancestry), checks its original lifetime, and uses it in existing UIA/browser/visual guards. Qt keeps its original same-process default. Unrelated foreground applications remain rejected. This does not claim protection from every malicious same-user process or establish live input reliability. Cancelled operations now receive an explicit protocol cancellation response.

Desktop evidence: four isolated bridge tests, seven BrowserFocus tests and two supervisor identity tests passed (13 total); real Electron Stop/reset/disabled-operation/navigation and Research denial scenarios passed after the supervisor/protocol change. Actual empty and disabled-inspector screenshots were visually inspected. No real desktop observation, clipboard access, application launch, browser action, send or installation was performed. Populated control/provider tests, broader per-action validation and final screenshots remain pending.

Agent now presents the existing structured task history, steps, changed files and validation, with pause/resume/cancel controls. Objectives enter the same NaturalLanguageOrchestrator as Home and Chat after workspace/project validation. Research now has question/depth/project selection, history, findings/citations, source/evidence inspection, pause/cancel/resume, report/source saving, website scope/learning, saved sources and quarantined downloads. Website learning and downloads reuse the registered tools; no network permissions were relaxed. Export destinations come from a native dialog. The approval drawer names the action and selected URLs using trusted repository records; its original action fingerprint is unchanged.

These are M2 previews, not full action acceptance. Research and Agent drafts/history survive navigation. Runtime snapshots include actual active request identities so renderer recovery does not label running work Ready. Resource updates are bounded without waiting for a continuous event stream to stop.

Fresh checks for this increment: full Python suite **578 passed**, compileall passed, TypeScript/lint/build passed and **11 frontend tests passed**. Full ordinary Electron suite: **14 passed, 1 opt-in live AI scenario skipped**. The separately recorded live Ollama scenario from the first increment was not repeated here. These results cover the current task workspaces and Chat options; remaining Studio and action-level acceptance work is not claimed complete.

Actual Agent/Research screenshots are in the ignored M2 artifact directory. Research findings/sources and Agent partial history are explicitly illustrative fixtures, not live execution or web evidence. The real Electron/Python denial test leaves Knowledge unchanged; an inert fixture download is read without network or execution. Research preparation cancellation is tested against the real controller with only configuration deliberately held by a test event. External website learning, downloads, model-based Agent execution, active pause/resume UI and per-action failure coverage remain pending. No M2 approval, release tag, default switch or Personal Core UI is claimed.

Next: complete cross-feature handoffs, remaining action acceptance and the M2 review package. The first increment evidence below remains historical to that increment.

M1 at `d355f94` is explicitly user-approved as the visual/interaction baseline. Branch: `development/3.5.1-electron-experience`. The worktree was clean at that baseline. M2 is **in progress**, not complete or awaiting final milestone approval. No release tag, launcher switch, Qt removal or Personal Core interface work has occurred.

## Implemented in this increment

- Core handoff projection now lives in a decorative portal outside the scrollable rail. Rail/page scrolling and focus remain enabled. Real Electron tests check every animation frame for horizontal rail overflow at 1440×920, 1366×768 and 640×480, with reduced motion on/off and rapid navigation.
- Settings has a readable searchable category sidebar, existing generation/retrieval/research/OCR/editor preferences, local model roles, permission/scoped rules, desktop policies, backup/restore/export controls and Diagnostics. Python validates settings and excludes unknown persisted fields from renderer snapshots/events without deleting them. Monaco consumes saved editor preferences.
- Native file dialogs own import/export/backup/restore/workspace paths. Renderer payloads cannot provide those paths through a generic call. Desktop emergency stop also has a narrow main-process operation independent of the ordinary request queue.
- Projects supports search/create/detail, real linked record inspection, Chat/Studio handoff and native workspace approval/trust selection. Remaining relationship operations are explicitly pending.
- Memory supports local search/filter, CRUD, source inspection, suggestions and export. Full suggestion/export UI acceptance is still pending.
- Knowledge supports local source import, health/index state, re-index/relink/remove, jobs and retrieval inspection. Web-source/website-learning migration remains pending.
- Backup uses SQLite's backup API for a committed WAL-consistent snapshot. Restore rejects unsaved Studio buffers, concurrent protocol work, language interpretation, active validation and model benchmarks; after restore, new work is blocked until restart.

All Spaces labels the new routes as **M2 previews**. Existing services remain authoritative; no new frontend keyword router or inference provider was added. Lightweight visited views retain state; Monaco retains its existing bounded model lifecycle. Domain records stay in the existing repositories and formats.

## Fresh evidence

Baseline rerun: 552 Python tests, 9 frontend tests, compilation, TypeScript, lint and production build passed before implementation.

Current Python suite: 560 tests passed, with Qt fallback tests included and no skips. `python -m compileall -q .` passed. TypeScript, lint, 11 frontend tests and production build passed. The complete ordinary Electron suite passed 10 scenarios and skipped its opt-in live AI scenario; that live Ollama stream/cancel/state-retention scenario was then run separately and passed. Targeted M2 scenarios and current screenshots are under `artifacts/ui-review/M2/` (ignored).

Evidence classification:
- Unit / isolated integration: `tests/test_m2_settings.py`, existing backend/security/natural-language/Qt tests, `desktop/tests/m2-contracts.test.ts` and existing frontend tests.
- Live local: actual sandboxed Electron plus supervised Python in temporary profiles; settings persistence and invalid-value rejection, Monaco preferences, Project/Memory creation, document import and lexical retrieval with an unavailable Ollama endpoint, source removal without deleting the original, navigation/renderer reload, existing Studio saves/tests/conflicts/cancellation and real Ollama streaming.
- Mocked boundary: only native picker choices in fixture import/OCR tests. Domain operations use real Python services and repositories. No live desktop manipulation or external send occurs.
- Visual inspection: actual Settings, Diagnostics, Projects, Memory and Knowledge screenshots. Empty/populated data is isolated and named Fixture. Capture is not a frame-rate benchmark.
- Not tested live: model downloads/benchmarks, permissions granting real desktop input, external Research/SMTP/IMAP/accounts, full cross-feature migration, packaging, clean-machine install, multiple monitors/DPI variants. Some local action-level UI checks remain pending in M2_PARITY.md.

## Remaining M2 work

Agent, Research and Desktop Control frontend migration; Knowledge web-source/learning/download tools; complete Project relationship handoffs; outstanding Chat attachments/branches/project management and Studio Git/checkpoint/command/preview actions; full action-level cancellation, state, approval and keyboard coverage; complete M2 visual/recording package and security/performance validation. The 125-action initial ledger also requires the documented manual audit of Qt local-only menus/actions.

Settings/Projects/Memory/Knowledge were connected before the higher-risk task/control work to establish and validate the shared data/permission boundary. This sequencing does not remove or defer any mandatory M2 obligation. Native Identity, Contacts, Calendar, Tasks/Reminders and Mail remain mandatory later work under the master brief; their new interfaces have not been started.

No claim of M2 completion, final release approval, universal intelligence, reliable vision localisation, interactive PTY/LSP/debugger support or clean-machine packaging is made.
