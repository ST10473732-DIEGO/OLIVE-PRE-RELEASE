# OLIVE functional reliability implementation ledger

This is the **implementation and acceptance ledger**, starting from the clean
`b7f96aa7e71d6ac977b76296e684a264447d1237` worktree on
`design/olive-clarity-and-multi-project`. Work is on
`functionality/chat-reliability`. The master brief remains authoritative;
historical review gates in release documents do not supersede it.

The current acceptance matrix below supersedes the historical checkpoint sections.
Generation/video, personal provider authentication and mobile deployment are not
claimed complete. Installation/disposal authority and phone platform were requested
together; silence has not authorized downloads, deletion or deployment.

## Historical 621b2bf repair: code delivered in Chat

On 13 September 2026 the installed `qwen3:8b` classifier returned
`{"mode":"action","domains":["code"]}` for the exact request:
“Give me code for a simple calculator app.” This reproduces the faulty
speech-act decision, not merely an assumed frontend problem. The same model
classified the explicit Studio create/save/run request as an action.

The old classifier described editing code as an action without distinguishing
code delivered in an answer. In `interaction/router.py`, `code.modify` requires
a workspace and invokes `agent.run`. Thus selecting a workspace could turn
requested answer content into editing work; without one the request instead
asks for a saved workspace. Nothing at that layer produces a normal code answer.

`interaction/deliverable.py` now recognizes clear conversational code,
explanation and wording requests without inference. It can only select the
existing answer path, never authorize an action. Mixed clauses, selected source
references, pending draft revisions and explicit workspace actions retain
semantic resolution. Classifier instructions and demonstrations also distinguish
conversational output from file changes. This is a conservative fast path plus
a semantic fallback, not a universal natural-language grammar.

The actual route is renderer submit → interaction.submit → interpreter →
conversation.answer → ChatController.send → GenerationPipeline → Ollama stream
with no action tools → chat_stream events → saved assistant message. No Agent
planner is required for the direct route. Retrieved document processing retains
its existing authorization boundary.

The Ollama adapter already separated thinking from content; that separation is
preserved. Empty/whitespace-only output now raises an actionable error. A
provider-reported output-limit stop also raises an error after retaining partial
content. Controller coverage verifies both original request and partial answer
survive failure without creating tasks, workspaces or runs.

## Historical 621b2bf evidence and limits

- Real Electron/Python/Ollama acceptance: `desktop/tests/e2e/calculator-chat.spec.ts`.
  The exact request initially produced complete Python calculator code, arithmetic
  and division-by-zero handling, and usage instructions; a later run selected
  HTML/CSS/JavaScript and supplied a full HTML document. Code was inspected as an
  answer; this acceptance does not execute the generated program.
- First recorded UI run: visible code at 11.1 s, completion at 17.6 s. These are
  end-to-end UI timings, not cold/warm decoder benchmarks. Subsequent reruns have
  their own timings in the evidence JSON (latest: code visible at 6.0 s,
  completion at 19.2 s). Zero classification calls on the direct
  route; no resolved action steps.
- Explicit comparisons of Agent history, workspaces, run sessions, terminal
  commands, buffers and approvals confirm no new execution work in that run.
  Normal and 1000×700 screenshots were opened and inspected.
- Local evidence: ignored `artifacts/core/functionality/calculator-chat.json`,
  `calculator-chat.png`, and `calculator-chat-small.png`. Synthetic profile data
  and model responses remain outside committed source.
- Live classifier checks also returned answer/conversation for “Provide
  JavaScript for a countdown timer” and “I need C# code for a small calculator”,
  and action for Open Discord, Run this script, and the Studio create/save/run
  request. The semantic gate alone still classified the email wording example
  as communication in one run; the direct draft-output path handles the exact
  example. Broader draft paraphrases remain an acceptance gap.
- This is not completion of explicit new-project execution or all Chat routing.
  A full real Studio create/build/run demonstration remains open. No UI redesign
  was made.
