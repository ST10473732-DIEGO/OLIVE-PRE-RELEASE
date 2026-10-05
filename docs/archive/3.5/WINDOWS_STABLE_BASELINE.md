# Windows stable baseline

## Repository and preserved design

Starting branch: `design/olive-workspaces`, commit `b25b9b8`.
Completion branch: `final/windows-stable-baseline`.
Tested implementation commit: `9cafe6838d2d7b2fa7e6d0011959bcd97c9b927b`
(Windows reliability work in `8b43b8b`, bounded research correction in `9cafe68`).
Checkpoint identity: the final hash is recorded in the completion report; resolve
the branch locally with `git rev-parse final/windows-stable-baseline`. This file
is versioned with that checkpoint rather than embedding a self-referential hash.

The starting worktree was clean, with one worktree, no configured remotes and no
unmerged branches. HEAD already combined functionality through `3e1f349`, OLIVE
GO through `819dc0a` (including accepted `acb383e` ancestry), and Claude's newest
workspace design `d53e835` plus its handoff `b25b9b8`. No reset, cherry-pick,
history rewrite or blanket conflict resolution was necessary. Design styles,
layouts and OLIVE GO implementation are preserved.

## Launch and dependencies

From the repository root in PowerShell:

```powershell
.\run_olive.bat
```

The launcher now opens the current Electron interface. It requires the existing
Python virtual environment and a built desktop application. Initial desktop
setup remains `cd desktop`, `npm ci`, `npm run build`; no model is downloaded by
launching the app. `python main.py` remains the historical Qt entry point.
Never run two writers against one profile. `OLIVE_DATA_DIR` is authoritative;
fresh defaults and legacy profile reuse remain unchanged.

Acceptance machine: Windows, Python 3.14.5, Node 24.19.0, .NET SDK 10.0.401,
Ollama 0.34.1, NVIDIA RTX 3080 Ti Laptop GPU (16 GiB). Repository pins include
Electron 44.3.0, React 19.3.0, TypeScript 6.0.3, Playwright 1.63.0,
Monaco 0.56.0, xterm 6.0.0 and pywinpty 3.0.5. Optional local media acceptance
uses the already-installed ComfyUI v0.35.0 / SDXL runtime.

## Architecture and repairs

Natural language still enters `NaturalLanguageOrchestrator`, `CapabilityRouter`
and `InteractionContext`, followed by deterministic tool permissions,
confirmation, execution and observation. Model output and retrieved content do
not supply authority. Mail previews, Discord bot/personal-account boundaries,
workspace checks, credential vaults and desktop takeover/stop remain intact.

- **Chat:** constrained programming-language identifiers prevent explanatory
  model prose from breaking project creation. Proposed code/project actions
  receive a second semantic classification using the reasoning role before
  action routing; this adds inference latency but does not authorize execution.
  Targetless diagnostic questions
  stay in Chat; semantic classification uses selected workspace context for
  abbreviated feature changes without authorizing them. Selected-record summaries
  retain read-only capability resolution instead of losing Mail context through
  the ordinary-answer shortcut. An answer stream that
  ends without Ollama's completion marker now remains incomplete, preserving
  partial content and giving retry guidance.
- **Research:** when scope review identifies insufficient support and other
  retrieved excerpts remain available, synthesis gets one bounded opportunity
  to correct the missing premises. The same independent review runs again;
  continued rejection remains uncertain. Both reviews are retained. No new
  source fetch or relaxed citation validation is used to justify a claim.
- **Studio:** ordinary console Run previously used subprocess pipes and a
  separate line-input form. It now connects to the existing ConPTY session
  service and xterm terminal. A process adapter preserves RunSession observation,
  output history, permissions, Stop and timeout behavior. Build/test output
  remains separate. New sessions are selected/focused; exited sessions reject
  input. Listeners are removed on unmount. Closing/Stopping a terminal reaps its
  owned program descendants and completes the run lifecycle. Failed starts
  cannot remain permanently `starting`.
- **Errors:** safe known messages cover stale file revisions, missing files or
  executables, timeouts, disconnects, exited terminals and denied permissions.
  All dispatched request failures carry request ID, method, feature, stage,
  category and opaque context IDs. Main-process logs retain safe correlation;
  arguments, terminal input and private content are not logged by this change.
  Existing opt-in `OLIVE_ATTACH_DIAGNOSTICS=1` retains bounded DPAPI-protected
  original exceptions/stack information. Logging does not retry or suppress
  failed operations. Desktop's diagnostic pane filters unrelated feature errors.
