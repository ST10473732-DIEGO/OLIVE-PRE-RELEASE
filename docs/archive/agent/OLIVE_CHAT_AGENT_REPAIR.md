# OLIVE Chat and unified-agent repair

24 September 2026. This is an evidence report, not a claim of a general-purpose
operator or universally correct coding model. Work remains on
`feature/olive-unified-agent`, the broader approved implementation branch.

**BASELINE_HEAD:** `f7efb5034b3b3c1fe43680570c03fefbcb440822`, retained at
`baseline/olive-chat-agent-repair-f7efb50`. Legitimate later work was preserved.
No reset, stash, history rewrite, remote push, release or hosted CI was performed.
Implementation HEAD: `cc03f84c206627791e413168780fb946ec53b333`.
The final documentation commit follows this checkpoint; the final response supplies
the final HEAD without a self-referential hash here.

Implementation commits, in order: `14c8976`, `a02d2f2`, `16886b2`, `fdfbad0`,
`1b618f2`, `896606c`, `cc6d4a6`, `0676d9a`, `d01c412`, `4c48c91`, `bb75dd2`,
`fb494e1`, `39fc242`, `604399c`, `cc03f84`. Their subjects and complete changes are retained
in Git; no earlier checkpoint was rewritten.

## Completion matrix

| Requirement | Status | Evidence and limits |
|---|---|---|
| Message/code Copy | IMPLEMENTED_AND_LIVE_TESTED | Normal desktop-entry launch, actual generated Python block, real Chat Copy activation through native input, normal Kate paste/save, exact 237-character match including Unicode and final newline. Trusted IPC and failure cases also tested. |
| Ordinary code answers | IMPLEMENTED_AND_LIVE_TESTED | 24 live requests across eight languages/current text presets; 24 each for both candidates. No project/file/process effect for answer-only cases. Generation is not blanket correctness: compiled baseline Python had a missing import. |
| Local Owner Mode | IMPLEMENTED_AND_LIVE_TESTED | Enabled by versioned installation migration; normal Chat create/edit/move/Trash, Studio starters/run/validation, Firefox and owned messaging required zero redundant prompts. This covers implemented typed capabilities, not every requested future OS operation. |
| Control-region verifier | FIXTURE_ONLY | New 90-case held-out synthetic evaluation admits 49/50 unambiguous present targets and rejects all 40 absent/ambiguous/disabled/occluded cases. Zero actions in this benchmark. Real semantic native tasks are separate evidence. |
| Native Discord | PLATFORM_LIMITED | Actual installed client launch/focus/frame verified after launcher-identity repair. Native accessibility exposes no usable account/composer context. No verified real send. |
| Discord in Firefox | PLATFORM_LIMITED | Exact user phrase routes to visible Firefox and verified official web URL. Account/channel/composer/send semantics remain unverified, not inferred from Firefox search. |
| Real external messaging | NEEDS_USER_TARGET | No separate actual destination/content was supplied. No historical example was sent. This input dependency does not excuse unfinished client integration. |
| Generic owned messaging | IMPLEMENTED_AND_LIVE_TESTED | Native non-networked GTK fixture, varied servers/channels/content, destination binding, native actions, exact outgoing text and fixture Sent/Delivered state. Not evidence of Discord delivery. |
| Bounded multi-step tasks | IMPLEMENTED_AND_LIVE_TESTED | Explicit sequential tasks, browser reading/scroll/tabs, owned page summary, Dolphin transfer, messaging/app switching. Some attempts failed safely; broad model-generated multi-effect plans and page-to-derived-Kate-note remain NOT_IMPLEMENTED. |
| Four repositories / two models | IMPLEMENTED_AND_LIVE_TESTED | Four exact source revisions reviewed; both permitted artifacts acquired, hashed and evaluated in repaired production Chat. No model promoted. Source inspection is not a security audit. |
| Simple Chat / app-Core boundary | IMPLEMENTED_AND_LIVE_TESTED | Existing Chat/Home entry retained; code generation separated from commands, stable Copy, typed owner grants and tested file/Studio boundaries. V2 workspaces and remote controls retained. No OS split implemented. |

