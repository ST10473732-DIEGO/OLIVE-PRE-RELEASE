# Browser, Connections and local media acceptance

These changes preserve the existing OLIVE shell. They do not enable hosted AI,
account sign-in, downloads of models, or external message submission.

## Browser — OLIVE GO

Open OLIVE GO in navigation. Its chrome is the design in
`docs/design/olive-go-artifact.html` (one-band tab strip and toolbar, a single
address field, a new tab page with the olive mark, right-hand panels), built in
`desktop/src/features/go/`. Electron 44's WebContentsView still hosts actual
pages in tabs; address text becomes an encoded query for the chosen engine
(Google by default; DuckDuckGo and Bing from a fixed map). HTTP(S) URLs are
validated. Back/forward, reload/stop, close/reopen, pin/reorder, history,
favourites, find, zoom, downloads, Clear browsing data and preferences use the
real browser service in `desktop/electron/main/browser.ts`; `docs/design/OLIVE_GO_PARITY.md`
maps every old action to its new place. Suggestions are local unless the
person turns engine suggestions on, and never leave a private tab.

Normal tabs and history/bookmarks survive restart. Provider cookies retain their
own expiry rules. Private tabs share a separate memory session, are excluded from
normal history/bookmarks and are cleared when the last private tab closes. This
does not hide traffic from websites or network operators.

Remote views have no Node or OLIVE preload, and retain sandbox, context isolation,
web security and certificate checks. Site permissions are currently denied with
an inspectable explanation, including camera/microphone and clipboard reads.
Native file selection is user initiated. Unsupported authentication and external
protocols need the system browser. Downloads require native destination selection,
show source/progress/cancellation, and never execute automatically. Download lists
are session-local. Privileged app dialogs hide native views, including immediately
when a backend approval arrives.

Summarize in Chat extracts bounded visible page text using fixed service code,
omitting form fields and editable content. It checks the page identity again and
marks extracted material as untrusted source data. No model-provided JavaScript
is accepted. Page content does not confer action authority.

`browser.spec.ts` drives OLIVE GO's chrome, uses actual loopback HTTP navigation and file bytes, verifies
the remote page lacks Node/OLIVE APIs, normal/private cookie separation, history,
find/zoom, a download destination approved only for the exact fixture URL/name,
restart and native-view hiding during a real modal. Native OS window captures
are required: Electron capturePage alone omits WebContentsView content.
`browser-public.spec.ts` reached Google's real anti-bot page. Navigation is live
external evidence; search results were not verified and CAPTCHA was not bypassed.

## Connections

Discord remains a bot integration. Vault configuration verifies bot identity;
destination discovery filters accessible text channels using guild roles and
channel overwrites. Selected destination revisions bind subsequent review. Sending
requires the exact preview/approval and reports the returned bot message identity.
Uncertain submission cannot be blindly retried. Rate-limit responses report the
wait instead of silently resubmitting. These paths have synthetic transport and
permission tests; no personal Discord account or real bot send was exercised.

