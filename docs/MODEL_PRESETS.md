# OLIVE public presets

Presets are product settings and pipelines, not OLIVE-trained models. Runtime
identity remains Ollama's original tag and digest; no display aliases duplicate
weights. Advanced Settings exposes both the current conversation provider and
the separate tool/research role policy. Existing chats without a preset retain
their exact model tag, generation settings and messages; the picker labels this
compatibility state "Previous selection · Advanced". New conversations use NORMAL.
Unavailable providers report Needs setup without hosted or paid fallback.

Live native Calendar/Task/Mail acceptance exposed invented optional fields and
incorrect follow-up slots from the FAST provider. Structured native record and
communication interpretation now uses the separate measured reasoning role
(gpt-oss:20b here), while conversational answers keep their selected preset and
direct path. This is a correctness/latency tradeoff, not a claim of universal
model reliability. The role remains inspectable in Advanced Settings.

| Preset | Installed default | Pipeline |
| --- | --- | --- |
| OLIVE FAST | qwen3:8b | Direct text/code; 4,096 output-token ceiling |
| OLIVE NORMAL | gpt-oss:20b | Direct text/reasoning; 4,096 output-token ceiling |
| OLIVE MAX | qwen3-coder:30b | Direct text/code; 8,192 output-token ceiling |
| OLIVE DEEP | gpt-oss:20b + qwen3-vl:8b when relevant | Native extraction, bounded retrieval, source/page metadata, up to three relevant images/pages via vision, then text synthesis |
| OLIVE REIMAGINE | Pillow; approved ComfyUI 0.35.0 / SDXL base 1.0 | Verified local crop/resize and real 1024×1024 generation/image-to-image; per-profile engine setup, progress/cancel and measured GPU handoff. Video remains unavailable. See BROWSER_AND_MEDIA.md |

Native PDF text and tables are extracted first. Existing OCR applies only to
pages meeting the insufficient-text/image heuristic when OCR is available. DEEP
can inspect explicitly numbered PDF pages or pages selected by retrieved chunks
for visual questions; it does not claim to inspect every page. Vision descriptions
are labelled with their actual input source/page and provider, and remain fallible
interpretations. Unretrieved/unreadable content requires an explicit page or setup.
The shared residency service serializes managed model use and unloads the prior
managed model when switching. Task mode (Chat/Search web/Research thoroughly) and
action permissions remain separate from the preset.

## Measurements on this machine, 2026-09-13

Hardware verified: i9-12900HX, 68,430,585,856 bytes physical RAM, RTX 3080 Ti Laptop
GPU with 16,384 MiB VRAM. The bounded suite in
`scripts/preset_benchmark.py` used temperature 0, context 4,096, output ceiling
1,200, two serial passes, six text cases per model and one image case for vision.
Raw responses, exact installed sizes/quantization/digests, first-content timing,
load time, resident-model state and post-request RAM/VRAM are retained in
[the evidence JSON](evidence/preset-benchmark-2026-09-13.json).

| Model | Strict checks | Warm median first content | Warm median total | Observed resident VRAM |
| --- | --- | --- | --- | --- |
| qwen3:8b | 6/12 | 29 ms | 257 ms | 5.20 GiB |
| gpt-oss:20b | 10/12 | 474 ms | 482 ms | 11.86 GiB |
| qwen3-coder:30b | 8/12 | 33 ms | 241 ms | 13.83 GiB |
| devstral:24b | 6/12 | 85 ms | 1,230 ms | 13.83 GiB |
| qwen3-vl:8b | 2/2 image checks | 715 ms | 734 ms | 5.40 GiB |

First-pass total for the initial quick request was approximately 6.5/14.7/18.1/13.6
seconds respectively; vision's first image took 10.0 seconds. These include actual
load/switch overhead. Subsequent prompts in that pass were already warm. Samples
are not peak utilization or a broad quality ranking; exact timing varies with
system load. First-content timing excludes hidden reasoning and tool-only output.

FAST passed the quick/code/C# accuracy floor and produced the correct document
calculation and longer numeric values, but failed strict formatting and supplied
the wrong structured tool argument (`window` instead of `application`). It is not
selected as a reliable direct tool caller. NORMAL had the strongest strict score,
including source-label formatting and tool proposals, but omitted the last number
in the longer response. MAX passed structured tools where the smaller Qwen did
not, and the actual calculator generation/build/run acceptance supplies additional
local coding evidence. It added an extra number in the longer case; its document
answer was substantively correct but differently formatted. This supports a
provisional strongest *tested coding* Qwen choice, not universal superiority.
Devstral omitted document labels and declined the supplied tool. All these failures
remain in the evidence. Generated benchmark code/tools were not executed.

Official installed-model descriptions were checked at
[Qwen3](https://ollama.com/library/qwen3:8b),
[Qwen3-Coder](https://ollama.com/library/qwen3-coder:30b), and
[gpt-oss](https://ollama.com/library/gpt-oss:20b). Local digests are authoritative;
public tags can change. After the inventory and Diego's explicit 2026-09-14
approval, only llava:34b and dolphin-mixtral:8x7b were removed through Ollama.
The four active preset models, qwen3-embedding:0.6b and devstral:24b remain with
unchanged digests. Old chat records are preserved; selecting a removed tag needs
setup. See [verified storage measurements](STORAGE_REVIEW.md). The separately
approved SDXL checkpoint is a media-engine model, not an Ollama display alias.
