# M1 focused corrections — 10 September 2026

Starting checkpoint: `f4b107b66458278c6fe238518eec13a9d7217df8`, clean worktree on `development/3.5.1-electron-experience`. Existing release tags were preserved. The user recommended continuation of the Electron visual direction, requested these focused corrections, and explicitly withheld completed-migration/final-release approval. **Updated M1 remains awaiting user review. M2/M3 have not started.**

## Corrections and evidence

All items below are mandatory M1 review corrections. Tests use temporary profiles/workspaces; review artifacts are ignored, not application data committed to Git.

| ID | Correction and implementation | Fresh evidence | Status / limitation |
| --- | --- | --- | --- |
| M1C-01 | Short-window Home spacing/card heights; shared growing Home/Chat input (`GrowingComposer`, `responsive.css`) | Electron `m1-review`: first complete recent row inside the initial 1366×768 window; input grows with multiple lines | Implemented and live checked; long drafts/pinned lists still scroll normally |
| M1C-02 | Save/reconcile acknowledgements use a separate status line. Output channels keyed by RunSession/validation ID and workspace (`studioOutput`, `Studio`, `App`) | Actual Python tests → Monaco edit → Save → Home → Studio retains OK/exit output; reducer tests isolate workspaces and bound history | Implemented; 12 renderer channels, 150k characters per text channel; 8 recent backend validation records (active validations retained) with 12k retained output characters each; older output is explicitly truncated |
| M1C-03a | Hierarchical explorer with directory icons, relative basenames, full path tooltips, indentation, expand/collapse and roving tree keyboard controls (`Explorer`) | Unit ordering/collapse; Electron arrow-key focus and hidden descendants; Python and Java open/edit regressions | Implemented; existing bounded approved-workspace tree service is reused |
| M1C-03b | Validation identity/cancellation event reaches `RunService.wait_cancellable`; Stop only enabled for supported active work | Live delayed Python test stopped before its completion marker; unit stale cancellation ID rejected; Run Stop uses actual run state | Implemented; stopping cannot undo effects completed before cancellation |
| M1C-04 | Distinct Connections plug icon, All Spaces grid, descriptive tooltips, selected route semantics and expansion labels (`App`) | Actual screens; Electron keyboard/navigation checks | Implemented; one primary window retained |
| M1C-05 | Available Electron / temporary Qt fallback / not implemented labels (`SpaceCards`) | Unit markup and actual All Spaces; planned cards disabled, fallback cards use information affordance | Implemented; fallback information does not launch a second writer automatically |
| M1C-06 | Backend-readable approval action/target/content/scope/consequence; technical JSON collapsed (`presentation.py`, `ApprovalSummary`). Structured validation task and step status (`TaskResult`) | Actual approval screenshot; native cancelled task and completed/cancelled/not-attempted steps; nested action mutation rejected before execution | Implemented for the M1 connected actions; comprehensive Agent and domain result interfaces remain M2/M3. Old synthetic approval/partial-result screenshots remain fixtures |
| M1C-07 | Optional Review tests invokes the existing permission/confirmation pipeline; normal direct Test/Save still avoid redundant approval | Actual backend approval denied via Cancel; all temporary workspace file names/hashes identical afterward. Separate direct local tests succeed; running test Stop verified | Live local, no mocked approval or outcome in new review evidence; no external actions |
| M1C-08 | Operational helper/explorer/toolbar text 13px, xterm output 14px; compact task summary and more usable output height | Actual 1440×920 and 1366×768 screens; existing 640×480 through 1920×1080 resize checks | Visually checked by agent; final user judgement pending; no accessibility certification |
| M1C-09 | Reproducible capture test, screenshots, recording, review notes and ZIP | `desktop/tests/e2e/m1-review.spec.ts`; ignored `.experience-351/m1-corrections/review` | Updated review package; no release tag or default launcher switch |

## Verification

