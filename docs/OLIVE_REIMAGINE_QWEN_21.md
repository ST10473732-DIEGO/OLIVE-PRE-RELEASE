# REIMAGINE: Qwen Image 2.1 evaluation gate

2026-09-23. **BLOCKED, not integrated or promoted.** Existing SDXL and raster
editing remain unchanged. No image weights have been downloaded, no licence
has been accepted on the user's behalf, and no restricted weights are bundled.
The user selected preparation for research/evaluation and will review the licence.

The [current upstream licence](https://github.com/QwenLM/Qwen-Image-2.1/blob/main/LICENSE)
(release 2026-09-20) defines non-commercial use as research/evaluation only.
Personal/local/free-product use is not a general permission. Commercial use
requires a separate agreement. This milestone's text/JDK acquisition approval
explicitly excludes image weights.

The [official repository](https://github.com/QwenLM/Qwen-Image-2.1) and
[Comfy-Org package](https://huggingface.co/Comfy-Org/Qwen-Image-2.1) were checked.
Candidate revision `9a44dbdb47cefd046be9c0a13476192f34c8db8e` requires:

| Component | Bytes | Precision |
| --- | ---: | --- |
| qwen_image_2.1_int8_convrot.safetensors | 7,256,783,064 | INT8 ConvRot diffusion |
| qwen3vl_8b_int8_convrot.safetensors | 9,350,798,360 | INT8 ConvRot encoder |
| qwen_image_2.1_vae_bf16.safetensors | 675,509,688 | BF16 VAE |

Total 17,283,091,112 bytes, excluding staging and runtime changes. All file
SHA-256 values are in the acquisition manifest. Optional prompt enhancer
weights (two further ~9.47 GB models) are unnecessary and excluded. Download
size is not simultaneous VRAM use. RTX 3080 Ti is compute capability 8.6;
INT8 ConvRot kernel support and sequential offload have not been measured.

## Verified native workflow gap

The upstream [generation graph](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_qwen_image_2_1_t2i.json)
uses `UNETLoader`, `CLIPLoader`, `VAELoader`, `TextEncodeQwenImage21`,
`EmptyLatentImage`, `KSampler`, and `VAEDecode`, with frontend workflow helpers.
The [edit graph](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_qwen_image_2_1_image_edit.json)
also uses `QwenImage21Cache` and `ComfySwitchNode`. These are not SDXL graphs.

Installed ComfyUI is 0.35.0 at
`40c4fcdf513a4523e39d54a9d391908af8df8171`; its native Qwen module lacks
`TextEncodeQwenImage21` and `QwenImage21Cache`. Its dedicated PyTorch environment
is 2.14.0+cu130, runtime CUDA 13.0; CUDA availability and GPU capability 8.6
were verified on host. Driver-advertised CUDA 13.4 is a different measurement.
A recoverable, pinned compatible ComfyUI environment is required before activation.
No bulk upgrade of OLIVE's venv or SDXL-weight substitution was performed.

The current media bridge accepts a checkpoint in a fixed SDXL graph and offers
no engine/component selection. A Qwen adapter must resolve real component
identity centrally and expose truthful existing state, without disguising
Qwen as an SDXL checkpoint or relabelling the UI. That integration is not claimed.

## Acceptance prepared, not passed

Fixed image cases: natural still life (three olives), illustration, an
OLIVE-labelled mock poster (never an application asset), left/right spatial
counts, exact text, reference-preserving edit, transparent cutout with actual
alpha extrema inspected. Start at 1024 pixels, fixed seed/steps/workflow;
record cold/warm time, sampled and allocator peak memory, provenance, readable
format/dimensions and human assessment. Preserve source images. Exercise edit →
cancel → generate → Chat and verify identity-bound cleanup. No Qwen output,
transparency result, latency or image-quality improvement is claimed here.

[FLUX.2-klein-4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) is
an Apache-2.0 generation/edit alternative; [Z-Image-Turbo](https://huggingface.co/Tongyi-MAI/Z-Image-Turbo)
is a generation-speed challenger. Neither was downloaded or substituted.

## Existing SDXL functional acceptance

The existing engine completed generation, reference edit, cancel, a fresh
post-cancel generation, Chat handoffs and owned shutdown through the real
REIMAGINE controls. All three output PNGs were readable 1024×1024 RGB; original
bytes remained unchanged and the cancelled job produced no artifact. Seed 0,
20 Euler/normal steps, CFG 7, denoise 1 for generation / 0.65 for editing.

Single measured UI jobs: generation 14.286 s, edit 12.182 s, restart generation
12.428 s; cancellation 1.326 s. These are n=1 operation timings after engine
setup, not repeated cold/warm performance claims. Peak sampled torch reservation
was about 9.96 GiB, with about 20 MiB remaining after release/Chat handoff.
Torch reservation is not total GPU usage. The original SDXL checkpoint hash,
stored F16 tensor metadata and sampled RAM/VRAM are in
[the live result manifest](evidence/backend-v3-live.json). Execution precision
was ComfyUI's automatic choice, not independently kernel-instrumented.

Visual inspection found **four olives instead of three**, and the edit did
not reliably make the olives purple or plate blue. Those quality constraints
failed despite functional pipeline success. There is no alpha channel in these
outputs, and no transparency claim. This preserves a working engine; it is not
an image-quality upgrade or a Qwen/FLUX comparison.
