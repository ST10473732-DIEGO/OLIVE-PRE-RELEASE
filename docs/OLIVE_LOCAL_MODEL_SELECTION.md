# Local model selection — V3

2026-09-23; no model promoted. Public mappings remain FAST/qwen3:8b,
NORMAL/gpt-oss:20b, MAX/qwen3-coder:30b, DEEP/gpt-oss:20b plus existing
bounded evidence/native extraction/vision, REIMAGINE/current media engine.
The requested HEAVY, PRO and IMAGINE names are planning correspondence only.

## Acceptance fixed before candidate measurements

`olive/evaluation/fixtures/backend_v3.json` contains 48 synthetic cases, including
12 held-out cases. Only development results may guide changes. Run held-out
cases once candidate configuration is fixed; do not modify expected answers
or tune prompts to them. Compiler tasks require source review, actual compiler
and execution checks; no substring-match claim of executable correctness.
Human rubric cases require 0/1/2 grading by the stated rubric. Pending review
is not a pass. Provider-contract cases are deterministic fault injection and
must be reported separately from live model accuracy.

Compare three repeated trials, identical case, output limit, sampler and
context. Report median/range, no p95 at this sample count. First trial is a
cold model residency transition, not a claim of a cold filesystem cache.
Cold-switch load is separate from warm visible-answer latency. Reasoning
stream spans are not exact GPU reasoning time. Peak resources are sampled
and therefore lower bounds, not allocator maxima. Do not compare unequal
output work without reporting output length/token counts.

Required promotion gates:
- No permission, injection, remote-scope or lifecycle regressions. All
  deterministic security cases and existing C1–C8 tests must pass.
- FAST: at least baseline correctness and 20% lower median warm visible-answer
  latency on the same cases; warm median <= 3 seconds, completion <= 20 seconds.
- NORMAL: no lower correctness; improve at least two failed baseline cases
  without worsening median completion by more than 25% (or improve latency
  by >=20% at equal correctness). Visible-answer median <= 8 seconds.
- MAX: improve executable/reasoning quality with completion median <= 90 s,
  visible-answer median <= 20 s. Explicit offload allocation recorded.
- DEEP: real scoped evidence support, no invented citations; <=120 s local
  work budget and at most one issue-triggered revision. Model-only tests do
  not establish the full workflow. Existing remote budgets take precedence.
- Retain at least 2 GiB VRAM and 8 GiB available RAM with desktop/OLIVE running;
  no swap growth attributable to the run. Missing telemetry blocks promotion.
- Held-out and human/compiled results complete, no truncation or failures
  hidden as success; exact digest/template/quantization recorded.

These targets are proposed engineering gates fixed before measurements; the
baseline will show where current behavior misses them. Failed gates retain
current defaults. No migration is justified until promotion evidence exists.

## Verified sources and artifact provenance

