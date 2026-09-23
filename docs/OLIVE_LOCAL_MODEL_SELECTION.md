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
Installed runtime is 0.34.2. Actual model load remains a separate gate.
The registry's built-in qwen3.5/qwen3.8 renderers own tokenizer/template use;
OLIVE does not construct a substitute chat template.

[Gemma 4 12B](https://huggingface.co/google/gemma-4-12B-it) is a possible
Apache-2.0 vision/general challenger, not yet acquired. Existing
[gpt-oss](https://openai.com/index/introducing-gpt-oss/) remains a baseline.
Vendor model-card scores are not laptop benchmark measurements.
[Thinking controls](https://docs.ollama.com/capabilities/thinking),
[context allocation](https://docs.ollama.com/context-length) and
[local-only settings](https://docs.ollama.com/faq) were checked. This runtime's
installed baseline /show responses omit thinking.values; their controls remain
explicitly unverified metadata, not inferred proof that a flag was honored.
