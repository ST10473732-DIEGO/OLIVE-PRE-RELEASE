# Supplied repository and text-model review

Reviewed 24 September 2026. External source snapshots were stored outside OLIVE's
import/plugin paths. No upstream installer, launcher, plugin or test suite was
executed. This is a scoped source review, not an exploit audit or validation of
publisher performance/refusal claims. No source code or system prompt was copied.

| Exact supplied repository / pinned revision | Inspected sources | Evidence and OLIVE decision |
|---|---|---|
| [USB-Uncensored-LLM](https://github.com/techjarves/USB-Uncensored-LLM/tree/5cf6e1a04e217d07978cec5aa8cf8514c0428796) | README, repository tree, Shared/config/models.json, Shared/chat_server.py, Linux/start.sh and install.sh; OS launcher layouts | Archived/deprecated runtime/catalog application, not new weights. Catalogue identifies HauhauCS. Shared model storage is useful; OLIVE retains its existing store/lease owner. Server binds 0.0.0.0; Linux launcher uses wildcard origins and forceful cleanup. None of those defaults were adopted. No standalone code licence found in the inspected tree; no copying authorized by mere public availability. |
| [Portable-Local-Studio](https://github.com/techjarves/Portable-Local-Studio/tree/6c3059443666edba1d5ad7f72ec42afad1ca779e) | README, MIT LICENSE, App.jsx, TextChat.jsx, ModelManager.jsx, serve.cjs, linux.sh, setup-llama.sh, worker/setup layout, issue-regressions.test.cjs | Distinct text/image/speech engines, mutually exclusive heavy engines and retained conversation state are relevant principles. OLIVE already has shared residency and app-owned stores; keep them. Server listens on 0.0.0.0 with wildcard CORS, including APIs: rejected. Reasoning display/extraction is not adopted. README explicitly does not support Qwen Image's multi-component workflow. Keep ComfyUI; voice remains future work. |
| [AEON Qwen3.6 / DFlash](https://github.com/AEON-7/Qwen3.6-27B-AEON-Ultimate-Uncensored-DFlash/tree/558bc694ef71ec85fc927b85c5a562f7acf1df38) | README, Apache-2.0 LICENSE, container/recipe and speculative-decoding test/source layout | Supplied quickstart explicitly targets ARM64 DGX Spark/GB10 and Blackwell NVFP4. Not run on this x86_64 Ampere laptop. DFlash is target/draft speculative decoding, not prompt text; container limitations do not disprove other implementations. No local acceleration or lossless-quality claim. Defer a draft-model trial until an answer baseline justifies extra acquisition/runtime work. |
| [qwen38-uncensored](https://github.com/Wassimyounes01/qwen38-uncensored/tree/fffca789e393a2d9c93d37e14c97cfc55a074eb1) | README, MIT LICENSE, package.json, bin/install.cjs, lib/platform.cjs, lib/profile.cjs, Modelfile, examples/chat.cjs, test/profile-test.cjs | Default modified-weight and legacy official-weight-plus-prompt routes differ. Linux Q4_K_M/8192/all-GPU defaults do not measure available VRAM. Moving resolve/main URLs and coarse existing-file size checks are insufficient provenance. SYSTEM metadata includes capability/benchmark claims and legacy identity inconsistent with the newer default. Reject those prompt/hardware/download defaults; use pinned artifacts, conservative context and measured allocations. Tests assert profile metadata, not OLIVE answer quality. |

The explicitly linked [AEON Qwen3.8 successor](https://github.com/AEON-7/Qwen3.8-27B-AEON-ULTIMATE-UNCENSORED/tree/c94b74ba8e5f39360013070b1bd960e2cb04f1b0)
was inspected as a **related README**, separately from the supplied Qwen3.6 source.
No successor weights or container were acquired. Its broader hardware recipes do
not become measured results on this laptop.

## Adaptation ledger

| Source idea → existing gap | Adaptation | Dependencies / data / measurable check |
|---|---|---|
| R1 shared artifacts; R2 engine ownership → avoid future per-app runtimes | Retain Core ModelResidencyService and verified manifests; Candidate A cache/import shares the same inode rather than a duplicate weight copy | No new server/application dependency. Existing leases and cancellation remain. Record actual artifact hashes and GPU residency. |
| R2 ordinary streaming; R4 explicit think=false example → model-native controls differ | Add validated thinking control only for explicitly configured local model profiles. Keep answer text outside planner schemas and keep hidden reasoning out of persisted/displayed content | Existing Ollama adapter; no copied SYSTEM block. Compare first visible output, completion, actual model digest and code behaviour. |
| R4 coarse reuse → wrong/stale files could masquerade as ready | Pin revision/full manifest, exact size and SHA-256; stage .part files and publish only after verification | Existing Ollama blob store, no external install hooks. Failed validation preserves previous files/tags. |
| R2 retained navigation state → Copy was remounting during status refresh | Stable Markdown CodeBlock component identity, native clipboard IPC and regression against refresh | Existing React/Electron only. Actual native Copy activation → Kate paste matches exact bytes. |
| R3/R4 advertised capabilities → misleading runtime status | Separate publisher claims, architecture support, actual image/projector roles, answer quality and planner readiness | Report evidence instead of embedding model-card statistics in the system prompt. No MTP or DFlash acceleration claimed. |

## Acquired artifacts and access

The pre-download manifest is `docs/evidence/chat-text-model-acquisition.json`.
Total verified acquisition: **21,791,142,154 bytes** (about 20.30 GiB), below the
30 GB authorization. Recorded free disk before acquisition exceeded 400 GB.
No optional A projector, alternate precision, third candidate or base model was
fetched. Existing weights and public preset assignments were retained.

- **A:** HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive, revision
  `0a41c68809d375475f954be12ba7c40efa56c2a9`, Q6_K, 7,359,259,008 bytes;
  SHA-256 `c0ba7beb68fd3fe47891bd549486d38dcf62d00817296ea314ad37017f5a4986`.
  Imported as internal `olive-eval-hauhau-q6:20260924`, Ollama manifest
  `022de4bfdd9d4c16141f8c30846f155c51cf7a5b91090a24dcb63a7dbeddec07`.
  Model metadata lists Apache-2.0 and Qwen3.5-9B base. Publisher modification/
  losslessness claims are not independently established by this trial.
- **B:** author-linked public Ollama distribution
  `orcarouter/Qwen3.8-27B-Uncensored:q3_K_M`, full manifest
  `4da593b4aaed076b41e22b07f680075ff3856c46802f64866c353ac2b1a4fbcd`.
  Exact weight/projector/config/layer sizes and digests are in the manifest.
  HF file access is gated; no contact-sharing agreement or account gate was
  accepted. Its public publisher-linked distribution was available without that
  gate. Apache-2.0 metadata and the publisher's separate research-use language
  were inspected for this benign local evaluation. No hosted OrcaRouter API used.

Evaluation uses installed Ollama 0.34.2, existing loopback service/resource
manager, 4096 context and explicit internal model configurations. No maximum-GPU
flags, remote code loader, copied capability prompt or new refusal model. GUI-Owl
remains the independent desktop grounding baseline.

The first A trial used model-default thinking: it exhausted 2048 output tokens
in 39.85 seconds with **zero visible answer characters**. The repair trace
identified this after correct answer routing; it was not a refusal or a code
schema parse failure. The public error previously hid this distinction. The
adapter now reports the specific budget/empty-answer condition without revealing
reasoning. Subsequent explicit think=false trials are recorded separately.

Model-quality results, compilation checks and any promotion decision are in the
Chat repair report. No promotion has been made at this checkpoint. Candidate tags
are optional local evaluation configurations; rollback is simply to keep/use the
unchanged public presets. No pruning or migration away from Ollama was performed.

## Held-out local answer decision after 9e4d915

The finite follow-on gate retained both candidate digests and acquired no model.
A passed 13/14 primary cases and 3/3 implicit-context/longer-context supplements,
but **failed the unchanged Python behavior gate**: NaN raises
`decimal.InvalidOperation` rather than the requested `ValueError`. B passed
14/14 plus 3/3 and two compiled production Chat turns in an isolated local-only
profile, including a retained-constraint follow-up. B therefore passes this
finite local answer/code role. The actual installed `gpt-oss:20b` baseline passed
13/14 plus 3/3; its generated Python incorrectly accepts `0.001` after rounding.
No candidate code was repaired. Earlier measured failures remain historical;
newly performed passing checks do not erase them.

A/B used think=false, temperature 0.2, output 2048, context 4096 with explicit 8192
context cases. The baseline used its native think=low profile. All passed streamed
cancellation/recovery. Resource and latency limitations, exact prompts/outputs,
compilers and digests are in [the closeout](../agent/OLIVE_AGENT_FREEFORM_CLOSEOUT.md#text-model-decision)
and [raw gate evidence](../../evidence/freeform-closeout/answer-gate.json).
The longer context supplement used 4,704 prompt tokens for A/B in an 8192 window;
it does not establish maximum context. Cache and partial regression overlap
prevent a controlled speed ranking. No equivalent-base uncensoring claim is made.

Candidate-specific shared C7 validation remains unperformed, not failed. Public
presets, remote mappings and user overrides remain unchanged; B was active only
in the explicitly isolated evaluation profile. No public shared-preset promotion
is claimed. Chat-only candidates were not subjected to unrelated planner/GUI gates.