- Fresh checks: Python compileall and 764 unittest cases passed; TypeScript and
  lint passed; all 25 frontend tests passed; Vite/Electron build passed. Five
  Electron scenarios passed: actual calculator answer, live stream/cancel/route
  retention, Chat operations, responsive sandbox/security, and actual C# starter
  editing/run. The C# starter is not the requested calculator-project acceptance.
  The final conservative routing guard also passed its targeted safety tests.
- `scripts/natural_language_context_acceptance.py` passed with the actual local
  model: same pending message identity, recipient retention during a body
  correction, and cancellation. No external send was approved or performed.
- Existing non-failing warnings remain: large frontend chunks and a Python
  shutdown ResourceWarning about 26 uncollectable objects. These are not reported
  as repaired by this checkpoint. The full ordinary Electron suite and complete
  master-brief acceptance have not been run.

## Baseline preservation and initial environment inspection

Before source edits, 896 tracked files were copied to ignored
`build/functionality-baseline/current-source.zip`; every entry was read back and
verified against SHA-256 values in `manifest.json`. This is a current-source
recovery backup, not a user review ZIP or proof of intact historical Git objects.
No history repair, pruning, reset, tag, publication or cleanup was performed.

Ollama was running; no Electron process was visible at initial inspection.
Process command-line inspection through CIM was denied. The restored local
Python is 3.14.5 at `.venv/Scripts/python.exe`. Python/Ollama are absent from the
shell PATH; the Ollama local API responds. The installed Electron dependency is
44.3.0. Restricted writes to existing generated directories and isolated vault
tests required normal reviewed sandbox escalations; no access rules were changed.

The local model API reports devstral:24b, qwen3-vl:8b, qwen3-coder:30b,
gpt-oss:20b, qwen3:8b, qwen3-embedding:0.6b, llava:34b and dolphin-mixtral:8x7b.
No model mapping, weight, embedding dependency, user profile or credential was
changed. Hardware verification, disk/reference inventory and representative
cold/warm benchmarks remain open. No space was reclaimed.

## Master acceptance checklist — current continuation

This table is the current requirement-to-evidence map. Earlier dated sections
are checkpoint history, not the current status. External configuration and future
mobile work are not live verification. Targeted fixtures are identified below.