An explicit personal-account sender request prepares text for manual sending and
does not substitute the bot. User-token automation is excluded in accordance with
[Discord's published policy](https://support.discord.com/hc/en-us/articles/115002192352-Automated-User-Accounts-Self-Bots).
Channel filtering follows the [official permissions model](https://docs.discord.com/developers/topics/permissions).

## REIMAGINE

Choose OLIVE REIMAGINE in Chat, then Open media tools. Actual local Pillow crop
and resize preserve an imported original, create separate output artifacts and
record hashes/settings/provenance. Preview and export use those real files.
Cancellation before completion creates no output. Python tests inspect pixels,
dimensions, original bytes and exclusive export; `media.spec.ts` exercises the
real import/resize/preview UI and verifies its saved output using Pillow.

Image generation and image-to-image now have **real local UI acceptance** using
the explicitly approved ComfyUI v0.35.0 and SDXL base 1.0 installation. The test
creates separate 1024×1024 PNGs, verifies provenance/dimensions/nonblank pixels,
preserves original bytes, cancels a running prompt, and returns to actual Ollama
Chat. Outputs and screenshots are in `artifacts/core/functionality/media-live/`.
Visual inspection found imperfect prompt fidelity: four olives instead of three,
and only partial requested color changes. An actual artifact is not a guarantee
of exact counting, layout or edit fidelity. The adapter accepts only a dedicated loopback
endpoint, built-in workflow nodes and installed checkpoint selections. It does
not accept uploaded arbitrary workflows or custom node code. A configured engine
is executable software that must itself be trusted; node metadata is not a sandbox.

Ollama and media share the residency lock. OLIVE unloads its managed model, refuses
to evict unrelated resident models, scopes cancellation to its prompt identity,
and checks engine idleness and native CUDA allocator release before subsequent Chat inference.
The runtime disables asynchronous/dynamic allocators so model memory is measured;
an empty `/free` acknowledgement alone is not release evidence. Cancellation uses
the version-0.35.0 prompt-specific interrupt and waits for the prompt to stop. If engine
state cannot be verified, Chat fails with a relevant retry message. Other clients
must not use this dedicated engine concurrently.

Video crop/trim/resize currently report Needs setup: FFmpeg is not integrated.
Generative video reports Unsupported: no configured model/workflow. Neither has
produced a verified video artifact. A chat/vision model is never labelled an image
generator. No paid fallback is present.

## Approved and installed download manifest, 2026-09-14

Diego approved the exact runtime/checkpoint below. Both downloads passed their
pinned byte counts and SHA-256 checks. The verified GPU has 16 GiB VRAM and driver
616.56. The separate portable runtime uses embedded Python 3.13.14 and Torch
2.13.0+cu130, preserving OLIVE's Python environment. The installed workflow
uses SDXL base, Euler sampling and the adapter's bounded image dimensions; no
refiner, custom node, video model or extra checkpoint was installed.

| Item | Destination relative to repository | Download bytes | SHA-256 |
| --- | --- | ---: | --- |
| ComfyUI v0.35.0 NVIDIA portable | `.media-runtime/downloads/ComfyUI_windows_portable_nvidia.7z` | 1,910,039,517 | `6fb005a8269c6f5972a8fb76d7a4fc251578ccc7906671a801b382591c791dd2` |
| SDXL base 1.0 | `.media-runtime/ComfyUI_windows_portable/ComfyUI/models/checkpoints/sd_xl_base_1.0.safetensors` | 6,938,078,334 | `31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b` |

Total transfer: **8,848,117,851 bytes (8.85 GB)**. Allow about 25 GB free for the
archive, unpacked runtime, checkpoint and initial outputs; unpacked size is an
initial planning estimate. Measured installation/resource/acceptance results are
recorded in FUNCTIONAL_RELIABILITY.md. No system Python or driver changed. The
launch binds only 127.0.0.1 and disables custom nodes and hosted API nodes.

Sources checked on 2026-09-13: [official portable installation](https://docs.comfy.org/installation/comfyui_portable_windows),
[pinned release](https://github.com/Comfy-Org/ComfyUI/releases/tag/v0.35.0),
[SDXL checkpoint listing](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/tree/main).
Release/API metadata supplied byte counts and hashes. The checkpoint model card
and CreativeML OpenRAIL++-M license were read and retained under `.media-runtime/`,
with a license copy beside the checkpoint. The portable GPLv3 notices remain.
The full model repository was not downloaded.

From the repository root, run `powershell -File scripts/media_engine.ps1 -Action Start`.
This starts a hidden, task-owned process; it refuses to reuse an unrelated listener.
In Chat choose OLIVE REIMAGINE → Open media tools → Local generation setup →
Check dedicated local engine, then select `sd_xl_base_1.0.safetensors`. Configuration
is per data profile; acceptance used an isolated synthetic profile, not personal data.
Choose Generate image or Generative image edit and create the artifact. No automatic
startup, personal-profile change, firewall rule or remote listener was installed.

Before stopping the engine, use **Release and disconnect engine** in Media tools;
then run `powershell -File scripts/media_engine.ps1 -Action Stop`. Disconnect only
clears configuration after verified GPU release and preserves artifacts. If a
configured engine is offline, restart it to reconnect/disconnect safely; Chat
does not guess that its GPU resources are free. The stop script refuses active jobs.
