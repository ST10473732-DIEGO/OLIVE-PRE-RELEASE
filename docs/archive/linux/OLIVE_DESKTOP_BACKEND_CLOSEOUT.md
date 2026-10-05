# Linux desktop/backend closeout

For the subsequent unattended implementation, newly reproduced PTY/Connect fixes,
current verification totals and minimum human resume procedure, see
[the unattended run report](OLIVE_DESKTOP_UNATTENDED_RUN.md). The checkpoint and
measurements below remain historical evidence.

2026-09-23. **Partial implementation, not full desktop-operator acceptance.**
The independent backend/V2 repairs are implemented and regression-tested. Human
Stop verification and native task acceptance did not complete; the measured
vision candidate also failed its grounding gate. This milestone must not be
presented as a finished universal or production-certified desktop operator.

## Checkpoints and history

Branch `feature/olive-desktop-control-linux-v1` starts from verified clean V3
BASELINE_HEAD `2df73b31ca11374978363a8f9d9c34ab052a74a4`, preserving DESIGN_BASE
`50003790c42aff620d63d664dff89c0338347cab` and the inherited wizard fix.

| Commit | Work |
| --- | --- |
| `80d2793` | Baseline, frozen-byte manifest/checker, initial host/acceptance gates |
| `5aad726` | Approved narrow Studio Explorer state fix and active resize fixture |
| `ae0666c` | Finite direct-user grants, strict action validation and durable effect reservations |
| `5e1dd6f` | Approved GO initial-layout timing and truthful Stop/takeover copy; native find regression |
| `28d3195` | Linux reviewed launches, private diagnostics, truthful WinForms selection and Qt fixture disposal |
| `1b3716a` | Typed empty-answer metadata, existing bounded vision retry and measured failed grounding comparison |
| `ebd7d20` | Portal/PipeWire/EIS/AT-SPI adapters, private helper ownership, immediate Stop, bounded local loop and tests |

The final documentation commit records this ledger and the completed verification
manifest. `git rev-parse HEAD` gives the resulting report checkpoint. No merge,
push, tag, release, history rewrite, C9/C10 work or model download/promotion.

## Preservation and retained runtime

The checker compares 225 baseline hashes against the actual V3 Git object and
scans frozen roots for additions/deletions, including untracked/ignored files.
There are zero unauthorized edits/additions/deletions. Exactly three new exceptions
were explicitly approved: Studio.tsx (three-line responsive state effect), Go.tsx
(initial measurement timing), and DesktopPolicies.tsx (three-line safety copy).
The original freeze bytes/checker remain unchanged; the V3 wizard exception remains
exactly preserved. No Electron main/preload/security-contract edit.

No user-profile migration or destructive data operation. All test databases,
messages, projects and generated images were synthetic/disposable. Existing
models, indexes, pairings, credentials, Studio permissions and old configurations
remain. The optional per-user OLIVE desktop entry is the only installed artifact;
no SDK/package/environment/system upgrade. It is collision-safe and not autostart.

CachyOS/KDE Wayland; KWin/KDE portal 6.7.5; application portal 1.22.1;
RemoteDesktop v2, ScreenCast v5, GlobalShortcuts v2; libei 1.6.0, PipeWire 1.6.9,
AT-SPI 2.60.7 and GStreamer 1.28.7. RTX 3080 Ti Laptop 16 GiB. Existing runtime:
Python 3.14.7, Node 24.21.0, Electron 44.3.0, Ollama 0.34.2, .NET SDK 10.0.401
and Temurin JDK 21.0.12.1+1. Normal `run_olive.sh` and C#/Java Studio journeys pass.
Native `.desktop` UI acceptance and native Windows acceptance remain pending.

FAST=qwen3:8b; NORMAL=gpt-oss:20b; MAX=qwen3-coder:30b;
DEEP=gpt-oss:20b plus the existing bounded extraction/retrieval/vision workflow;
REIMAGINE=SDXL. Public IDs, labels and semantics unchanged. Qwen Image remains
licence/acquisition/runtime-blocked. No cloud fallback, Jev, Laya or classification
model. The local vision evaluation does not promote a checkpoint or add remote vision.

## Inherited issue outcomes