| Acceptance / brief sections | Implemented behavior and UI entry | Backend | Evidence and status | Setup / limits |
| --- | --- | --- | --- | --- |
| A — Chat/routing/streaming (§2–4) | Code/explanations/drafts answer in Chat; actions retain scoped review; partial failed streams remain incomplete | interaction deliverable/interpreter/orchestrator; ChatController; Ollama | Repaired; real calculator code UI repeated, 16.1 s latest; no Agent/workspace/process; paraphrase, cancellation and stream tests | Conservative fast path plus semantic fallback; not a universal grammar |
| B — Explicit project execution (§2–4) | Home/Chat creates and runs a calculator in Studio | project.create; reviewed coding workflow; Studio run service | Live local UI repeated, 1.4 min latest; real arithmetic, unit tests and division-by-zero; cancelled second project never created | Follow-up found zero handling already present, so this is not proof of a forced edit; native designer acceptance separately edits real C# |
| C — Five presets (§5–7) | FAST/NORMAL/MAX/DEEP/REIMAGINE; provider/digest inspectable in Advanced | PresetCatalog, model registry/residency, DEEP | Implemented and measured; MODEL_PRESETS.md and committed benchmark JSON; real image/PDF reading | Bounded benchmark, not peak-resource or universal quality ranking; no duplicated weights/paid fallback |
| D — Simplification (§8) | General preferred name Diego; Profile/Contacts absent from navigation, launcher, project tabs and public tool catalog | Existing internal profile/contact stores retained | Live UI and backend compatibility tests; old records/links survive reload and backup/restore | Internal compatibility APIs remain; timezone/storage identity preserved |
| E — Research in Chat (§9) | Search web/Research thoroughly and Saved research & evidence, independent of preset | Existing research planner/gateway/extraction/evidence/synthesis | Live official Python documentation answer; latest research 17.65 s backend, actual 3.0 inference; history/source-save denial and draft retention UI pass | Citations and model scope review are fallible; evidence remains inspectable |
| F — Multi-account Mail (§10,12) | All Inboxes, per-account filters/folders, Trash, search, attachments, From and receiving-account replies | Extended M4 store/IMAP/SMTP/vault; Gmail remote locations | Live two-account loopback TLS/UI with overlapping IDs; SMTP accepted/partial/uncertain paths, incremental sync/restart | Local peers are synthetic, not connected personal mailboxes; no permanent-deletion recovery claim |
| G — Gmail/iCloud (§11) | Mail Connections setup and honest connection state | Desktop OAuth state/PKCE/system browser/vault/XOAUTH2; iCloud TLS/app password | Implemented; synthetic OAuth/refresh/revocation tests; live external authentication unverified | Google desktop client registration and user consent; iCloud app-specific password. Exact checklist in [MAIL_TRANSPORTS.md](../MAIL_TRANSPORTS.md) |
| H — Studio/designer (§13–15) | Independent projects; Monaco, terminal, build/run/test, LSP/DAP/Git; Design/Code/Preview WinForms | Existing Studio services plus owned WinForms layout generator | Live C# console, ASP.NET endpoint and Python service acceptance; real native calculator UI computes, saves/reopens, undo/redo and conflict rejection; WINFORMS_DESIGNER.md | Declared generated subset, 8 basic controls; no arbitrary constructors or full Visual Studio parity; canvas does not simulate native layout containers |
| I — Browser (§17–18) | Real tabs/address/Google/back/forward/find/zoom/history/bookmarks/downloads/private mode | Electron 44 WebContentsView; isolated sessions and narrow browser IPC | Live loopback UI, actual download bytes, modal hiding, native normal/small captures, restart; Google reached its real CAPTCHA page | Google results unverified; denied site permissions and unsupported auth require system browser; download list is session-local |
| J — Connections/apps (§16) | Accessible bot destinations, exact reviewed bot send; personal Discord manual | Discord transport/permissions/revision ledger; UI consequence policy; owned UIA resolver | Synthetic bot transport/policy tests; real generic UIA exact text verified on one owned fixture with one-use PID/window/content approvals | No live bot configuration/send; no self-bot or simulated personal send; no claim of any-app compatibility |
| K — Cleanup (§19) | Inventory and exact approved local disposal manifest | Supported Ollama commands, followed by tag/digest/storage verification | Only llava:34b and dolphin-mixtral:8x7b removed; six remaining digests unchanged; 46.61 GB observed free-space gain | Source, data, toolchains and recovery copies kept; shared blobs never manually deleted. STORAGE_REVIEW.md |
| L — REIMAGINE (§7) | Media import/crop/resize/generate/image-to-image/preview/export, progress/cancel and disconnect | Pillow; approved loopback ComfyUI 0.35.0 / SDXL base 1.0; measured shared GPU residency | Real raster and 1024×1024 generated/edited outputs through UI; source bytes preserved; running prompt cancelled; actual Ollama handoff | Per-profile engine connection; imperfect counting/color prompt fidelity; video editing/generation remains unavailable. BROWSER_AND_MEDIA.md |
| Mobile/cross-device (§20) | Portable contracts and concrete iPhone final-stage plan | olive/sync validation, stable IDs/revisions, grants/revocation/conflicts | Implemented contract tests; iPhone selected; future mobile stage | No client/deployment/listener, database-file sync, vault sharing or external-action replay. MOBILE_CROSS_DEVICE.md |
| Method/closeout (§1,21–23) | Redesign/history/security preserved; synthetic isolated acceptance | Existing Electron/React/TS/Python/Monaco tooling | Fresh full Python 815 passed; ordinary Electron 44 passed / 10 opt-in skipped; separate live SDXL journey passed; TypeScript, lint, 26 frontend tests and build passed | No tags, releases, version/default-launcher changes, cloud deployment or review ZIP |

The previously bundled decisions were answered explicitly on 2026-09-14: approved
media installation, approved exact two-tag disposal, and iPhone as the phone target.
Execution and fresh verification are recorded below. Mail account credentials
must be entered by the user through the setup UI, not supplied to the model.

