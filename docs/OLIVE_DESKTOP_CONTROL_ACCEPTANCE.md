# Linux Desktop Control acceptance

See [the unattended continuation](OLIVE_DESKTOP_UNATTENDED_RUN.md) and
`evidence/linux-desktop-unattended.json` for subsequent fixes and fresh full-run
results. The results below describe the earlier checkpoint, not an aggregate
combined with newer focused tests.

2026-09-23. **Milestone incomplete; live control is not accepted.** Implementation,
portable regression and real local-model measurements are separate evidence.
No renderer change beyond the three individually approved exceptions.

## Inherited failures and reproduced causes

Initial six-case reproduction: **1 passed, 5 failed**. GO initially passed, then
its intermittent failure was reproduced independently. Historical V3 aggregates
are not reused as current success.

| Case | Current outcome and evidence |
| --- | --- |
| attach-diagnostics | Fixed Linux disabled-policy rejection and private opt-in JSON metadata; Windows keeps DPAPI. The fixture now awaits the real failure event across Electron's separate event/invoke channels. |
| m2-desktop | Real backend Stop latch, reset and disabled-policy rejection pass. These boundaries do not certify portal injection. |
| owned-launch | Linux policy enablement and reviewed Python launch use the actual interpreter. Stop cancels the real approval and the owned script never executes. |
| browser/GO | Fixed approved initial native-layout timing. Loaded DOM text in a hidden 1×1 view returned 0 matches; actual presentation returned 2 for the same text. Twenty fixed native-find trials and the full GO journey pass. No fake text counter or find API replacement. |
| responsive | Approved three-line state fix closes Explorer on narrow panel opening. The fixture runs its real input-waiting program before asserting Stop. 640×480 assertions retained. |
| winforms-designer | Native Windows limitation retained. Original native Windows journey remains; Linux verifies the unavailable template and available C# console template. No native Windows pass claimed. |

The original Desktop Control documentation's “unavailable everywhere on Linux”
expectations in L1/L3 were replaced with explicit Off/no-session/no-Stop-verification
assertions. API availability is host-dependent and never implies consent.

## Regression commands and results

Run from the repository with `.venv/bin/python` and the retained
`.toolchains/node/bin`, `.toolchains/dotnet` and `.toolchains/jdk/bin` on PATH;
DOTNET_ROOT/JAVA_HOME point to the existing repository toolchains.

- Full Python: **1,154 tests: 1,146 passed, 8 skipped, 0 failed**, 135.310 seconds; no uncollectable-object shutdown warning.
- Exact Connect: `.venv/bin/python -m unittest discover -s tests -p 'test_connect*.py' -v`:
  **240 passed**, 89.597 seconds. Real TLS, authority, storage and lifecycle retained.
- Frontend: `npm --prefix desktop run test`: **96 passed, 18 files**.
- `npm --prefix desktop run typecheck`, `lint` and `build`: passed.
- Repository-source compilation: **688 Python files passed**, including new files.
  The required literal `.venv/bin/python -m compileall -q .` was also run; its
  sole error is the ignored PySide6 Android Jinja `__init__.tmpl.py`, not OLIVE source.
- Complete Electron: **55 passed, 16 skipped, 0 failed**, 71 tests, 7.7 minutes. Earlier
  full aggregates were 52/16/3 and 54/16/1 (passed/skipped/failed), with the demonstrated
  fixture defects retained in the investigation history. Focused passes were never
  added arithmetically to an older aggregate.

The owned adaptive-loop tests substitute only inference and unsafe host interaction;
real settings, scoped permission decisions, grants, session history and effect
receipts remain. They cover exact send without redundant confirmation, draft-only,
malformed actions, changed destination during inference, explicit Send deny, Stop
while inference waits and concurrent capability probes. Additional tests cover
stale generations, Stop under a held command lock/database writer, strict private
Stop frames, geometry, black/invalid capture, unknown actions and trailing constraints.
These are **not real GUI messaging or portal input tests**.

## Shutdown warning

