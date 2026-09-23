# OLIVE backend V3 implementation and acceptance

2026-09-23. Branch: `feature/olive-backend-models-v3`.
DESIGN_BASE: `50003790c42aff620d63d664dff89c0338347cab`.
Both the existing implementation branch and `feature/olive-design-v2` pointed
at this commit at inspection; the worktree was clean. No reset, stash, history
replacement, push, merge, tag or release. No tracked CLAUDE.md was present.

## Status

- **IMPLEMENTED:** SDK/JDK discovery and refresh, truthful readiness, native
  launcher environment, strict inference completion, artifact metadata,
  finite context/stream/queue budgets, preserved historical constraints,
  portable fixtures and an auditable design freeze.
- **BENCHMARKED:** installed local baselines and approved candidates. See
  [model selection](OLIVE_LOCAL_MODEL_SELECTION.md) and content-free evidence.
- **PROMOTED:** none. Current mappings and user overrides remain unchanged.
  Installing weights is not a product-quality promotion.
- **BLOCKED:** Qwen Image licence review, separate image download approval,
  compatible pinned ComfyUI nodes and measured hardware acceptance.
- **DEFERRED:** optional embedding/reranker replacement, speculative decoding,
  further precision/specialist trials, Mobile/C9 implementation and C10.
  No evidence justified these additions in this milestone.

## Design and data preservation

`evidence/backend-v3-frozen.json` pins 225 baseline files across `desktop/src`,
Electron, public assets, approved design/C9 documents, identity and Qt tokens.
`scripts/check_design_freeze.py` compares their bytes with immutable Git bytes
and enumerates the filesystem, including ignored/untracked additions and
symlinks. Added/deleted/changed lists must be empty except the exact approved
hash in `evidence/backend-v3-frozen-exception.json`.

The user approved one state-only exception in `NewProjectWizard.tsx`:
retain the created workspace in the result and open it on Done/close.
Immediate opening unmounted the first-workspace wizard before Created/Done
could be shown. No CSS, tokens, layouts, labels, icons or bridge contract changed.
No other production renderer change is authorized or made.

All runtime tests use disposable synthetic profiles/workspaces. No chats,
credentials, pairings, personal files, indexes or existing SDKs were migrated,
overwritten or deleted. Model acquisition was additive; previous tags/digests
are recorded in `evidence/backend-v3-host.json`. No data/default mapping
migration was necessary, so no migration is represented as tested.

## Host and normal launch

CachyOS/KDE Wayland, x86_64 i9-12900HX, 24 logical CPUs, 64,016 MiB RAM;
RTX 3080 Ti Laptop 16,384 MiB VRAM, driver 615.71.09. Driver CUDA advertisement
13.4 differs from verified ComfyUI PyTorch CUDA runtime 13.0 (compute 8.6).
Initial available RAM 57,065 MiB, free disk 415 GiB. Detailed versions and
baseline digests are in `evidence/backend-v3-host.json`.

The existing repo tooling is Python 3.14.7, Node 24.21.0/npm 11.19.0,
Electron 44.3.0 and Ollama 0.34.2. No assumption of global npm was needed.
Ollama was initially stopped; the normal launcher started an app-owned,
loopback-only service with `OLLAMA_NO_CLOUD=1`, one loaded-model limit and
no pruning. Existing profiles/services were not commandeered.

[Toolchain acceptance](OLIVE_TOOLCHAIN_REPAIR.md) records .NET SDK 10.0.401,
runtimes 10.0.12, OmniSharp 1.39.15, netcoredbg 3.2.0-1092 and the approved
local Temurin JDK 21.0.12.1+1. Real builds, structured MSTest, diagnostics,
breakpoints, interactive C# input, Java run/Stop and owned-process cleanup
passed. Two normal `run_olive.sh` restarts report C# and Java ready and open
Studio, Chat, Devices, GO and REIMAGINE. No OLIVE desktop entry was found in
the standard user locations; desktop-entry launch is not claimed.

## Public contracts and model handling

| Public label / ID | Existing and retained default | Requested planning term |
| --- | --- | --- |
| FAST / `fast` | `qwen3:8b` | FAST |
| NORMAL / `normal` | `gpt-oss:20b` | NORMAL |
| MAX / `max` | `qwen3-coder:30b` | HEAVY |
| DEEP / `deep` | `gpt-oss:20b` plus existing extraction/retrieval/vision | PRO |
| REIMAGINE / `reimagine` | Existing SDXL/media engine and raster editing | IMAGINE |