## Root causes and repaired paths

Copy originally used the browser clipboard API while Electron denied browser
permissions. Electron 44.3.0 supports an asynchronous native clipboard write.
`desktop/electron/clipboard.ts` now accepts only the exact trusted main frame,
webContents and `dmdo://app/index.html` origin, validates a bounded string and
awaits the real write. Preload exposes only `copyText`, never ipcRenderer, read
access, native clipboard objects or arbitrary channels. GO/foreign frames are
rejected. No sandbox/contextIsolation weakening, shell interpolation, clipboard
monitor or desktop-session prerequisite was introduced.

A second reproduced bug remounted code-block components during runtime refresh,
removing Copy feedback/targets. A stable `CodeBlock` component fixes that.
`CopyButton` captures the selected payload, handles overlapping clicks/unmount,
and reports success only after completion. Code copies raw text without fences;
whole-message Copy retains source Markdown. Hidden reasoning is never included.
Tests cover two blocks, tabs/Unicode/newlines, long stopped output, thread switches,
remote attribution, repeated clicks, rejected/oversized writes and malicious frames.

Early CDP-only activations updated an Electron readback but did not prove native
Wayland paste ownership. Those attempts were rejected as acceptance. The passing
run activated the actual focused Chat Copy control using EIS Space, then used the
production Chat Kate paste/save operation. The generated and saved hashes match
in [chat-copy-live.json](../../evidence/chat-copy-live.json). No hidden direct write
was counted as GUI success. Acceptance reads only the owned test payload.

The exact request “Write a Java login screen.” was classified as `code.inspect`,
which demanded a saved Studio workspace. Other prompts already generated code;
the evidence did not support blaming every preset's weights. Answer-only
deliverables now bypass that action interpretation without limiting languages to
Studio templates. Quoted/fenced action words do not create authority. Explicit
named Studio creation and file mutations still take the existing typed paths.
Selected Studio state alone is not permission to inspect/edit it.

A final restart check found a separate context bug: a new Chat did not receive
Studio's selected workspace reference, so “Run my project” could not resolve it.
The strict renderer/Electron/Python request contract now carries an optional
workspace ID. Core binds it only for an explicit local existing-project action,
before issuing the owner grant. Unknown IDs fail; answer-only code, newly requested
code/isolated previews and remote Chat ignore the reference. No project source
is copied merely because Studio is open. The final normal-launch test selected an
owned Python project in Studio, opened a new Chat and ran it with exit 0, the
expected stdout and zero approval prompts. See
[chat-closing-live.json](../../evidence/chat-closing-live.json).

Planner JSON remains separate from normal answer text. The normal prompt asks
for useful source, requested language, assumptions and honest validation limits.
It does not copy external system prompts or add a blanket refusal model.
Native thinking controls are explicit per internal profile. A zero-visible-answer
output-budget exhaustion is distinguished from refusal, malformed planner output
and provider errors. Upstream errors expose bounded categories/status, not raw
private provider messages. New-chat admission waits for the actual new conversation.

Read-only bridge refresh calls no longer consume the finite mutation replay
ledger; repeated refresh previously exhausted it during long evaluation. Mutation
deduplication, receipts and changed-argument rejection remain tested.

A fresh standalone Connect run exposed a Studio completion race after an invalid
interpreter configuration was cleared. The collector published a terminal state
before awaiting output drain and recording its exit code; Connect could see
“completed” with no exit code and classify it as failed. Terminal state now
publishes only after output, exit code and process cleanup are ready. A deterministic
test holds the drain boundary open and checks the state before and after release;
it demonstrably fails against the prior collector and passes against the fix.
The failed 241-test aggregate is retained separately from the corrected rerun.