- **Launch/tests:** normal Windows launch selects the accepted Electron design.
  Windows path assertions compare path identity rather than casing. Native
  restore approval is separated from unattended restore-integrity coverage.

## Presets

| Preset | Current mapping / pipeline | Evidence |
| --- | --- | --- |
| FAST | `qwen3:8b` | Live Chat question and code answers |
| NORMAL | `gpt-oss:20b` | Live ordinary Chat and public-source research |
| MAX | `qwen3-coder:30b` | Live code answer, with no workspace or execution |
| DEEP | `gpt-oss:20b`, bounded extraction/retrieval; relevant `qwen3-vl:8b` vision | Live mixed PDF retained native page metadata and read the scanned page with evidence |
| REIMAGINE | Local ComfyUI / SDXL; existing local raster editing | Live generation, edit, artifact verification, cancellation and GPU handoff back to Chat |

No mapping was changed. The installed set remains `devstral:24b`, `qwen3-vl:8b`,
`qwen3-coder:30b`, `gpt-oss:20b`, `qwen3:8b`, `qwen3-embedding:0.6b`.
No models were installed or deleted. One owned Ollama server and the existing
loopback-only media engine were started for acceptance and stopped afterward.
Cleanup verified the Ollama executable, command and creation time, reaped its
four owned processes, and confirmed the media process exited. The six installed
models were checked again before shutdown and remain unchanged.

## Request-flood investigation

The historical OLIVE GO → Studio `olive:call` storm did not recur. Each new
Python/C# terminal acceptance test repeats Chat → OLIVE GO → Studio → Mail →
Agent → Desktop Control → Chat → OLIVE GO → Studio twice and asserts there are
no renderer errors or unexpected rejected IPC calls. The deliberate post-exit
terminal write produces exactly one expected rejection, not a retry storm.
OLIVE GO's independent native-view/security/restart regression also runs.

This establishes the tested transitions, not the historical root cause. Safe
correlated diagnostics are retained for a recurrence. No global console
suppression, swallowed request failure or blind retry was introduced.

## Coverage and results

Verification runs (each count comes from one complete run, not combined
partial reruns):

| Check | Result | Local log |
| --- | --- | --- |
| Python compile, `.venv/Scripts/python.exe -m compileall -q .` | Passed | `.windows-acceptance-compile.log` |
| Python unit/regression suite | 828 passed, 0 failed, including real C# signatures/formatting/code actions | `.windows-final-python-research.log` |
| Frontend unit tests | 29 passed in 10 files | `.windows-acceptance-frontend.log` |
| TypeScript and ESLint | Passed | `.windows-acceptance-types.log`, `.windows-acceptance-lint.log` |
| Production frontend and Electron builds | Passed | `.windows-acceptance-build.log` |
| Final complete Electron suite, safe live flags enabled | 57 passed, 0 failed, 1 native-dialog skip (16.5 minutes) | `.windows-stable-electron.log` |
| Live semantic routing matrix | 20/20 passed after semantic action review | `.windows-routing-reviewed.log` |
| Normal launcher / owned process shutdown | 2/2 cycles passed, 9 owned descendants reaped per cycle | `.windows-launcher-final.log` |

The final Electron run used the frozen implementation commit above: 46 ordinary
isolated tests plus 11 opt-in live tests passed in that single run. Live coverage
includes local Ollama/vision/media, personal and Mail language workflows, and
safe public Google/research access. Native restore-dialog automation is the sole
skip. No manual native-dialog pass is claimed. An earlier default-only complete
run passed 46 with 12 opt-in skips; it is not substituted for the final run.
Logs and synthetic screenshots remain local ignored artifacts, not committed
user data. Owned server cleanup is recorded in `.windows-owned-cleanup.log`.
Earlier failing attempts were investigated and are not counted as clean runs:
Windows path casing, changed dock/error expectations, a dirty-buffer teardown
dialog, premature model discovery, schema language prose and targetless/follow-up
intent classification were repaired. The broader live run exposed a selected
Mail summary losing its record context; its repair passed the real search,
summary, draft, recipient correction and cancellation workflow. A subsequent
routing recheck exposed fast-model code/action misclassification; code/project
actions now receive semantic reasoning review, followed by a 20/20 live rerun.
One subsequent complete run finished with 56 passes, one skip and one research
failure: synthesis omitted a retrieved premise needed to support its numerical
claim. The bounded synthesis correction described above addresses this without
relaxing evidence review. A deterministic regression exercises both successful
correction and continued rejection; the targeted live rerun passed. Earlier
failed runs remain failures in their original logs.
Native restore focus remains classified
below rather than being counted as a pass.

