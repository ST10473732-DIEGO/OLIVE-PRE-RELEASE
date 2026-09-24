# OLIVE freeform execution closeout

Partial closeout; remaining gaps are explicit below. BASELINE_HEAD:
`9e4d91544227fb9e1dc3d59dfacb6fa627d83d9e`, clean checkout on
`feature/olive-unified-agent`. The reported checkpoint is the actual HEAD and
ancestor; no later work was discarded. Historical evidence remains unchanged.

## Fresh declared acceptance set

Declared before execution. All paths and content belong to a fresh acceptance
directory. Messaging destinations below belong to a non-networked fixture.
Each attempt is recorded separately; a safe rejection is not a completed
reachable task. No real external message is authorized by these examples.

| ID | Task | Required outcome/category |
|---|---|---|
| F01 | Read an owned maintenance page in Firefox, summarize its dates and save the result in Kate | Dependent derived note; exact source facts and saved bytes |
| F02 | Find the owned maintenance page from an owned results page and read it | Result selection; browser |
| F03 | Save a literal note at an already occupied test path, then open the browser | Collision refusal; original bytes unchanged; later step not run |
| F04 | Create and save a new Kate note with initially empty Save As filename | Task-owned dialog |
| F05 | Create another Kate note while an unrelated owned fixture Save As remains open | Isolated session; unrelated dialog unchanged |
| F06 | Reach an initially offscreen owned control and activate it | Scroll/menu navigation and actual region input |
| F07 | Send exact text to Finch in the owned messenger, then open Kate | Fixture destination and exact outgoing bytes |
| F08 | Send different text to Heron in a second owned workspace, then Firefox | Fixture server/channel binding |
| F09 | Reach an initially absent target through the fixture menu and activate it | Reachable navigation |
| F10 | Activate a genuinely missing fixture target | Missing-target category; zero incorrect effects |
| F11 | Message an ambiguous fixture recipient | Ambiguity rejection; zero sends |
| F12 | Stop during a dependent plan, then start a fresh task | Cancellation/recovery; no remaining old effects |

Native, browser, fixture-only and external-client evidence remain separate.
The earlier 16/29 outcomes and raster benchmark are historical, not measurements
of this task set. At initial inspection only Firefox was running; Kate was not
running, so the historical real Save As dialog cannot be reported as still open
in this restarted desktop session.

## Outcome and limits

This is a partial general-agent closeout, not a finished operator claim. The fresh
set establishes a dependent owned-page → extracted summary → Kate save, exact
browser link selection, isolated empty-filename Save As handling, scrolling/menu
navigation and one actual model/region-grounded EIS click. It does not establish
arbitrary freeform goals or Discord account/composer execution.

No reset, stash, branch downgrade, model download/removal, user-data migration,
C9/C10/OS implementation, public default change or push was performed. The
existing V2 UI, Copy, code-answer boundary, selected workspace, portal identity,
input authority, Stop/watchdog and Connect lifecycle code were preserved.
Changes here are nonvisual integration. Production Chat was exercised through its
trusted Electron renderer bridge (`interaction.submit`), with the same native
authority and input path used by Chat. Fixture preparation and read-only evidence
inspection were separate. Only one application/model owner ran at a time.

## Implementation and authority

`olive/interaction/interpreter.py` proposes a typed finite plan using the existing
reasoning router. `olive/desktop/freeform_plan.py` validates it against the
original request before any effect. Named result references replace model guesses
about step numbering; one bounded schema correction is allowed. A navigation
result consumed as page text is lowered to an explicit observation. The old 2–8
explicit-clause route remains an optimization; typed plans allow up to 24 steps
within a ten-minute task budget. The existing `orchestrator._native_submit` and
`linux/runtime.py` execute them, reobserve each effect and record verified
subgoals/remaining effects. There is no second input executor.