[Qwen 4B](https://huggingface.co/Qwen/Qwen3.5-4B),
[9B](https://huggingface.co/Qwen/Qwen3.5-9B),
[27B](https://huggingface.co/Qwen/Qwen3.8-27B), and the
[Ollama Qwen3.5](https://ollama.com/library/qwen3.5/tags) /
[Qwen3.8 registry](https://ollama.com/library/qwen3.8/tags) were inspected.
The acquisition manifest pins registry manifest and layer digests. Config blobs
verify Q4_K_M for all three; 4B/9B require Ollama >=0.17.1, 27B >=0.32.12.
Installed runtime is 0.34.2. All approved text artifacts loaded successfully in the live comparison.
The registry's built-in qwen3.5/qwen3.8 renderers own tokenizer/template use;
OLIVE does not construct a substitute chat template.

[Gemma 4 12B](https://huggingface.co/google/gemma-4-12B-it) is a possible
Apache-2.0 vision/general challenger. The user approved its pinned Q4_K_M
artifact; it was downloaded and compared, without promotion. Existing
[gpt-oss](https://openai.com/index/introducing-gpt-oss/) remains a baseline.
Vendor model-card scores are not laptop benchmark measurements.
[Thinking controls](https://docs.ollama.com/capabilities/thinking),
[context allocation](https://docs.ollama.com/context-length) and
[local-only settings](https://docs.ollama.com/faq) were checked. This runtime's
installed baseline /show responses omit thinking.values; their controls remain
explicitly unverified metadata, not inferred proof that a flag was honored.

## Live development results

All 30 strict-output development cases were run three times per model: **630
responses**, 90 per model. All 630 completed with valid schema; no truncation or provider failure was
recorded. Host swap grew during some samples (maximum per-request increase
733,335,552 bytes). This is host-wide telemetry and cannot be attributed to
inference alone; the no-swap promotion gate is not established. Exact-answer correctness
is narrower than semantic correctness: for example, an alternative plural can
fail a fixed string expectation. Expected answers/prompts were not revised to
favor any model. Do not read these scores as broad coding-quality percentages.

| Artifact | Exact / 90 | Warm visible median [range], ms (n=89) | Completion median, ms (n=90) | Cold load, ms (n=1) | Peak sampled VRAM, MiB |
| --- | ---: | --- | ---: | ---: | ---: |
| `qwen3:8b` | 63 | 29.4 [18.8–53.9] | 151.9 | 3106.9 | 5680 |
| `gpt-oss:20b` | 66 | 508.5 [295.2–1963.3] | 606.3 | 5240.1 | 12604 |
| `qwen3-coder:30b` | 72 | 30.9 [17.2–185.1] | 206.9 | 7279.5 | 14968 |
| `qwen3.5:4b` | 57 | 78.8 [54.2–113.2] | 238.9 | 12306.4 | 4076 |
| `qwen3.5:9b` | 63 | 75.7 [55.3–113.7] | 301.3 | 3823.7 | 6605 |
| `qwen3.8:27b` | 69 | 12895.4 [6043.8–43325.8] | 14228.6 | 4314.2 | 11051 |
| `gemma4:12b` | 57 | 82.4 [74.8–98.1] | 382.1 | 11629.3 | 8395 |

The content-free [result manifest](evidence/backend-v3-benchmark.json) includes
per-case sample counts, medians/ranges, artifact digests/template hashes,
quantization, context, thinking settings, output character/token distributions,
prefill/decode rates, reasoning stream spans, placement bytes and RAM/swap.
No p95 is asserted. Each cold load is one residency transition, with warm OS
file caches possible. One-second memory samples can miss short allocation peaks.

Contexts were 4,096 for all except Qwen3.8 (8,192, explicit `num_gpu=40`).
Sampler: temperature 0, seed 42, output limit 512. gpt-oss used `think=low`,
Qwen3.8 `think=true`, others `think=false`, matching their evaluated roles.
Ollama 0.34.2 owned tokenization/rendering; no substitute template was supplied.
These differing architectures/policies and variable output lengths make raw
completion times unequal work. The quantized offload result is not a controlled
same-context causal estimate or a transfer of vendor full-precision benchmarks.
KDE and real V2 OLIVE windows were running; some verification jobs also ran.
A promotion would require a quieter paired confirmation and all workflow gates.

## Decision

- **FAST:** Qwen3.5 4B was slower to first visible answer and scored lower than
  qwen3:8b. Retain the existing default.
- **NORMAL:** Qwen3.5 9B was faster than gpt-oss but scored lower (63 versus 66).
  Gemma4 12B also scored lower (57). Neither met the no-quality-regression gate.
- **MAX/DEEP quality candidate:** offloaded Qwen3.8 scored 69 versus the coder
  baseline's 72, with much longer visible delay. The larger context does not
  establish an earned quality improvement. Do not promote it for either mode.
- **Resource caveat:** the existing coder baseline reached 14,968 MiB at only
  4K context, leaving less than the proposed 2 GiB GPU headroom. Retaining it is
  compatibility, not certification that the old default meets the new gate.
  Conservative placement needs further paired workflow measurements before a
  separate resource-policy/default change. Qwen3.8 offload retained headroom.

No configuration migration occurred. All user settings and the exact baseline
artifacts remain available. No Q5/Q6, secondary specialist, embedding, reranker,
MTP or speculative-decoding downloads were justified by this first comparison.
Held-out strict cases remain reserved: no candidate passed the development gate.
Compiler and subjective smoke checks are reported separately; they cannot
reverse these failed promotion gates or prove a universal quality winner.

## Reproduce locally

With an idle owned loopback Ollama and the approved installed digests:

```sh
.venv/bin/python scripts/backend_v3_benchmark.py --models qwen3:8b gpt-oss:20b qwen3-coder:30b --trials 3 --context 4096 --output /tmp/olive-baselines.json
.venv/bin/python scripts/backend_v3_benchmark.py --models qwen3.5:4b qwen3.5:9b gemma4:12b --trials 3 --context 4096 --output /tmp/olive-small.json
.venv/bin/python scripts/backend_v3_benchmark.py --models qwen3.8:27b --trials 3 --context 8192 --num-gpu 40 --output /tmp/olive-quality.json
.venv/bin/python scripts/backend_v3_collect_review.py --models qwen3-coder:30b qwen3.8:27b gemma4:12b --output /tmp/olive-review.json
```

The runner refuses pre-existing resident work and unloads only its leased model.
The review collector does not execute answers. Inspect pure generated sources
before compiling in disposable owned fixtures; record compiler exit status and
positive/negative/zero input assertions. Never treat generated tool names or
claimed tests as executed evidence. Keep raw answers out of committed reports.

## Reviewed compiler and subjective smoke checks

The [review manifest](evidence/backend-v3-reviewed.json) records 28 compiler
cases (four languages × seven models), one sample each. All inspected addition
functions compiled and passed three runtime assertions: positive addition,
cancellation to zero and zero inputs. C#/Java required normal class/entry-point
wrappers. Two coder answers violated “no Markdown”; their fences were removed
only after inspection and remain recorded as raw-format failures. This simple
smoke set cannot distinguish demanding coding ability.

The first broad execution command was rejected by automatic approval review.
Before execution, every exact source was checked against a fixed addition-only
allowlist and its reviewed hash; execution then ran with restricted filesystem
and network access and local package sources cleared. No general model-authored
operation or arbitrary tool name was executed.

Subjective results use the stated 0/1/2 rubric and agent inspection, not an
independent human panel. All seven summaries preserved the two-case/one-failure
facts without inventing a cause; all seven missing-image answers acknowledged
no visual evidence. Several South African “now-now” answers added unsupported
cultural or timing claims; Qwen3.8 exceeded the fixed 120-second bound on that
case. The [Dictionary of South African English](https://dsae.co.za/entry/nownow/e05259)
was used to check temporal senses, not to tune prompts or expected answers.
The held-out missing-image rubric was consumed; the strict held-out subset
remains unused because all candidates failed their development promotion gate.

For Linux compiler reproduction, after reviewing the answers, create an explicit
JSON mapping from `model/case` to each reviewed answer's SHA-256, then run:

```sh
.venv/bin/python scripts/backend_v3_compile_review.py --answers /tmp/olive-review.json --reviewed-hashes /tmp/olive-reviewed-hashes.json --output /tmp/olive-compiler-results.json
```

The harness independently rejects any source other than the fixed pure addition
definitions; reviewed hashes alone do not authorize arbitrary source. It refuses
to overwrite results, uses disposable projects and clears NuGet sources. It is
a Linux local verification tool, not a new Studio/Remote Studio execution path.