The normal-launch probe measured five seconds of foreground Welcome idle per
cycle: 16.25% and 23.12% of one logical CPU core across owned processes, with
499.7 and 496.1 MiB combined working set. This is a short sanity sample, not a
long-duration benchmark or a claim about other applications' GPU activity.

The live `calculator-project.spec.ts` journey uses one isolated profile for an
ordinary question, a code-only answer with no workspace/run, approved project
creation and execution, and a context-aware follow-up. It then saves the small
`input()` fixture through Monaco, types `level` into the actual xterm terminal,
observes the response, navigates OLIVE GO to an owned HTTP fixture, returns to
Studio and visits Mail, Tasks, Agent, Desktop Control and Chat. It asserts no
unexpected `olive:call` rejection and waits for captured owned child-process
identities to disappear after normal close. No injected model result is used.

| Area | Meaningful exercised paths |
| --- | --- |
| Chat | Ordinary questions, code answers vs actions, 20 live routing paraphrases, project creation/follow-up, scoped approvals, cancellation, incomplete/empty streams, missing models and preset selection |
| Studio | Real Monaco editing/save/conflict checks; Python/C#/Java runs; ConPTY frontend typing, Backspace, Enter, synthetic paste, `level`/`hello`/`radar`, Ctrl+C/Stop, post-exit rejection; workspace isolation; LSP/DAP, builds/tests, Git and isolated local preview; owned WinForms fixture |
| OLIVE GO | Native fixture navigation/search, tabs, history/favourites, downloads, private storage, panels, route changes/restart and absent privileged bridge/Node in remote pages |
| Mail | Synthetic multi-account separation/reply identity, draft persistence, EML/HTML isolation, IMAP fixture sync, TLS SMTP fixture accepted/partial/uncertain outcomes; Gmail OAuth and iCloud IMAP/SMTP/vault structure |
| Personal/data | Projects, Knowledge ingestion/retrieval, Memory CRUD, task/calendar/reminder relationships, recurrence/restart, notifications and backup round-trip |
| Agent/Desktop | Synthetic planning/progress/cancel/history, permission denial, owned launch confirmation, emergency Stop and verification; no unrelated personal apps controlled |
| Lifecycle/UI | Route churn, native view cleanup, two normal-launch/shutdown cycles, owned PTY child cleanup, language-server shutdown, responsive/security/appearance smoke |

## Limitations and classifications

- Native restore dialog acceptance reproduced focus loss; the helper refused
  to click. `OLIVE_NATIVE_DIALOGS=1` opts into exclusive foreground coverage.
  Unattended tests control only dialog responses and still perform real
  archive creation, validation, restore, restart and relationship/outbox checks.
  No native-dialog pass is inferred from the controlled test.
- The first live routing run timed out during cold model startup. Subsequent
  warm tests are reported separately; no indefinite automatic retry was added.
- One MAX test exceeded its original 120-second harness budget while still
  emitting tokens. Closing the test retained an incomplete answer. Its live
  acceptance now allows at most five minutes and requires a complete response;
  a subsequent run completed MAX in 14 seconds. Runtime limits and model mappings
  were not changed to disguise the timeout.
- An owned WinForms probe failed once with exit 1 after earlier passes. Its
  original exception was not retained by the old assertion, so no root cause is
  claimed. The harness now reports probe stderr immediately; the focused rerun
  passed the actual native calculations. Native UI timing remains environment
  dependent.
- Local inference remains model/hardware dependent. Passing the synthetic
  language matrix is not a guarantee for every utterance or generated program.
- Mail provider OAuth/login and real external sends were not performed through
  personal accounts. Fixture SMTP/IMAP results do not certify provider credentials.
- Desktop automation is limited to supported providers and owned fixtures;
  arbitrary Windows applications are not certified. Personal Discord self-bot
  automation is not supported.
- Python reports a shutdown `ResourceWarning` about 26 uncollectable objects
  in these full runs, also present in the starting run. This is separate from
  the owned child-process checks; it is not presented as a measured memory leak.
- No clean-machine installer certification, binary publication, tag, release,
  remote push or merge to main was performed. No Linux implementation or OS,
  Connect/mobile/device-pairing work is included.

Future platform work is scoped in [Linux port readiness](../linux/LINUX_PORT_READINESS.md).