`TaskResults` carries the original request digest, task lifetime/Stop epoch,
verified window/URL location, observation lineage and bounded summary digest.
Only a summary result can fill note content. Paths, applications, recipients,
accounts, servers and literal message bodies remain original-request resources;
model fields and page instructions cannot grant authority. Directional literal
file/message effects still require an independently resolvable existing scope.
A proposal cannot multiply one authorized send. Multiple derived-note paths are
rejected before execution. Results are cleared when the task ends and are never
added to Memory or Knowledge. No shell interpolation is used.

Summaries are deliberately extractive: every selected excerpt must occur in the
observed source, at most 12 excerpts and 4,000 characters. This prevents adding
unsupported dates; it does not independently eliminate OCR transcription errors
or validate arbitrary paraphrases. For this owned page the excerpts were checked
against the source HTML, and the resulting UTF-8 file bytes match the generated
note. The verified source window and current URL must still match at read time.
Failures, cancellation and summary runtime errors retain earlier partial results.

Remaining planner limits are substantial: finite effect vocabulary, literal
application/resource names, conservative rejection of negative/conditional
freeform constraints, existing explicit scope requirements for messaging and
file transfer, no automatic repair of a failed effect, no arbitrary document
paraphrase binding, no file-overwrite goal, and no general discovery of an
unnamed server/account. A nine-step schema fixture tests the expanded budget;
no nine-effect live general-goal success is claimed. Most fresh navigation/send
cases still use deterministic clauses. F01 is the live model-planned dependency.
The validator proves authority for proposed effects; it does not independently
prove that a model included every effect in an arbitrary natural-language goal.
Location bindings currently cover explicit visits, not arbitrary link/menu
outcomes, so broader derived navigation remains limited.

## Editor ownership and observed crash

`applications.launch_editor_session` uses Kate's supported `--startanon` path;
new compositor windows and process creation time handle Kate's detached launcher.
`editor_ownership.py` records the document window, process lifetime, windows
present before Save As and the task's verified save action. A new dialog is bound
by transient parent or independently isolated session history. An empty filename,
shared PID/title, or KWin's `normalWindow` flag alone never establishes ownership.
Path collision checks precede launching a new editor; no existing file is replaced.
The helper resets ownership state with its control session.

F04 completed through a newly created empty-filename dialog. F05 created/saved an
independent note while a separate **owned acceptance** Save As remained open;
its original window and parent IDs were verified afterward. The historical user
dialog was unavailable because Kate was absent at this session's initial
inspection. It was never dismissed to unblock these tasks.

A later closeout-only AT-SPI tree read triggered/coincided with a Kate/Qt SIGSEGV
at 23:15:56 SAST on 24 September, in `QSortFilterProxyModel::data` through Qt's
DBus/accessibility stack. That owned PID 8574 and its Save File window are now
absent. The inspection dispatched no keyboard, pointer, save, cancel or close
input. Root cause beyond this stack/correlation is not established. The final
state must not be described as an open preserved dialog. No replacement dialog
was created to hide this failed inspection. The prior F05 evidence and the later
crash are both retained in `dialog-closeout.json`; unrelated user data was not
used for the fixture. Remaining owned saved-note editor sessions were left alone.

## Native, browser and messaging coverage

| Path | Status | Evidence and remaining boundary |
|---|---|---|
| Firefox owned page/read/link selection | IMPLEMENTED_AND_LIVE_TESTED | Exact native `jump` action selected the observed link; URL/window checks bind subsequent reads |
| Kate new derived note | IMPLEMENTED_AND_LIVE_TESTED | Source excerpts and saved bytes verified; no overwrite |
| Generic visual filled-control input | FIXTURE_ONLY | GUI-Owl plus independent OCR/region evidence actually clicked New sample through EIS and observed a changed frame; not just raster coordinates |
| Menu/scroll reachability | FIXTURE_ONLY | Amber appeared through Menu; Cobalt reached by scrolling after clipped GTK viewport repair |
| Owned local messenger | FIXTURE_ONLY | Finch send verified before a later Kate failure; explicit Osprey Workshop/Heron send and next effect completed; ambiguous Robin rejected |
| Native Discord | IMPLEMENTED_AND_LIVE_TESTED for launch/focus/frame only | Native scoped AT-SPI returned zero usable controls; no composer/account verified |
| Discord in actual Firefox | IMPLEMENTED_AND_LIVE_TESTED for official navigation only | 278 controls, no recognized message composer; observed editable fields were search/address shapes |
| Visual message candidate evaluation | FIXTURE_ONLY | Missing semantics enters GUI-model plus independent region evaluation, including when OCR abstains; model-only labels cannot authorize input |
| Discord visual account/composer/settings executor | NOT_IMPLEMENTED | Candidate evaluator deliberately ends without typing until roles and current submission settings are jointly proven |
| Actual external message delivery | NEEDS_REAL_USER_TASK | No actual user messaging task was supplied; no external text entered or sent |
| Hosted/native Windows/macOS and disruptive display tests | UNTESTED_PLATFORM | Not inferred from Linux or unit results |