All applicable inherited Electron assertions now pass in a **fresh full run**:
attach-diagnostics, m2-desktop, owned-launch, native GO find and responsive Studio.
The first three prove real policy/Stop/approval-cancellation boundaries, not live
portal injection. Native WinForms remains Windows-only, with its full Windows
journey retained and a passing Linux-unavailable-template check.

The 26-object shutdown warning was isolated to combined Qt test fixture lifecycle.
Explicit disposal of owned managers/bridges/deferred widgets removed it in the
36-test reproducer and final full Python run. No forced GC or warning suppression.
The vision evaluation additionally proved an unreachable retry contract; preserving
bounded token-limit metadata fixes that contract but does not fix model grounding.

## Verification

- Python: **1,154 tests; 1,146 passed, 8 skipped, 0 failed**, 135.310 seconds.
  No uncollectable-object warning in the final run.
- Connect: **240 passed** independently; also included in the final Python suite.
- Frontend: **96 passed**, 18 files. Typecheck, lint and production build passed.
- Electron: **55 passed, 16 skipped, 0 failed**, 71 tests, 7.7 minutes. Opt-in live
  tests and native Windows-only execution are distinguished in the suite.
- Repository Python source compilation: **688 passed**. Literal full-tree compileall
  was run and reports only the existing ignored PySide6 Jinja template error.
- Freeze: **225 accounted for; 3 approved exceptions; zero unauthorized changes**.

Portable runs use deterministic inference/unsafe-input substitutions while keeping
real permissions, storage, TLS, bytes, receipts and lifecycle tests. No hosted run
or Windows/macOS/mobile result is claimed. Full logs remain local; only bounded,
content-free evidence is committed.

## Measured limits and incomplete deliverables

The installed qwen3-vl:8b Q4_K_M artifact was evaluated on three synthetic layouts,
two trials each. Before/after the bounded retry repair: correct grounding **1/6 →
2/6**, median completion **20.863 → 67.350 seconds**, sampled whole-GPU maximum
**7451 → 8251 MiB**. Valid JSON/labels did not guarantee correct coordinates.
The visual-input gate failed; screenshot-driven actions stay disabled. No private
reasoning was retained. See both exact-digest manifests for individual outcomes.

The user approved live acceptance, but no compositor global Stop activation was
received. One action registration succeeded; later consent timed out or was denied/
cancelled. No saved OLIVE key assignment was found. The agent did not operate its
own consent dialog. No real capture/input or GUI task was claimed successful.

Still required: human Stop/source consent; measured actual capture/input and cleanup;
real Firefox/Kate/Dolphin/owned-messenger tasks; broader natural-language scope,
file/edit workflows and existing-window activation; reliable visual grounding;
physical-takeover safeguards; real multi/fractional/rotated-display acceptance;
Chat/DEEP/C7/SDXL handoffs; desktop-entry UI acceptance and later authorized hosted
validation. Discord has no real navigation/send evidence and no official GUI-
automation exemption. These are substantive incomplete items, not inferred passes.

The implementation status is **IMPLEMENTED** for the guarded adapter/task foundation
and independent repairs, **BENCHMARKED—FAILED GATE** for screenshot grounding,
**BLOCKED** for live control without human Stop/consent, and **PENDING/NOT COMPLETE**
for broad application workflows. There is no promoted model or accepted live operator.

## Use and rollback

See [normal-launch and human Stop steps](../../features/desktop-control-linux.md#normal-launch-setup-and-next-human-controlled-test).
Trusted tasks default Off. A first `Open Kate` request only prepares the shortcut;
verify it from another app, then explicitly Reset Stop and submit a new task before
handling source/device consent. Do not use a private or busy desktop for acceptance.

For exact source rollback, close OLIVE, ensure no local uncommitted work, then:

```
git switch feature/olive-backend-models-v3
git rev-parse HEAD
# Expected preserved checkpoint: 2df73b31ca11374978363a8f9d9c34ab052a74a4
./run_olive.sh
```

Do not reset history or delete profiles, indexes, models or toolchains. The optional
managed launcher can remain and follows the checked-out source. Preserve a modified
user entry; no automatic removal is needed. This branch and its evidence remain
available for resuming the pending human-controlled acceptance.