The original full run emitted 26 uncollectable objects. Import-only discovery did
not reproduce it. Individual Qt suites passed without it; combined offscreen Qt
experience/window/preview suites reproduced it without the native helper. Those
fixtures stopped timers/closed widgets but left their owned QObject managers,
bridges, callbacks and deferred widgets alive. Explicit `deleteLater` plus delivery
of Qt DeferredDelete events removes the warning in the 36-test reproduction and
in the subsequent full Python run. No `gc.collect`, warning filter or weakened
assertion. No evidence that this warning came from portal/GPU workers. A minimal
third-party-only QObject/Property/WebEngine example did not reproduce it, so this
report does not blame PySide6 for an established upstream defect.

## Real installed vision evaluation — failed grounding gate

Same fixed synthetic images, three layouts × two trials. Required correctness:
strict valid schema, exact target label, and predicted center inside the actual
button. All three are required; confidence does not count. One fixture includes
an irrelevant instruction to authorize a shell command. No command was executed.

Artifact: `qwen3-vl:8b`, Q4_K_M,
`901cae73216286ea8c5aba8b46d307ff7188f737285ec500c795a12f05225d28`.
Ollama 0.34.2; RTX 3080 Ti Laptop 16,384 MiB. A live `/api/ps` sample reported
5,793,780,858 bytes both size and size_vram. Peak samples below include the whole
GPU, encoders/context and desktop; they are not exact peak-allocation telemetry.
Temperature 0; existing adapter budgets 4096/8192 context and 1536/3072 output,
at most one retry within 90 seconds. No model/template/mapping migration.

| Measurement | Before retry-contract repair | After repair |
| --- | --- | --- |
| Trials | 6 | 6 |
| Correct label and center | 1/6 | 2/6 |
| Schema-valid answers | 1/6 | 4/6 |
| Median completion | 20.863 s | 67.350 s |
| Range | 18.288–24.223 s | 50.571–70.836 s |
| Maximum sampled whole-GPU use | 7451 MiB | 8251 MiB |
| GPU samples (~0.5-second interval) | 244 | 729 |

The existing vision retry expected an empty response plus eval_count, but the real
inference service rejected empty answers first. A typed failure now preserves only
bounded eval-count/stop-reason metadata. Empty answers remain failures to ordinary
callers. Vision can use its already-defined one retry only on first-budget exhaustion.
Afterward two trials still exhausted 3072 tokens; two valid replies had wrong centers.
The improvement does **not** pass a visual-action gate. Screenshot-driven Linux
input stays disabled. No p95, universal quality claim, real screenshot acceptance
or promotion. Cold/warm states and decode rates were not separately measured here.

Reproduce explicitly (not ordinary CI):

```
OLIVE_START_OLLAMA=1 PATH="$PWD/.toolchains/ollama/bin:$PATH" \
  .venv/bin/python scripts/evaluate_linux_desktop_grounding.py \
  --run-installed-model --output /tmp/olive-grounding-new-result.json
```

The harness refuses an existing output, downloads nothing, uses an isolated profile,
generates synthetic pixels, reuses OLIVE's registry/residency, and closes only its
owned Ollama process. Both pre/post content-free manifests are committed.

## Live host gate and outstanding scope

The user approved an idle-desktop acceptance session. KDE's dialog was shown, but
no global Stop activation arrived; the user confirmed it had not been pressed.
Later tests hit consent timeout or a denied/cancelled portal response. No saved
OLIVE shortcut binding was found. The automated test closed without capture/input.
The agent did not approve its own portal dialog or synthesize the human keypress.

**BLOCKED:** real global Stop verification, portal source/device consent, actual
capture/EIS/AT-SPI injection, physical interruption response and measured cleanup.
**NOT IMPLEMENTED/ACCEPTED:** broad free-form planning, implicit-account messaging,
visual-only input, adaptive Kate save and Dolphin copy/move, browser navigation/
read/find/tabs/download acceptance, owned GUI messenger acceptance, and real
Discord navigation/send. The current loop/grammar and provider substitutions are
not a substitute for those deliverables. Existing-app focus/activation and
accessibility gaps still need host evidence and narrow supported APIs.

**PENDING:** native fractional/multiple/rotated displays, Chat/DEEP/C7/SDXL/desktop
resource handoffs, normal desktop-entry UI acceptance, native Windows/macOS,
and hosted runs (no push authorized). Normal `run_olive.sh` L1 journeys exercise
real V2 pages and process cleanup; C#/Java/PTY journeys retain normal toolchain
behavior. No iPhone/mobile or native Windows GPU result is inferred.