The submission contract now accepts a current native composer `send`/`send
message` action whose exposed key binding is Return/Enter, while explicit
newline/conflicting hints override it. This is fixture-tested and does not
certify Discord's current settings or an unknown editable field. Existing
exact-body, account/server/channel, unrelated-draft and one-attempt delivery
checks remain. No uncertain send was replayed through another client.

The documented third-party policy risk remains: this work does not claim that
Discord permits GUI automation. No model-produced JavaScript, client changes,
private API, tokens/cookies, anti-detection or CAPTCHA bypass was used. The
candidate evaluator is useful progress, not finished real-client integration.

## Owner Mode coverage inventory

This inventory follows the registered typed tools in `application/service_container.py`,
`tools/`, `studio_tooling/controller.py`, desktop controllers, Personal/Mail,
Research and Media. “Existing Ask/direct action” means a real controller exists
but the local owner task policy does not automatically cover it; it is not an
implementation or permission-denial failure. Direct UI actions retain their
existing exact consent contracts. All rows retain Deny, trust, expiry, revocation,
OS authentication and high-impact boundaries; remote Chat/Connect never inherit
these owner grants.

| Implemented controller family | Owner/Ask coverage in this pass |
|---|---|
| `filesystem.stat/read_text` | Reads bound to an existing scoped owner file task |
| `filesystem.copy/move/write_text/trash` | Existing exact-resource owner contracts retained; no new broad grant |
| `filesystem.list/search/create_directory/delete` | Existing typed Ask/direct-action paths; directory creation not newly integrated; permanent delete remains high-impact |
| `code.read_file/read_range/search_text/search_symbol/list_symbols/find_references/replace_exact/replace_range/create_file` | Existing workspace/checkpoint controllers; no blanket new owner mapping to these tool names |
| `git.status/diff/log/branch_list` | **Added** finite read grants for explicit Git inspection in one selected approved workspace; argument allowlist, Deny/Stop/expiry retained; FIXTURE_ONLY |
| `git.add/commit/create_branch/checkout` | Existing Ask/direct action; no mutation grant added |
| `studio.run`, `workspace.run_validation` | Existing detected-run/known-standard validation owner scope retained |
| `studio.new_project` | Existing explicit named console starter contract retained |
| `workspace.create_template`, `studio.scaffold` | Existing Ask/direct action; no new owner mapping |
| Studio input, access, language service, build/test/debug/terminal/launch, package installation, local web requests, designer read/save | Existing typed controllers/direct actions; separate generic owner integration remains NOT_IMPLEMENTED |
| `terminal.run` | Existing bounded executor; no generic shell owner bypass |
| `system.open_application/open_path/list_running_applications/close_application/terminate_application`, `ide.open_workspace/open_file` | Existing typed policy paths; native explicit launch/focus continues through desktop task authority; no new close/terminate owner grant |
| Desktop capture/inspect/control, visual click, browser navigation/search, clipboard, media controls and platform navigation | Existing bounded desktop/direct-action routes; fresh Linux coverage above; no platform-wide permission blanket |
| Interactive browser operations/artifact download | Existing typed controller/direct action; no new generic owner grant |
| Communication submission and native send/draft | Existing exact ordinary-task authority; external destinations still require verified client context |
| Personal tasks/calendar/notes/reminders/import/export; internal contacts/profile compatibility controllers | Existing validation/store/controller and Ask/direct-action paths; no source observation automatically stored |
| Mail local records/connections/import/export/draft/send/sync/remote actions and conversions | Existing exact typed authority and sensitive configuration paths; no new generic owner grant |
| Research and local Media import/render | Existing controllers and policy; no additional automatic Ask migration |
| Bluetooth, arbitrary OS settings, arbitrary app account control, root operations | NOT_IMPLEMENTED in this completion pass where no applicable controller exists; not labeled a permission failure |