## Continuation: explicit project acceptance (2026-09-13)

The starting checkpoint was verified as `621b2bf` on
`functionality/chat-reliability`, with a clean worktree. No reset, release change,
history repair or replacement of the redesign was performed.

The exact request "Create a calculator project in Studio and run it." initially
resolved Studio as an external application. The semantic catalog lacked project
creation. The repaired path represents `project.create`, resolves an installed
language (Python by default), calls the existing reviewed `studio.new_project`
tool, generates bounded source changes with the local coding model, reviews
each write against its workspace and original content, validates, then runs.
Code-only requests retain the accepted tool-free Chat path.

`scripts/coding_project_acceptance.py` and the real Electron
`desktop/tests/e2e/calculator-project.spec.ts` both passed with synthetic profiles.
The Electron scenario starts in Home, approves only inspected fixture operations,
creates actual Python source, compiles it, runs six generated unit tests, and
enters `2 + 3`, `8 / 2` and `9 / 0` through Studio's program-input UI. Actual
output includes 5, 4, and a division-by-zero message. The backend acceptance also
checks successful process exit and a successful calculation after the error.
The follow-up "Change it so it handles division by zero." retains the same
workspace and leaves an unrelated sentinel unchanged. In this run the generated
calculator already handled zero: the follow-up verifies that behavior and reruns
checks; it is not evidence of a forced source modification. Cancelling a second
project's real approval leaves no extra workspace. No completed task was injected.

New program input is bound to the exact running native session and workspace,
bounded, and subject to terminal permission. Closed sessions reject input. New
tests cover Deny, cancellation during review, folder-scoped creation denial,
dirty buffers, typing while approval waits, unread-source overwrite and path
escape rejection. Editor changes now update the backend retained buffer, and
reviewed writes recheck that buffer before saving. Terminal close now waits for
Windows process termination and reader shutdown before releasing the workspace.

Partial streamed responses persist `completion_state=incomplete`; old messages
load compatibly. Alternate legacy text-only branches show unverified completion.
The normal/smaller-window screenshots are retained in ignored
`artifacts/core/functionality/project/` and were inspected internally. These are
targeted Python console/Chat/Studio results, not WinForms, C#, browser, or full
master-brief acceptance. The existing redesign remains visible.

Hardware inspection confirms the i9-12900HX, 68,430,585,856 bytes of physical RAM,
and RTX 3080 Ti Laptop GPU with 16,384 MiB VRAM. Serial installed-model benchmarks
are in progress. No model weights, backups, legacy records or user data were
removed. Remaining master checklist items stay open; work continues to presets
and presentation simplification after this internal checkpoint.

Fresh continuation regression: `compileall` passed; all 771 Python tests passed
(94.394 seconds); all 25 frontend tests passed; TypeScript and lint passed. The
Electron project scenario passed separately after the selection/input repairs.
The known Python shutdown ResourceWarning remains. This is an internal stage
checkpoint; a fresh complete applicable suite is still required at final closeout.

## Continuation: presets, simplification and Chat research

The explicit-action checkpoint is committed as `58eae7d`. Ten additional live
semantic paraphrases passed via `scripts/routing_paraphrase_acceptance.py`; this
is interpretation evidence, separate from the real project execution above.

Five public presets now select explicit local providers and pipelines. New chats
use NORMAL; legacy raw model selections remain intact and inspectable in Advanced
Settings. See [MODEL_PRESETS.md](MODEL_PRESETS.md) and its raw measured evidence
for installed tags, digests, capabilities, correctness, cold/switch and warm timings,
and resource samples. No weights were duplicated or removed. REIMAGINE reports
Needs setup and cannot silently produce chat instead of a media artifact.

Profile and Contacts have been removed from navigation, launcher and active pages;
their public tool definitions and semantic proposals are hidden. Internal APIs,
stored identities, old contacts and linked records remain for compatibility and
data safety. The preferred name Diego lives under General preferences; existing
timezone/locale and permission internals are retained. User prompts receive the
name as a preference without instructions to repeat it.