The four-layer Java comparison is in
[chat-layer-comparison.json](../../evidence/chat-layer-comparison.json): direct local
endpoint 11.645 s, adapter 9.476 s, orchestrator 8.647 s and production Chat
12.396 s, all genuine `gpt-oss:20b` Java source. Direct/adapter share prepared
prompt/options; orchestrator/UI retain production defaults. These are not
byte-identical or statistically controlled latency trials. Bounded traces retain
request IDs, categories, model/prompt/output digests and timings, not hidden
reasoning or unrelated user content.

## Desktop integration and truthful verification

The named KDE grant remains `local.dmdo.desktop`. The native helper registers on
its own portal connection; normal-launch evidence records nonempty identity,
`kde-authorized/remote-desktop` value `yes`, combined RemoteDesktop/PipeWire and
EIS session. No permission was recreated during launches, errors or tests.
Existing provisioning receipts and rollback remain in the unified-agent report.
This is KDE-specific owner provisioning, not a strong hostile-same-user sandbox.

Installed launcher wrappers can resolve to a different real executable. The
application resolver now binds exact desktop-entry identity to KWin PID plus
owner/executable/process lifetime and entry digest. This fixed native Discord's
first launch-stage failure. KWin replies are accepted only from its unique bus
owner; there is no arbitrary model-supplied JavaScript endpoint. Missing AT-SPI
does not invalidate independently verified KWin activation and fresh capture.

Capture uses the selected window's actual portal mapping, including observed
HDMI-A-5 and DP-4 outputs at 1920×1080. This is not full multi-display/scale
certification. Firefox current-page OCR now crops the independently observed
document region so unrelated tab titles do not enter the model context.
DOM/script injection, browser debugging ports, tokens and profile copying are
not used. Temporary OLIVE-only loopback test inspection was removed from the
desktop entry after each launch.

EIS text input now waits for the installed libei ping/pong ordering guarantee
after its own modifier release. It does not ignore genuinely held modifiers.
Cancellation remains independent, with finite waits and release/close cleanup.
Dolphin uses the exact AT-SPI Selection target, verifies one selected file,
preserves collision checks and reserves paste once. Hash/source/destination
verification follows the visible operation. Messaging uses advertised native
invoke actions when pointer hit testing is unsupported; focus alone is not
reported as a click or effect.

The old OCR-distance verifier rejected left-aligned button centres. The new
`target_region.py` uses candidate identity/state/extents or bounded connected
control-region evidence; it does not pad text boxes or accept an entire row.
Results distinguish FOUND, NOT_VISIBLE_HERE, AMBIGUOUS, NOT_ACTIONABLE, STALE and
UNSUPPORTED. A model point alone is insufficient evidence. The GUI model's
absent-target behavior remains poor and is not hidden by the verifier result.

| Held-out category | Raw GUI-Owl correct | Independent verifier correct | Combined admission |
|---|---:|---:|---:|
| Present, unambiguous | 50/50 | 49/50 | 49/50 |
| Missing | 0/25 | 25/25 | 0 admitted |
| Ambiguous | 0/5 | 5/5 | 0 admitted |
| Disabled | 0/5 | 5/5 | 0 admitted |
| Occluded | 0/5 | 5/5 | 0 admitted |

This seeded synthetic raster set has 90 cases, median model decision 1.427 s and
zero actual input actions. It does not certify arbitrary icon-only menus,
scrolling/native/browser layouts. Historical 40/40-present, 0/10-absent raw results
and the earlier OCR verifier's 2/40-present, 10/10-absent results remain separate.
See [chat-region-evaluation.json](../../evidence/chat-region-evaluation.json).