No new public mode, blanket Allow row or settings ceremony was added. The added
Git mapping is tested against argument expansion, cancellation and remote-context
inheritance but has no new production-Chat live acceptance claim. Full migration
of all implemented controllers remains unfinished.

## Text-model decision

The finite gate extends `scripts/backend_v3_benchmark.py` using the existing
Ollama service, registry and residency leases. No third candidate or new
quantization was acquired. See `answer-gate-declaration.json`, `answer-gate.json`,
`implicit-context.json` and `production-answer.json` for prompts, outputs,
settings, compile diagnostics, resource samples and timings.

| Model | Exact digest | Completed local answer-role decision |
|---|---|---|
| A: `olive-eval-hauhau-q6:20260924` | `022de4bfdd9d4c16141f8c30846f155c51cf7a5b91090a24dcb63a7dbeddec07` | FAILED_GATE: unchanged Python code compares NaN before finiteness and raises `decimal.InvalidOperation` instead of required `ValueError`; primary 13/14, supplement 3/3 |
| B: `orcarouter/Qwen3.8-27B-Uncensored:q3_K_M` | `4da593b4aaed076b41e22b07f680075ff3856c46802f64866c353ac2b1a4fbcd` | Passes this finite local answer/code role: primary 14/14, supplement 3/3, plus two compiled production Chat turns with retained constraints |
| Installed answer baseline: `gpt-oss:20b` | `17052f91a42e97930aa6e28a6c6c06a983e6a58dbb00434885a0cf5313e376f7` | FAILED_GATE in this comparison: unchanged Python code accepts `0.001` after rounding; primary 13/14, supplement 3/3; existing defaults retained |

Each primary run used context 4096, temperature 0.2 and output budget 2048;
the two context cases set 4096 and 8192. A/B used `think=false`; the baseline's
native supported profile used `think=low`. Follow-up/language/length/JSON,
missing context, unchanged Python and JavaScript behavior, contexts, three
repeated latency trials, active-stream cancellation and immediate recovery were
measured. Code ran unmodified in a no-network Bubblewrap process with no user
files mounted. This is representative coverage, not a comprehensive code score.

The explicit missing-attachment questions were supplemented by separately
declared implicit photo/PDF questions, without telling the model the attachment
was absent. All three answered truthfully. A longer 8192-context recall used
4,704 prompt tokens for A/B and 4,179 for the baseline; despite its historical
case name `context_boundary8192`, it is not a maximum-context or saturation test.
Measured peak total GPU usage was 7,075 / 14,447 / 12,709 MiB respectively, with
about 58.8 GB host memory available. Higher contexts were not tested.

Repeated READY request latencies in seconds were A 2.756/0.062/0.058,
B 3.760/0.153/0.158, baseline 3.862/0.199/0.199. Identical prompts permit caching;
these are not independent uncached throughput measurements. The first Python
regression overlapped part of the primary baseline run, so no controlled speed
ranking is claimed. The supplement ran without the full regression. Active-stream
cancel awaited task teardown in approximately 0.000–0.001 seconds and subsequent
recovery returned correct output; these timings do not measure hardware release.

B's isolated production profile used context 4096 / think=false / temperature 0.2 / output 2048,
with provider digest recorded and no preset alias. Its code turn took 18.121s;
its retained-constraint follow-up took 17.721s. Both unchanged code blocks passed
the same behavior checks; the follow-up explicitly adds blank-string rejection.
The interpretation trace remained `conversation.answer` with no tool execution.
Only the task-owned evaluation profile selected B. Public defaults, remote
mappings and personal overrides were not changed; downloaded is not active.