Chat exposes Search web / Research thoroughly independently of preset. Sessions
are linked by stable IDs in saved chats, with progress, original evidence and
history accessible there. Existing research records/reports remain unchanged.
Explicit source URLs constrain selected evidence and search domains. Redirected
or cached sources outside that scope are rejected as evidence. A live test exposed
a related-product documentation result and an overly weak numeric assertion;
these failed attempts were retained and repaired. Scope review now distinguishes
labelled deductions from source assertions; novel numeric quantities remain
inferences and require review, never automatic factual approval.

`scripts/deep_document_acceptance.py` passed with real native extraction/retrieval
(12 to 18 units => 50%) and real qwen3-vl image interpretation followed by text
synthesis (SAVE from button.png), with actual source/provider metadata and no
project or process. DEEP's PDF rendering is bounded to relevant/requested pages;
unexamined pages are not claimed readable. Broad mixed/scanned-PDF acceptance
remains open. The strengthened Electron scenario passed (43.2 seconds), requiring
the actual rendered Chat answer to contain 3.0 and its inference label, as well as
checking the persisted evidence. Normal and smaller-window screens were inspected.
Fresh compileall and all 778 Python tests passed (93.632 seconds); the existing
shutdown ResourceWarning remains. Frontend tests (25), TypeScript, lint and build
passed. This stage is not a claim of whole-brief completion.

An additional startup race is repaired: request controls wait for initial model
discovery, preset failures give fixed safe guidance, and pre-generation failures
retain the user's message. Every generated answer records its actual Ollama tag,
digest (when available), and public preset. Partial response completion state is
still retained. No external account sign-in or message submission was performed.

## Continuation: Mail accounts and authentication

Mail continuation after `2a85b50`: repaired INBOX/Inbox visibility, account-filtered
folder counts and replies, advertised SPECIAL-USE roles, provider-correct Trash
selection, Gmail account-scoped X-GM-MSGID label identity, COPYUID move identity,
and string/byte IMAP capability handling. Existing SMTP submission safeguards and
legacy contact records remain. The composer uses recent explicit participants;
Calendar draft creation has a Contacts-independent API while the old API remains
internal for compatibility.

Google desktop OAuth is implemented over M4 IMAP/SMTP with system-browser launch,
loopback state/PKCE validation, pinned TLS endpoints, vault-only client/refresh
credentials, memory-only access tokens, and a provider-validated primary sender.
iCloud has official server defaults and an app-specific-password setup flow.
The exact configuration checklist is in Mail Connections and [MAIL_TRANSPORTS.md](../MAIL_TRANSPORTS.md).
No personal account has been connected; Google client registration and user
consent remain required. Synthetic OAuth tests do not count as live Google auth.

Mail targeted regression: 33 Python cases passed, including real TLS sockets to
two separate synthetic IMAP peers, overlapping IDs, Gmail label deduplication,
Trash/COPYUID and XOAUTH2. Three real Electron M4 workflows passed (20.1 seconds):
content isolation/proposals, bounded sync/body fetch/restart, and draft autosave.
The real two-account Electron acceptance also passed (5.9 seconds): two separate
loopback peers, overlapping message IDs, unified/per-account Inbox, receiving-account
reply selection, and actual Google Needs setup/iCloud server-default UI. It exposed
an incoming-only From selector bug; that account now remains visible with an explicit
sending-setup limitation. Normal and smaller-window screenshots were inspected in
`artifacts/core/functionality/mail-accounts/`. A complete Python run passed 785
tests (96.755 seconds), compileall passed, and 25 frontend tests, TypeScript, lint
and build passed. One additional refresh-rotation test and progress updates receive
targeted checks before this checkpoint. The known shutdown ResourceWarning remains.
Studio/WinForms, Browser, app workflows, media integration, cleanup and mobile
contracts remain unfinished. The master task is still active.

## Run this checkpoint