The GUI baseline remains `GUI-Owl-1.5-8B-Instruct.Q5_K_M.gguf` (SHA-256
`c8cabd3eca98f7d40eb583116f66648b465cf144cadb00258e661574e954da83`) and
`GUI-Owl-1.5-8B-Instruct.mmproj-f16.gguf` (SHA-256
`88969da9a3c92b3ecd1f735af3d3d88afb6c240cd14067766c421c08b5d940b2`), using
isolated CUDA llama.cpp b11147 / `fee39dd92`. Its
community conversion provenance limitation remains. No GUI sweep, Ollama removal,
extra runtime owner, LAN listener or simultaneous unsafe model residency occurred.

## Messaging and multi-step outcomes

Native Discord's first failures were wrapper PID mismatch, then unavailable
accessibility at activation. Both launch problems were repaired. The remaining
observed native tree lacks verified account/destination/composer evidence.
`MESSAGING_OBSERVATION_UNAVAILABLE` and `MESSAGING_ACCOUNT_UNVERIFIED` now describe
the stage accurately. Supplying an account name alone does not prove it visible.
Firefox-web navigation is independently verified at the official origin, but
its real logged-in messaging context was not accepted or sent through.

Account, workspace/server, destination and exact content are separately bound.
Duplicate identities, changed targets and unrelated drafts stop execution.
Enter-to-send requires an observed composer-associated instruction; the model's
assertion alone is rejected. This semantic-hint route is fixture-tested, not
certified for Discord. The owned GTK messenger uses its actual Send action.
Durable effect reservations prohibit uncertain-send replay or a native-to-web
retry. A local echo is not treated as server delivery.