Candidate-specific shared C7 validation is **not run**, not a model failure.
There is no public shared-preset promotion. B is the selected local answer-role
evaluation winner within this finite gate; broader planner/GUI roles were not
imposed on a Chat-only candidate. A's historical absent-image/line failures remain
in the historical record, distinct from these newly passed cases. The earlier
thinking-enabled empty answer remains a budget/configuration failure, not a
refusal. No causal claim about “uncensoring” is supported by equivalent-base data.

## Every fresh task attempt

Order follows retained result artifacts. Full literal requests/responses and raw
artifact hashes are in [live-tasks.json](evidence/freeform-closeout/live-tasks.json).
Repairs and retests are separately named; this is not a controlled final-checkpoint
success ratio. Diagnostic inspections are listed separately in that manifest.
No incorrect dispatched message/path effect was observed; F07's rejected
unauthorized navigation proposal and the later Kate inspection crash are retained.

| Attempt | Seconds | Category / verified result or failure stage |
|---|---:|---|
| F04 | 6.428 | FAILED_GATE: detached Kate launcher process identity |
| F04-repair1 | 3.233 | IMPLEMENTED_AND_LIVE_TESTED: completed new empty-filename task-owned dialog |
| F01 | 0.043 | FAILED_GATE: media release environment guard |
| F01-environment1 | 0.039 | FAILED_GATE: model registry startup |
| F01-ready | 28.929 | FAILED_GATE: numeric result reference validation |
| F03 | 0.605 | EXPECTED_COLLISION: occupied file preserved; remaining effect stopped |
| F07 | 3.977 | PARTIAL: exact Finch send verified; subsequent Kate process ambiguous |
| F08 | 6.497 | FIXTURE_ONLY: exact Heron send and subsequent browser focus verified |
| F10 | 1.443 | EXPECTED_MISSING_TARGET: no input; remaining effect stopped |
| F06-visible | 1.780 | FAILED_GATE: asynchronous GPU release gate |
| D01 | 5.780 | FAILED_GATE: focus/geometry changed during observation |
| D02 | 2.711 | IMPLEMENTED_AND_LIVE_TESTED: official browser URL only; no messaging acceptance |
| F01-diagnostic-fix | 22.798 | FAILED_GATE: derived result type validation |
| F01-binding-fix | 23.152 | FAILED_GATE: derived result type validation |
| F05 | 3.298 | IMPLEMENTED_AND_LIVE_TESTED: independent save completed; unrelated owned dialog remained at that time |
| F09 | 4.570 | FIXTURE_ONLY: menu-revealed Amber click and browser focus verified |
| F06-scroll | 4.738 | FAILED_GATE: scroll occurred but viewport wrapper hid controls from observation |
| F11 | 4.779 | EXPECTED_AMBIGUITY: no recipient selected or message sent |
| F12 | 0.743 | CANCELLED: production cancellation after 0.5s; no later send |
| F12-recovery | 0.919 | IMPLEMENTED_AND_LIVE_TESTED: fresh browser task completed after Stop |
| F02 | 3.930 | PARTIAL: navigation completed; link hit-testing rejected |
| F06-region-ready | 1.782 | FAILED_GATE: asynchronous GPU release gate |
| F01-data-placeholder-fix | 22.732 | FAILED_GATE: derived result type validation |
| F01-named-results | 23.179 | FAILED_GATE: unexpected resource fields |
| F02-link-action | 5.545 | IMPLEMENTED_AND_LIVE_TESTED: completed with observed native link action |
| F06-region-handoff | 7.372 | FIXTURE_ONLY: completed actual EIS region click and verified changed frame |
| F06-inspect-open | 0.729 | DIAGNOSTIC: app observation only |
| F01-validated-reproposal | 26.886 | IMPLEMENTED_AND_LIVE_TESTED: completed after bounded schema correction |
| F06-scroll-viewport | 4.458 | FIXTURE_ONLY: completed scroll-to-target, exact click and browser focus |
| F07-app-binding | 7.959 | FAILED_GATE: hidden destination on another server; navigation denied before new send |
| D01-stable-window | 5.761 | IMPLEMENTED_AND_LIVE_TESTED: native launch/focus/frame only; no accessible composer |
| D02-context | 2.722 | IMPLEMENTED_AND_LIVE_TESTED: official browser URL only; separate read-only context inspection |
| F01-source-provenance | 27.269 | IMPLEMENTED_AND_LIVE_TESTED: completed with window/URI provenance and exact byte verification |