Studio continuation after `3935aea`: see `WINFORMS_DESIGNER.md` for actual native
calculator evidence, ownership/conflict limits and installed-toolchain checks.
The audit repaired shared run-configuration environment state, explicit run
environment filtering, interactive input on the advanced run path, and verified
listener ownership before Studio HTTP inspection. New template creation uses
no-restore/no-update-check; the API template omits optional OpenAPI packages.
Three existing Studio Electron scenarios and the expanded designer scenario
passed. Fifteen targeted Python tooling/designer tests passed. A full 790-case
restricted run had only two Windows vault/DPAPI environment failures; all five
relevant protected tests passed under the normal approved Windows logon. A fresh
full run is underway. This is not completion of the master brief.

From the repository root, use the existing isolated launcher:
`powershell -File scripts/launch_electron_preview.ps1`.
For this acceptance from `desktop`, set `OLIVE_LIVE_AI=1` and run
`node node_modules/@playwright/test/cli.js test calculator-chat.spec.ts`.
It uses a temporary profile and the installed local `qwen3:8b`, with no download.


## Continuation: Browser, app control, media and source-aware Chat

After `45edff9`, Browser and media tools were integrated into the existing shell;
Connections gained permission-filtered bot destinations and retained exact review.
The generic UIA acceptance used the existing owned-process window resolver and
verified `Hello from OLIVE` in its one synthetic editor. The approval handler
rejects every other target/content/action and cannot approve a broad discovery
or message send. A separate consequence-boundary rule prevents Discord desktop
variants or real Discord browser hosts from using generic UI submission.

Real raster editing is verified. ComfyUI is an unverified integration until its
runtime/checkpoint is approved, installed and exercised; video remains unavailable.
The download and storage manifests, supported boundaries and actual Browser
evidence are documented in BROWSER_AND_MEDIA.md and STORAGE_REVIEW.md. Mobile
contracts and the final milestone are in MOBILE_CROSS_DEVICE.md.

Final workflow testing found and repaired further real document defects. Missing
PDF pages no longer shrink page_count; optional unreadable_pages metadata migrates
with an empty legacy default. Image-only PDFs remain available for explicit DEEP
page vision even without OCR. Re-indexing keeps the original document name in
citations. Attached-document identity now reaches interpretation, preventing a
phrase such as “attached PDF” from becoming a fictitious file-read approval.
Actual Electron/Python/Ollama acceptance read a scanned pears total of 37 on page
2, while retaining native page-1 metadata and page-specific vision provenance.
The final targeted UI test passed in 39.3 seconds; its screen was inspected.
Temporary attachments retain their existing one-response lifetime; source
citations remain on the answer. OCR is absent here and is not claimed live tested.

Research testing exposed missing module-level qualifiers and an insufficient
scope-review response budget. Evidence selection now reserves the requested
definition and bounded module overview; plain definition-list text is retained.
Synthesis prioritizes explicitly requested sources, keeps inference labels, and
review uses bounded low reasoning with room for an actual JSON assessment.
Unsupported claims still fail closed. The actual official-source Chat answer
was reverified; source IDs alone are not considered a correctness test.
Closing/reopening the Chat research history panel now retains its question draft.

The initial full Electron run had 38 passes, 8 opt-in skips and 6 failures.
Obsolete Profile/Contacts UI assertions were deliberately replaced with active
General/Calendar/Tasks workflows and compatibility-record checks. Research panel
and browser-bridge assertions were updated to their real scope. All affected
targeted journeys then passed. Fresh complete-suite results are recorded below; the earlier totals are historical.

Normal Electron launch from the repository root:
`& .\desktop\node_modules\electron\dist\electron.exe .\desktop`
This uses existing configured data-location rules. For synthetic demonstration,
use `powershell -File scripts/launch_electron_preview.ps1`; it creates an isolated
seeded profile. The old default launcher and release version remain unchanged.

## Extended live-language repairs, 2026-09-14