- `python -m compileall -q .`: passed.
- `python -m unittest discover -s tests -v`: **552 passed**, 17.032 seconds. Unit/mocked integration plus the isolated real subprocess cancellation regression. No real desktop control or external messages.
- TypeScript strict checking, frontend lint and production build: passed. Frontend component/contract tests: **9 passed**.
- Electron: **7 passed** (1.2 minutes), recorded in the ignored `checks/electron-final.log`. The suite includes seven live local scenarios: Python Monaco/save/conflicts/output, Java local build/run, responsive state retention, actual approval/Stop corrections, basic single-window navigation, sandbox/renderer reload, and explicitly enabled installed Ollama streaming/cancellation.
- Qt fallback smoke: **49 checks passed**, isolated profile, clean shutdown. Its model stream is a deterministic fixture. It never shares the Electron writable profile.
- Security regressions include strict method/payload validation, raw privileged method rejection, Markdown HTML/remote-image blocking, private protocol stdin, duplicate request identity, approval binding/reuse/shutdown denial, changed-action invalidation, file hash conflicts, and actual cancellation of an owned validation process.
- Earlier Electron runs found a stale Java button locator after adopting tree semantics and a 640×480 output clipping regression. Both were corrected; the focused rerun passed all three affected scenarios. A sandbox launch could not start Electron; real-window checks ran with authorised desktop access.

## Review artifacts and classifications

The review ZIP contains fresh actual Electron content screenshots: Welcome, Home normal, Home 1366×768, All Spaces, populated Studio, Studio after saving, Studio 1366×768, collapsed real approval, cancellation with no file change, running tests with enabled Stop, and the stopped result. The short recording shows navigation, the retained Studio editor/output, supported Stop, a successful rerun and save without losing output. No Qt/concept/mockup image is used as Electron evidence.

Normal outer window is 1440×920 (content 1424×881); smaller outer window is 1366×768 (content 1350×729), zoom 1. Window resizing does not change Windows display settings. Fixture chat and workspace names are visibly labelled. The new approval/results are actual Python actions over those fixtures, not injected events. No account, email, secret, or private conversation is used.

Known visual issue: during the existing Welcome-to-rail Core handoff, a brief horizontal rail scrollbar can appear. Settled Home screenshots wait for that transition; the issue is not claimed fixed. Long command previews wrap and the shortest Studio layouts require output scrolling.

The recording reuses the existing CDP/FFmpeg tool. It captures application content, not native window chrome, audio or a reliable cursor trail. Event-driven frame counts do not establish frame rate, animation smoothness or GPU performance. No new cold/warm startup comparison or combined Ollama/GPU benchmark is claimed. Browser text-zoom tests are not OS DPI tests. Physical multi-monitor/DPI and fresh live backend-crash tests were not performed in this focused round.

## Retained scope and limitations

- Chat and Studio are available Electron prototypes, not declarations of full action parity. Agent, Research, Desktop Control, Projects, Knowledge, Memory and Settings remain temporary Qt workspaces. Native Identity, Contacts, Calendar, Tasks/Reminders and Mail remain unfinished M3 obligations; no new Personal Core interface was implemented.
- Output is read-only xterm presentation, not an interactive shell. Validation output survives route changes and renderer reload while Python remains alive; cross-process restart history of these output channels is not promised. Retention is bounded rather than a new logging subsystem.
- Cancelling an approval prevents command start. Cancelling already-running validation preserves completed steps and reports cancelled/not-attempted steps; it cannot roll back arbitrary test side effects. Approved native validation retains the existing trust policy; this is not a new filesystem/network sandbox.
- Monaco's existing dirty-buffer protection, hash-checked saves and compare/rebase paths remain. Optional LSP/debugging is not added. Native GUI/packaged clean-machine acceptance remains outstanding.
- No dependencies/frameworks, branding source/icon, storage schema, default launcher or release tag changed. Full master 3.5.1 requirements remain in force. Do not continue to M2 until the user reviews this corrected M1 checkpoint.