## Regression and provenance

Final production-code snapshot: `cbc7a088f4d3c62b74e8f5200fce608f32c0563c`.
The closeout/evidence commit follows it without changing production code. The
final checkout HEAD is the commit containing this report; obtain its full hash
with `git log -1 --format=%H -- docs/OLIVE_AGENT_FREEFORM_CLOSEOUT.md` (also reported
in the handoff). A commit cannot embed its own hash without changing that hash.

| Local commit | Scope |
|---|---|
| `b86f39faa311056b8303949299e5d52d49ea44ab` | Dependent task/results, editor ownership, navigation/visual handoff, messaging observation, scoped Git reads and tests |
| `cbc7a088f4d3c62b74e8f5200fce608f32c0563c` | Finite answer/context benchmark extension and scorer tests |
| Closeout commit containing this report | Evidence, inventory and factual journey; no production changes |

The fresh final Python snapshot passed **1,273 tests with 8 skips in 138.783s**.
Standalone Connect passed **241 in 89.314s**. Earlier complete Python snapshots
(1,257, 1,269 and 1,271) remain separate; no focused passes were added to an old
full-run total. Frontend passed **100 tests in 19 files**. Typecheck, lint and
build passed. All **748 repository Python sources** compiled.

`python -m compileall -q .` was executed and exited 1 on the unchanged ignored
PySide6 Android `__init__.tmpl.py` Jinja template. No source or dependency was
edited or skipped to make that command appear green. Repository-source
compilation is a separate check, not a replacement claimed as whole-tree success.

The first fresh Electron run passed 54, failed 2 and skipped 16 (7.3 minutes).
Its runner omitted the provisioned .NET/JDK directories: `spawnSync` returned
null before C# and Java fixture compilation. Those exact failures remain in
`regression.json`. The subsequent complete provisioned run passed **56 tests with 16 skips in
7.5 minutes**, with unchanged timeouts/skips. This is a separate full run, not
focused successes merged into the earlier total.

Provisioned versions: Python 3.14.7, Node 24.21.0, .NET SDK 10.0.401 and
Temurin JDK 21.0.12.1. Existing opt-in live/platform skips are not claims about
hosted/native Windows/macOS or disruptive display behavior. Full run logs,
commands, hashes and source counts are summarized in
[regression.json](evidence/freeform-closeout/regression.json).

`scope.json` records BASELINE_HEAD, implementation HEAD and changed-code hashes.
Historical evidence manifests are byte-for-byte unchanged; the old 16/29 outcomes
and 49/50 positive / 40/40 negative synthetic raster results remain historical.
Neither is pooled with this task set or labeled live generic-client acceptance.

Rollback uses local `git revert` of these commits in reverse order. No persistence
format migration or public model default was introduced. The earlier Owner Mode
migration receipt remains the existing rollback path for that historical setup.
Task-owned evidence, generated notes and the isolated evaluation profile remain
outside the repository; raw user chats, credentials, model weights, screenshots
and absolute personal paths are not committed. Saved-note windows were preserved;
the unrelated owned test dialog's final crash state is recorded above. The two owned fixture processes and loopback HTTP server were stopped after
verification, and only their exact task-created desktop entries were removed.
Their source, saved notes and evidence were preserved; no Kate process was
closed by cleanup. These fixtures are not a new product service. No push, merge, tag or release was performed.
