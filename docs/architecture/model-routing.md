# Model routing

OLIVE chooses local models in two separate layers. Both use only models already
installed in Ollama; OLIVE never downloads a model to satisfy a request.

## 1. Public Chat presets (fixed models)

Each Chat mode maps to a fixed model or pipeline in `olive/services/presets.py`
([chat modes](../features/chat-modes.md) describes them for users):

| Preset | Model / pipeline | Notes |
| --- | --- | --- |
| FAST | `qwen3:8b` | |
| NORMAL | `gpt-oss:20b` | |
| MAX | `orcarouter/Qwen3.8-27B-Uncensored:q3_K_M` | Pinned manifest digest `4da593b4…bcd`; rollback mapping `qwen3-coder:30b` (`PREVIOUS_MAX`) |
| UNCENSORED | automatic router | `olive/services/uncensored_router.py` picks among installed reduced-refusal models; local Ollama only |
| NOW | `qwen3.5:9b`, live pipeline | Web search and fetch, local synthesis with sources |
| DEEP | `gpt-oss:20b`, documents pipeline | Retrieval with citations; vision/OCR when available |
| REIMAGINE, AUDIO, VIDEO | media pipelines | ComfyUI / VoiceStudio engines, not Ollama text models |

## 2. Internal roles (measured candidates)

Internal work such as planning, vision, coding assistance and embeddings is routed
by role through `olive/agent/model_router.py` using the candidate lists in
`olive/services/model_policy.py` (`CANDIDATES`):

| Role | Candidates, in preference order |
| --- | --- |
| fast | `qwen3:8b`, `gpt-oss:20b` |
| general, reasoning | `gpt-oss:20b`, `qwen3:8b` |
| coding | `qwen3-coder:30b`, `devstral:24b`, `gpt-oss:20b` |
| vision | `qwen3-vl:8b` |
| embedding | `qwen3-embedding:0.6b` (`DEFAULT_EMBEDDING_MODEL`, also the settings default) |

A compatible manual override wins. Otherwise measured local benchmark results,
when present, outrank the list order; callers can opt to keep an already-loaded,
adequately measured candidate to avoid a model switch. If no embedding model is installed, document
retrieval stays lexical and diagnostics report semantic retrieval as off.

The rest of this page is the original local-model-stack record, including the
6 September 2026 measurements on the Windows reference machine.

## Local model stack (record)

Roles are fast, general, reasoning, coding, vision and embedding. Settings → Models
provides automatic/performance/balanced/quality modes, explicit compatible overrides,
context budgets, benchmark results and opt-in refresh. Role selection uses installed
capabilities; image requests never fall back to a text-only model.

Initial candidates are qwen3:8b for fast work, gpt-oss:20b for general/reasoning,
qwen3-coder:30b and devstral:24b for coding, qwen3-vl:8b for vision, and
qwen3-embedding:0.6b for embeddings. Local fixtures inform selection; they are not
universal quality rankings. Model downloads are not part of the benchmark.

The residency service serializes managed inference and reuses consecutive models.
It unloads its previously managed model when switching rather than keeping several
large models resident. It does not evict unrelated clients' models. This reduces
pressure on the tested RTX 3080 Ti Laptop GPU's 16 GiB VRAM; it is not a guarantee
that every model fits entirely in VRAM. Ollama can offload larger models to RAM.

Default role contexts are bounded instead of using advertised maxima. User overrides
remain validated. The desktop planner uses fast for one inspected app and reasoning
for multiple apps; deterministic UIA and shell actions use no model. Vision is an
explicit authorized observation path.

Live diagnosis found that forcing `think=False` on this installed qwen3-vl returned
empty final content. The vision path preserves the default and allows a bounded
1536-token result budget and one bounded 3072-token retry with a shared 90-second
deadline. Internal reasoning is never
displayed or used as an executable instruction. Invalid final schemas fail closed.

Benchmark data is stored in `model_benchmarks.json` when run through the application.
Opt-in acceptance scripts use disposable or ignored output files. Current fixtures
are deliberately small; larger repository-quality evaluation remains necessary.

## Local measurement, 6 September 2026

RTX 3080 Ti Laptop GPU, 16 GiB VRAM; 64 GiB system RAM; i9-12900HX.
Twenty-one short fixtures ran sequentially, with no model downloads.

| Model | Exact fixture successes | Mean request time including first load |
| --- | --- | --- |
| qwen3:8b | 4/5 | 1.310 s |
| gpt-oss:20b | 4/5 | 3.424 s |
| qwen3-coder:30b | 3/5 | 3.869 s |
| devstral:24b | 4/5 | 3.465 s |
| qwen3-vl:8b | 1/1 | 10.513 s |

Devstral passed all four coding JSON fixtures and failed the actual tool-call fixture;
qwen3-coder passed two coding fixtures plus the tool-call fixture. Devstral is the
provisional coding-quality choice for these fixtures. Qwen3:8b remains useful for fast
structured work; its tool-call fixture failed, so tool requests still require strict
validation. The single vision fixture is a basic OCR check, not a general vision score.
These latest results were persisted in the application benchmark repository. The
separate custom-painted window localization test fails with empty final content,
including a bounded retry. It must not inherit the basic OCR fixture's success.
General and reasoning currently share the small general-fixture score; use a manual
role override when distinct reasoning selection is required pending richer evaluation.

## Measured roles and residency (6 September 2026)

The measured policy then selected qwen3:8b for Fast, General and Reasoning,
devstral:24b for Coding, qwen3-vl:8b for Vision and qwen3-embedding:0.6b for Embedding.
Equal general-fixture quality plus lower latency favours qwen3:8b; this does not prove
parity on complex reasoning. A compatible manual gpt-oss:20b override remains available.

A bounded live sequence verified the custom-painted Preview label, then a structured
reasoning response. Ollama reported only qwen3-vl resident (5.79 GB), then only qwen3:8b
(5.27 GB), with one managed switch and no errors. Reasoning took 6.47 seconds including
load. Deterministic desktop operations use no model.

Diagnostics identify the installed thinking renderer/parser exhausting localization
budgets before final JSON. A smaller label schema succeeds (79 tokens, about 6.4 seconds).
Only counts and finish reason are exposed; reasoning text is not. See docs/features/desktop-control-windows.md.


OLIVE was formerly named DMDO. See [the rebrand compatibility map](legacy-dmdo-compatibility.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