Discord prohibits normal-account automation and documents no GUI/Firefox
exemption. Neither route is described as officially supported or ban-safe.
See [Discord's account policy](https://support.discord.com/hc/en-us/articles/115002192352-Automated-User-Accounts-Self-Bots).
No token extraction, private endpoints, client patch, CAPTCHA bypass, evasion or
bulk-send facility was added. This policy distinction does not replace generic
visible-client architecture with a bot requirement.

The initial three native batches recorded 31 attempts, including 22 combined
desktop tasks with 12 complete verified combined outcomes. The later Owner Mode
batch added eight attempts, including three successful combined tasks (two
different messenger destinations followed by app activation, and KCalc open/click).
A later three-task editor batch stopped safely at an existing Save As dialog.
The closing search→summary retry added one successful combined task.
Thus **29 combined attempts / 16 fully verified combined outcomes** are recorded;
failed earlier attempts are retained, not replaced by later counts. Code answers,
Core file actions and Studio tasks are separate categories. Evidence:
[chat-combined-live.json](../../evidence/chat-combined-live.json),
[chat-owner-live.json](../../evidence/chat-owner-live.json).

Verified tasks include fresh Firefox searches/read/scroll/tab changes, owned
page→Chat summary (correct 12 mm/24°C facts), visible Kate note and native Copy
paste/save, Dolphin copy/move, varied owned messenger sends, Python/Java Studio
starters/validation and Python run. No approvals appeared for these authorized
ordinary effects. KCalc demonstrates a generic semantic app interaction.

The bounded explicit plan accepts 2–8 independently scoped clauses, re-observes
between effects and stops on uncertain/failing steps. A final page summary uses
ephemeral untrusted observed text in the regular selected text-model answer
pipeline; observations do not become new user instructions or persistent memory.
Late responses/cancelled epochs cannot revive an old plan. Broad freeform
multi-effect interpretation and derived page→Kate artifact binding remain
unfinished. This is not advertised as arbitrary autonomous planning.

Fresh native cancellation evidence is in [chat-stop-live.json](../../evidence/chat-stop-live.json).
The actual Chat Stop response handler was invoked programmatically while Firefox
remained active. The stopped flag was observed in 29.90 ms, and helper cleanup
completed separately. A new explicit task succeeded. Suspending only the owned
OLIVE backend removed its heartbeat: the independent helper exited in 1,728.79 ms
from suspension, closing its portal/EIS descriptors. After resuming the backend,
a new task acquired a fresh session and completed. These are observed application
timings, not a hardware key-release bound or a tested physical shortcut.

Window admission now distinguishes opening an app/new document from effects on
an existing document/account. Only the former can select the topmost normal
window using [KWin's documented stacking order](https://develop.kde.org/docs/plasma/kwin/api/).
The selected window identity is pinned during activation; dialogs, unknown/tied
stacking evidence and existing-target ambiguity still stop execution. Selection
contract tests pass, but the final Kate retry reached a **genuine Save As dialog**:
KWin calls it a normal window, while AT-SPI correctly exposes Save/Cancel. Its
filename is empty, so ownership could not be established. It was not dismissed,
and no document text was changed. This is a concrete remaining admission blocker,
not a shortcut/consent prerequisite. See [chat-window-live.json](../../evidence/chat-window-live.json).
A second Resize request with no visible change also stops instead of claiming success; one later search→summary request hit an upstream
ResponseError before the diagnostic improvement. The same request completed on
the final native retry with a fresh visible-page read and actual NORMAL
`gpt-oss:20b` answer; the original upstream cause was not established. The earlier
failed attempt remains a failure, not a refusal or retroactive success.

## Text-model evaluation and promotion decision

[Repository/model review](../models/OLIVE_REPOSITORY_MODEL_REVIEW.md) records exact revisions,
inspected source paths, licences, adopted principles and rejected deployment/
installer defaults. Acquisition totals 21,791,142,154 verified bytes (20.30 GiB),
below the separately authorized 30 GB budget. Candidate A uses pinned Q6_K;
Candidate B uses the publisher-linked public Ollama Q3_K_M package. The HF gate
was not accepted or bypassed. No additional precision/projector for A or third
candidate was acquired. Existing weights and public FAST/NORMAL/MAX/DEEP IDs remain.

Both candidates ran **32 real production Chat cases**: 24 code requests across
Python, C#, Java, JavaScript, TypeScript, Rust, Go and Swift, plus eight explanation/
constraint/uncertainty cases. Both returned 24 code-bearing responses in the
requested languages with genuine provider attribution and zero action effects.
No unnecessary refusal was observed in this finite benign set; that is not a
universal refusal/correctness claim. No harmful-compliance benchmark was optimized.

| Measurement | A: HauhauCS 9B Q6_K | B: OrcaRouter 27B Q3_K_M |
|---|---:|---:|
| Median first visible output | 0.4395 s | 0.878 s |
| Median complete answer | 6.6395 s | 10.7305 s |
| First case total, including initial load | 8.597 s | 19.986 s |
| Peak sampled whole-GPU use | 6,837 MiB | 14,188 MiB |
| Peak sampled whole-host used RAM | 11,451,328 KiB | 10,424,052 KiB |
| Representative compiled/behavior cases | 5/5 | 5/5 |

Ollama 0.34.2, context 4096, explicit think=false, temperature 0.2, output budget
2048; serial leases, no GUI model resident concurrently. RAM numbers are whole
system samples, not model process allocations. Initial A default-thinking trial
used 39.85 s/2048 tokens with zero visible text; it remains a failed separate run.
No MTP/speculative acceleration or publisher full-precision score is claimed.

The [baseline evidence](../../evidence/chat-baseline-code-results.json) records 24 cases,
six per preset: FAST resolved to `qwen3:8b`, NORMAL and DEEP to `gpt-oss:20b`,
and MAX to `qwen3-coder:30b` in that evaluation configuration. Actual digests,
contexts, budgets and prompt hashes are retained; different preset labels do not
necessarily mean different weights. Representative
Python/C#/Java/JS/TS behavior checks passed 4/5 (Python omitted `isfinite` import).
A and B passed all five of those independent finite-number addition checks.
Generated function bodies were not repaired; the baseline C# function received
the documented standard test wrapper/import. Rust/Go/Swift remain generation-only.
This is a small behavior sample, not validation of all generated applications.

Manual constraint review found A invented zero triangles when the referenced
image was absent and exceeded a requested C# line limit. B correctly abstained
on the absent image. Some arithmetic/documentation and browser-authority
explanations still need broader checks. Long-context/follow-up coverage and
candidate C7 promotion validation are incomplete. No equivalent base model was
downloaded, so differences cannot be causally attributed to “uncensoring”.
**NO PROMOTION**: public presets/user overrides remain unchanged. Optional tags
are retained for reproducible evaluation and rollback, not automatically selected.
See [model results](../../evidence/chat-text-model-results.json) and the honestly timed
[role gate declaration](../../evidence/chat-model-evaluation-gates.json).

## Owner Mode, scope and app boundaries

[OLIVE_OWNER_MODE.md](../../security/owner-mode.md) documents installation migration v1,
OS-bound identity, task grants, explicit Deny, remote exclusion, expiry, effect
reservations, Stop and precise receipt rollback. Owner Mode is enabled for this
installation only. It does not permanently set every permission to Allow.
Ordinary file delete uses system Trash; credentials, security changes, payments,
root grants and unbounded deletion stay outside this policy.

[OLIVE_CORE_APP_BOUNDARIES.md](../../architecture/core-app-boundaries.md) contains the before/
after control inventory and tested app boundary. No workspace was removed or
visual system redesigned. Chat remains the ordinary entry; advanced policy stays
in existing Settings. Core owns model leases and typed capability dispatch;
apps retain their stores/workspace state. Same-user local identity is not a
malicious-process sandbox. Connect does not inherit local owner authority.

The scoped ledger [chat-agent-repair-scope.json](../../evidence/chat-agent-repair-scope.json)
records nine scoped UI/IPC paths (including new Copy modules). Owner Mode uses
the existing backend-driven Settings form; its narrow setting contract is recorded
in `olive/bridge/settings.py` and its implementation commit. Historical freeze
manifests were not edited.
No obsolete shared permission engine, Ollama consumer, user record, SDK, model,
profile, journey report or branch was deleted. No model received root.

## Regression, environments and rollback

Fresh aggregates at the implementation HEAD are recorded in
[chat-repair-validation.json](../../evidence/chat-repair-validation.json):

| Check | Result |
|---|---|
| Full Python | 1,247 run, 8 skipped, passed |
| Exact Connect C1–C8 suite | 241 passed |
| Frontend | 100 passed across 19 files |
| Electron | 56 passed, 16 platform/opt-in cases skipped |
| Typecheck / lint / production build | Passed |
| Repository Python compilation | 738 tracked sources passed |
| Whole-tree `compileall -q .` | Failed only on the unchanged third-party PySide6 Android Jinja template in the ignored venv |

Failed runs are preserved separately; focused reruns are not added
to old totals. Repository-only source compilation is separate from whole-tree
compileall, which encounters the unchanged ignored PySide6 Android Jinja template.
Linux native acceptance, synthetic providers, raster benchmarks and fixture
messaging are explicitly distinct. Windows/macOS native execution, broad multi-
display scaling and real external messaging were not certified here.

Roll back coherent implementation commits with normal Git revert, and restore
Owner Mode through its receipt as documented. Keep the prior unified KDE setup
unless intentionally revoking it. Candidate evaluation did not change public
preset assignments; using existing presets is the model rollback. User files,
profiles, unrelated grants and historical evidence remain intact.

The exact optional push command is `git push -u origin feature/olive-unified-agent`.
It has **not** been executed. A later authorized push should run the repository's
existing `linux-portable.yml` Python/frontend/typecheck/lint/build and
`connect-portable.yml` platform matrix. The current workflows do not run this
Electron suite: a separate runner job with its required display/toolchains would
be needed for hosted Electron evidence. Headless CI cannot certify this personal
KDE desktop or Discord delivery. No C9, C10,
Mobile or OLIVE OS implementation is included.