No naming migration, sixth mode, misleading attribution or protocol change.
DEEP is still a bounded evidence workflow, not a fourth mandatory checkpoint.
Native extraction and local privacy scopes remain separate from remote C7.
No extra router model, automatic model chain, cloud fallback or hosted embedding
was added. Studio's assistant remains answer-only under its existing policy.

The existing model registry now reports real digests, quantization, backend,
template hash and verified thinking controls where `/api/show` supplies them.
Failed metadata reads are not permanently cached; changed digests invalidate
metadata. Ollama owns the architecture tokenizer/chat template. Missing thinking
metadata is reported as unverified rather than fabricated support.

Inference now rejects empty, incomplete and length-truncated completion as
successful final output, including the measurement adapter. SDK fragmented
UTF-8 decoding is tested. Reasoning fields count toward activity and measured
reasoning duration but never become answer text, audit/C5/C7 content or saved
benchmark prompts. Strict schema/action validation remains outside models.

Startup (90 s including stream creation), inactivity (45 s) and total (300 s)
stream deadlines are separate and finite. Existing C7/caller deadlines remain
stricter where applicable. Stream closure is awaited inside the residency lease;
cleanup and next-request recovery are tested. The existing shared resource
manager admits at most four waiting inference requests. Media ownership and
C7 cancellation contracts remain intact; no GPU reset or forced unrelated unload.

Conversation summaries retain older user/system constraints with provenance,
including negations and selected scope. Final context accounting reserves output
and vision estimates and includes product/system framing. Oversized critical
context raises an explicit error before mutating the summary. Character/vision
estimates are conservative approximations, not exact architecture token counts.
No advertised 128K/256K allocation is enabled. Retrieval indexes are unchanged:
there is no demonstrated retrieval failure justifying incompatible-vector migration.

## Verification ledger

The unmodified starting Python baseline passed 1,094 tests with 11 skips.
The following figures are actual milestone runs, not historical targets.

- Canonical Python: **1,114 tests, 8 skips, passed** (160.381 s). The
  interpreter shutdown reports 26 uncollectable objects; it is recorded, not
  represented as a test failure or silently suppressed.
- Canonical portable Connect command: **240 passed** (89.069 s), also covered
  by the full Python run. Real TLS, authority, persistence, filesystem bytes,
  SQLite and exact-channel lifecycle tests remain enabled.
- Frontend: **96 passed in 18 files**; typecheck and lint clean; production
  Vite/Electron build passed, with the existing large-chunk advisory.
- Tracked-source compilation: **665 Python sources passed**. Literal
  `.venv/bin/python -m compileall -q .` encounters the known ignored PySide6
  Jinja template; that template is not repository Python source.
- Electron aggregate and live inference/media results are recorded below.
  Historical V2 counts are not substituted for results.

Commands use `.venv/bin/python` and the repository Node/SDK/JDK paths. Portable
CI still substitutes inference only; no GPU/weight downloads or hosted AI.
No hosted workflow was triggered because push is prohibited. Windows/macOS
native GPU, WinForms/debugger and mobile acceptance remain unclaimed.

## Image gate

[Qwen Image evaluation](OLIVE_REIMAGINE_QWEN_21.md) pins the proposed 17.283 GB
INT8 ConvRot diffusion/encoder and BF16 VAE components. The user selected
research/evaluation preparation only and retains licence review. Download
approval for text/JDK/Gemma does not cover images. Installed ComfyUI lacks the
required native 2.1 encoder/cache nodes; no Qwen weights were inserted into an
SDXL graph. No image upgrade, transparency result or commercial clearance is
claimed. Existing engine/default and original files are preserved.

## Rollback

Model/config rollback requires no action: defaults and overrides never changed.
Keep the baseline digests in `evidence/backend-v3-host.json`; installed candidates
can remain unused. Do not prune models, reset a user worktree or delete profiles.

For code rollback, first finish/close owned work and preserve any subsequent
user changes. On a clean branch, create a rollback branch and revert this
milestone's commits in reverse order (the final commit list below is authoritative).
`git revert --no-commit <newest> ... <oldest>` followed by a reviewed rollback
commit preserves history. Reverting `0caf404` restores the original wizard bytes
and removes its exception manifest. Reverting discovery restores prior lookup
behavior; the additive `.toolchains/jdk` installation may remain inert.
Do not remove SDKs or use `git reset --hard` as rollback.

## Stable client/Connect contracts

C7 remains `olive-inference/1`, `models.remote`, text-only presets `fast`,
`normal`, `max` resolved on the target. Bounds remain 24 messages, 16,000 bytes
per message, 48,000 input bytes, 2,048 output tokens, 64,000 output bytes and
120 seconds. Capability support never grants access to target Memory,
Knowledge, Mail, Studio, files, vision or media. No new enums/capabilities.
C8 remains revision-bound shared workspace view/edit/build/test/noninteractive
run: no remote shell, terminal, debug, LSP, Git, package installation or arbitrary
path/command. C5/C6 independence, read-only lookup rules, short transactions,
commit-boundary authority revalidation, EOF retirement, reconnect guarantees,
required receipts and fenced file cleanup are preserved and regression-tested.
Approved C9 design documents remain byte-identical; no iOS project was started.