The opt-in historical M3/M4 language journeys were actually rerun, not counted
as green because the ordinary suite skips them. They exposed invalid recurrence
and priority values, an unsolicited time shift during creation, obsolete public
Contacts link fields, and inactive/consumed operation choices. Public schemas now
match supported fields and current context. Recurrence and priority validate
before routing; native IDs must match the selected identity kind or be explicitly
supplied. A consumed proposal cannot become a repeated save, and pause/resume
are unavailable when there is no executable task. Existing native records and
legacy associations remain covered independently; no backend safety tests were
removed. The public task journey no longer requires creating a Contacts link.

The actual FAST model also invented a local folder and Gmail query syntax for
cached-mail search, and retained the wrong recipient in a correction proposal.
The exact-content harness rejected the wrong proposal before execution. Native
and communication extraction now uses the measured reasoning role. Local/cached
scope is distinct from a folder; sender/recipient filters retain plain query terms
and match exact addresses. Unsupported extraction triggers bounded retry, not
an invented successful search or save. Explicit addresses replace obsolete
Contacts-name resolution in the Mail language test.

Final separate live runs passed: M3 in 1.6 minutes (calendar proposal/correction/
review/save, project/event-linked task, reminder, actual free-time result, Agent
native read and restart retention); M4 in 58.0 seconds (imported message search/
summary, draft, recipient correction and cancellation with no outbox entry).
These are full journey timings, not token latency benchmarks. Earlier failures
remain in ignored evidence/logs and demonstrate why neither a model label nor a
test total proves every paraphrase reliable.

The historical `m2-closeout-live` harness was not rerun: it still addresses the
removed standalone Research launcher and lacks result assertions for its research
attempt. Current calculator-project, Research-in-Chat and native Agent-read
acceptance provide the relevant actual paths; it is not counted as a live pass.


## Final verified desktop continuation

- Python: compileall passed; all 808 unittest cases passed in 100.280 seconds
  (`.functionality-python-verified.log`). Vault, security, migration/backup,
  document, native identity, Mail transport and actual tooling coverage remain.
- Frontend: TypeScript and lint passed; 26 tests passed; Vite/Electron build passed.
- Fresh complete ordinary Electron suite: 44 passed, 9 opt-in skipped, 7.6 minutes
  (`.functionality-electron-closeout-final.log`). Native WinForms calculator passed
  in 25.8 seconds; Browser in 10.4 seconds; actual raster editing in 5.3 seconds.
- Separate actual-model/public acceptance: calculator answer 16.1 seconds;
  calculator project 1.4 minutes; stream/cancel/route retention 13.8 seconds;
  scanned-PDF DEEP 39.3 seconds; official-source Research 17.65 seconds backend;
  native Calendar/Tasks 1.6 minutes; native Mail 58.0 seconds. Google navigation
  reached its actual CAPTCHA page; results were not claimed. These separate runs
  are not represented as all opt-in tests passing in the ordinary suite.
- Normal and smaller-window screens were inspected, including actual native
  Browser captures, Chat, Media, Studio/designer, and the latest Mail/native-read
  results. Git diff checks passed; no version/identity changes, staged credentials,
  user-data files or model weights were found in review.
- Existing non-failing warnings remain: large frontend chunks and Python's
  26-object shutdown ResourceWarning. They were not silently labelled repaired.

Completed implementation commits before this final continuation are 58eae7d,
2a85b50, 3935aea and 45edff9, following accepted 621b2bf on the existing
functionality/chat-reliability branch. The final continuation commit contains
Browser, raster media, Discord boundaries, source/native workflow repairs and
portable contracts. No release tag, merge, publication or history repair occurred.

At commit f3a5582, generation installation, two-tag removal and phone-platform
selection were pending. The subsequent explicit approvals are implemented below.
Video editing/generation remains unavailable and unverified. Personal Gmail/iCloud
and Discord bot live verification still require user configuration and specific
external-send authority; no real messages were sent. The iPhone client remains the
future final milestone. These limits are not counted as completed capabilities.

## Approved installation, cleanup and iPhone continuation, 2026-09-14

The existing functionality/chat-reliability branch and f3a5582 checkpoint were
preserved. No history reset/repair, redesign, version/default-launcher change,
release tag, merge or private-profile modification was performed.