### Electron aggregate and unresolved issues

The last complete default run: **47 passed, 14 opt-in skips, 7 failed** in
10.8 minutes (68 tests). C#/Java creation, C# interactive input, normal Linux
launch/restart, C7/C8 controlled transport/UI and portable fixture journeys pass.
A subsequent focused preview check passed after replacing an animation-waiting
screenshot helper with direct owned-window compositor capture (2.3 s). All
preview isolation, network restriction and Stop assertions were retained. This
is a focused result, not a fabricated 48-pass aggregate rerun.

| Remaining failure | Evidence / boundary |
| --- | --- |
| attach-diagnostics | Linux Desktop Control unavailable; same baseline platform limitation |
| m2-desktop | Native Desktop Control unavailable on Linux; no platform skip added |
| owned-launch | Linux desktop policy enablement rejected; target launch remains disabled |
| browser / GO | Native find-in-page reports zero matches; documented intermittent baseline issue; frozen Electron contract unchanged |
| responsive | At 640×480 the Studio explorer intercepts clicks on Output; exposed after portable fixture repair; frozen layout not changed |
| winforms-designer | Windows Forms template/native designer unavailable on Linux; .NET SDK presence does not imply WinForms support |

No timeout extensions, assertion removals, screenshot-expectation changes or
blanket retries hide these failures. The sole approved renderer exception does
not authorize the responsive-layout repair. This is not a green cross-platform
release acceptance or approval to begin C9 implementation.

### Live local acceptance

Four serial opt-in Electron journeys passed (2.0 minutes): real C7 remote FAST
cancellation → local Chat, DEEP scanned-PDF evidence with retained native page
and vision attribution, SDXL generate/edit/cancel/new generation → Chat, and
FAST → NORMAL → MAX → DEEP → FAST. Correct public attribution, one resident
text model, answer-only Studio boundaries, readable files, original preservation,
queue release and owned-process shutdown were asserted. These are local Linux
results, separate from deterministic provider substitutions and hosted CI.

The actual local provider answered correctly with non-loopback Python TCP
connections blocked before connect. Ollama remained local with cloud disabled.
This is a client-transport denial test, not a kernel-wide airgap or a packet-level
claim about the whole host. Final owned runtime cleanup left no recorded worker;
GPU usage returned to 115 MiB, with 382 GB free disk. Nothing was left running
as a background promise.

See `evidence/backend-v3-live.json` for bounded, content-free metadata. Generated
images and raw synthetic compiler/rubric answers remain ignored local artifacts;
no weights, environments, SDKs, private data or large binary outputs are committed.

## Implementation commits

Documentation/evidence-only commits follow this code history. The final branch
HEAD is reported at handoff; no history was rewritten.

- `452346d` — Establish V2 freeze and versioned local backend evaluation gates
- `58c0d28` — Repair shared SDK and JDK discovery and refresh truthful Studio readiness
- `bf62e65` — Validate measured inference completion and track installed artifact metadata
- `0041f09` — Preserve request constraints and enforce finite context and inference queues
- `0caf404` — Preserve new-project completion until Done under the approved V2 exception
- `8576558` — Use native interpreters and portable process inspection in Electron fixtures
- `29da1d3` — Bound provider stream startup inactivity and total lifetime
- `3812fe7` — Count stream creation against the shared startup deadline
- `abafe55` — Verify frozen path additions and repair stale native UI test selectors
- `d593715` — Record approved acquisitions and make pinned local JDK setup reproducible
- `26e2862` — Capture preview evidence portably and detect substituted frozen roots
- `c679255` — Verify live model media handoffs and reproducible reviewed compiler fixtures


To reverse the entire current milestone, including its reports, from a clean
worktree (review the resulting staged diff before committing):

```sh
git switch -c rollback/olive-backend-v3 feature/olive-backend-models-v3
git revert --no-commit 50003790c42aff620d63d664dff89c0338347cab..feature/olive-backend-models-v3
git diff --cached --stat
git commit -m "Revert OLIVE backend V3 milestone"
```

If the implementation branch has advanced since handoff, substitute the exact
final handoff commit for the branch reference in both commands. This leaves
all profiles, installed weights, SDKs and original user files intact. Resolve
any later user changes explicitly; do not reset, stash or discard them.