ComfyUI v0.35.0 NVIDIA portable and SDXL base 1.0 were downloaded from the exact
approved URLs. Both byte counts and SHA-256 hashes matched the pinned manifest.
Archive member paths were validated before extraction. Licenses/model card remain
beside the local installation; no custom nodes, paid service, extra checkpoint or
system Python/driver installation was used. The runtime is loopback-only, with
custom/API nodes disabled. Its measured working logical size, including retained
archive, checkpoint and initial outputs, is 13,427,639,221 bytes (13.43 GB).
The normal user profile is not automatically connected to the engine.

Actual v0.35.0 inspection exposed empty HTTP-200 command responses and asynchronous
GPU freeing. The adapter now handles the documented empty acknowledgements, uses
prompt-ID-bound cancellation, waits for the cancelled prompt to leave the queue,
and verifies native allocator release before Chat. The launcher disables dynamic
VRAM and cudaMallocAsync because those allocators bypass the counters used here.
A release/disconnect control clears the per-profile connection only after verified
GPU release; offline/active-engine failure retains configuration and artifacts.

`media-generation.spec.ts` passed through real Electron controls in 58.5 seconds:
actual FAST arithmetic → SDXL generation → image-to-image → running-prompt cancel
→ actual FAST arithmetic → release/disconnect → actual FAST arithmetic. The
1024×1024 outputs took 19.222 and 19.401 seconds; cancellation took 6.028 seconds.
The sampled native Torch allocator maximum was 6,056,574,976 bytes (5.64 GiB),
with 20,971,520 bytes remaining after release. Sampled whole-system RAM use peaked
at 32,598,110,208 bytes; that includes other processes and is not engine-only RAM.
These are bounded journey samples, not continuous peak or cold/warm benchmarks.
Original bytes, distinct output hashes, actual PNG pixels, prompt/workflow/version
provenance and no cancelled output were checked. Normal/smaller-window screens and
the output images were inspected. Prompt fidelity is imperfect: four olives instead
of three, and only partial requested color changes. Evidence is retained under
`artifacts/core/functionality/media-live/`; no fixture output was substituted.

Only the two explicitly approved Ollama tags were removed with `ollama rm`.
Post-removal inventory verified their absence and the six remaining model digests.
Logical storage fell by 46,610,091,177 bytes; observed model-volume free space grew
by 46,610,325,504 bytes. The separately approved media runtime uses the repository
volume. No chat records, backup, toolchain or other model weights were deleted.
Exact local outcomes remain in `.functionality-cleanup-result.json` and the
approved manifest. See STORAGE_REVIEW.md for before/after measurements.

The final mobile plan now targets iPhone: an installable Safari client with
explicit desktop pairing, selective offline records, conflict handling, revocation
and unavailable-host behavior. Actual iPhone implementation and deployment remain
a separate final milestone; no network exposure or mobile client is claimed.

Fresh post-installation validation: `python -m compileall -q .` passed, including
the separate downloaded runtime tree. All **815 Python tests** passed in 102.155
seconds (`.functionality-python-media-complete.log`); TypeScript, lint, Vite/Electron
build and **26 frontend tests** passed. The initial restricted-shell run hit Windows
vault/diagnostic protection and Vite cache permissions; normal authorized synthetic
runs passed without weakening those protections. The existing large-chunk and
Python shutdown ResourceWarnings remain. Installed weights/runtime, private local
manifests, synthetic profiles and generated evidence are excluded from Git.

The fresh complete ordinary Electron suite passed **44 scenarios with 10 opt-in
skips in 7.4 minutes** (`.functionality-electron-media-final.log`). Actual native
WinForms calculator acceptance passed in 25.9 seconds, Browser in 10.8 seconds,
and raster editing in 5.3 seconds. The new live SDXL journey is deliberately opt-in
and passed separately in 58.5 seconds (`.functionality-media-live-verified.log`);
its skip in the ordinary suite is not presented as execution. Historical live
language/provider runs above remain separately dated evidence. Personal Mail/bot
configuration, unavailable video capabilities and the future iPhone implementation
are still explicitly outside the completed live scope.
