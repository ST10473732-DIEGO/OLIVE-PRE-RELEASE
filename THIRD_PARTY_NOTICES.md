# Third-party notices

OLIVE is proprietary software ([LICENSE](LICENSE)). It uses third-party components
that remain under their own licences; the OLIVE licence does not change those terms.

This file lists only what the tracked repository proves: licence fields in
`desktop/package-lock.json`, licence texts committed next to components, and
licences recorded in provisioning scripts. **It is not yet the complete notice set
for a distributed build.** See [Remaining release work](#remaining-release-work).

## Desktop application (npm, from `desktop/package-lock.json`)

Runtime (non-development) packages resolved by the lockfile, with the licence each
package declares. Full licence texts are in each package's `node_modules` folder
and must be shipped with a build.

- **MIT** (142): `@radix-ui/primitive` 1.1.7, `@radix-ui/react-compose-refs` 1.1.5, `@radix-ui/react-context` 1.2.2, `@radix-ui/react-dialog` 1.1.23, `@radix-ui/react-dismissable-layer` 1.1.19, `@radix-ui/react-focus-guards` 1.1.6, `@radix-ui/react-focus-scope` 1.1.16, `@radix-ui/react-id` 1.1.4, `@radix-ui/react-portal` 1.1.17, `@radix-ui/react-presence` 1.1.10, `@radix-ui/react-primitive` 2.1.10, `@radix-ui/react-slot` 1.3.3, `@radix-ui/react-use-callback-ref` 1.1.4, `@radix-ui/react-use-controllable-state` 1.2.6, `@radix-ui/react-use-effect-event` 0.0.5, `@radix-ui/react-use-layout-effect` 1.1.4, `@types/debug` 4.1.13, `@types/estree` 1.0.9, `@types/estree-jsx` 1.0.5, `@types/hast` 3.0.5, `@types/mdast` 4.0.4, `@types/ms` 2.1.0, `@types/react` 19.3.0, `@types/react-dom` 19.3.0, `@types/trusted-types` 2.0.7, `@types/unist` 3.0.3, `@types/unist` 2.0.11 (nested), `@xterm/addon-fit` 0.11.0, `@xterm/xterm` 6.0.0, `aria-hidden` 1.2.6, `bail` 2.0.2, `ccount` 2.0.1, `character-entities` 2.0.2, `character-entities-html4` 2.1.0, `character-entities-legacy` 3.0.0, `character-reference-invalid` 2.0.1, `comma-separated-tokens` 2.0.3, `csstype` 3.2.3, `debug` 4.4.3, `decode-named-character-reference` 1.3.0, `dequal` 2.0.3, `detect-node-es` 1.1.0, `devlop` 1.1.0, `escape-string-regexp` 5.0.0 (nested), `estree-util-is-identifier-name` 3.0.0, `extend` 3.0.2, `framer-motion` 13.2.0, `get-nonce` 1.0.1, `hast-util-to-jsx-runtime` 2.3.6, `hast-util-whitespace` 3.0.0, `html-url-attributes` 3.0.1, `inline-style-parser` 0.2.7, `is-alphabetical` 2.0.1, `is-alphanumerical` 2.0.1, `is-decimal` 2.0.1, `is-hexadecimal` 2.0.1, `is-plain-obj` 4.1.0, `isomorphic.js` 0.2.5, `lib0` 0.2.119, `longest-streak` 3.1.0, `markdown-table` 3.0.4, `marked` 14.0.0, `mdast-util-find-and-replace` 3.0.2, `mdast-util-from-markdown` 2.0.3, `mdast-util-gfm` 3.1.0, `mdast-util-gfm-autolink-literal` 2.0.1, `mdast-util-gfm-footnote` 2.1.0, `mdast-util-gfm-strikethrough` 2.0.0, `mdast-util-gfm-table` 2.0.0, `mdast-util-gfm-task-list-item` 2.0.0, `mdast-util-mdx-expression` 2.0.1, `mdast-util-mdx-jsx` 3.2.0, `mdast-util-mdxjs-esm` 2.0.1, `mdast-util-phrasing` 4.1.0, `mdast-util-to-hast` 13.2.1, `mdast-util-to-markdown` 2.1.2, `mdast-util-to-string` 4.0.0, `micromark` 4.0.2, `micromark-core-commonmark` 2.0.3, `micromark-extension-gfm` 3.0.0, `micromark-extension-gfm-autolink-literal` 2.1.0, `micromark-extension-gfm-footnote` 2.1.0, `micromark-extension-gfm-strikethrough` 2.1.0, `micromark-extension-gfm-table` 2.1.1, `micromark-extension-gfm-tagfilter` 2.0.0, `micromark-extension-gfm-task-list-item` 2.1.0, `micromark-factory-destination` 2.0.1, `micromark-factory-label` 2.0.1, `micromark-factory-space` 2.0.1, `micromark-factory-title` 2.0.1, `micromark-factory-whitespace` 2.0.1, `micromark-util-character` 2.1.1, `micromark-util-chunked` 2.0.1, `micromark-util-classify-character` 2.0.1, `micromark-util-combine-extensions` 2.0.1, `micromark-util-decode-numeric-character-reference` 2.0.2, `micromark-util-decode-string` 2.0.1, `micromark-util-encode` 2.0.1, `micromark-util-html-tag-name` 2.0.1, `micromark-util-normalize-identifier` 2.0.1, `micromark-util-resolve-all` 2.0.1, `micromark-util-sanitize-uri` 2.0.1, `micromark-util-subtokenize` 2.1.0, `micromark-util-symbol` 2.0.1, `micromark-util-types` 2.0.2, `monaco-editor` 0.56.0, `motion` 13.2.0, `motion-dom` 13.2.0, `motion-utils` 13.0.0, `ms` 2.1.3, `parse-entities` 4.0.2, `property-information` 7.2.0, `react` 19.3.0, `react-dom` 19.3.0, `react-markdown` 10.1.0, `react-remove-scroll` 2.7.2, `react-remove-scroll-bar` 2.3.8, `react-style-singleton` 2.2.3, `remark-gfm` 4.0.1, `remark-parse` 11.0.0, `remark-rehype` 11.1.2, `remark-stringify` 11.0.0, `scheduler` 0.28.0, `space-separated-tokens` 2.0.2, `stringify-entities` 4.0.4, `style-to-js` 1.1.21, `style-to-object` 1.0.14, `trim-lines` 3.0.1, `trough` 2.2.0, `unified` 11.0.5, `unist-util-is` 6.0.1, `unist-util-position` 5.0.0, `unist-util-stringify-position` 4.0.0, `unist-util-visit` 5.1.0, `unist-util-visit-parents` 6.0.2, `use-callback-ref` 1.3.3, `use-sidecar` 1.1.3, `vfile` 6.0.3, `vfile-message` 4.0.3, `yjs` 13.6.33, `zod` 4.6.1, `zwitch` 2.0.4
- **OFL-1.1** (3): `@fontsource-variable/bricolage-grotesque` 5.3.0, `@fontsource-variable/jetbrains-mono` 5.3.0, `@fontsource-variable/onest` 5.3.1
- **ISC** (3): `@ungap/structured-clone` 1.4.0, `lucide-react` 1.44.0, `qrcode.react` 4.2.0
- **(MPL-2.0 OR Apache-2.0)** (1): `dompurify` 3.4.15
- **0BSD** (1): `tslib` 2.8.1

The three `@fontsource-variable` packages bundle the Onest, Bricolage Grotesque and
JetBrains Mono fonts (SIL Open Font License 1.1). `dompurify` is dual-licensed
(MPL-2.0 OR Apache-2.0).

**Electron** 44.3.0 (MIT) is a build dependency that becomes the application
runtime when packaged. Its Chromium and Node.js notices (`LICENSES.chromium.html`)
come from the packaged Electron distribution and are not in this repository.

## iPhone app

| Component | Licence | Evidence |
| --- | --- | --- |
| OpenSSL 3.5.8, built statically by `mobile/ios/scripts/build-connect-tls.sh` (source SHA-256 pinned) | Apache-2.0 | `mobile/ios/NativeConnect/OpenSSL-LICENSE.txt` |
| yjs 13.6.33 and lib0 0.2.119, bundled unmodified in `NotesEngine.js` | MIT | `mobile/ios/OLIVEMobile/Resources/NotesEngine.LICENSES.txt` |

## Python backend

| Component | Licence | Evidence |
| --- | --- | --- |
| GUI-Owl tool-calling prompt text (`olive/desktop/gui_owl_prompt.txt`) | MIT, Copyright (c) 2022 mPLUG | `olive/desktop/gui_owl_prompt.LICENSE` |
| pycrdt 0.14.6 | MIT (as recorded in `desktop/THIRD_PARTY.md`) | to be confirmed from the built backend's metadata |

Runtime dependencies declared in `pyproject.toml` (licence texts aggregated per build into
`THIRD_PARTY-backend.txt`; see [Packaged notices](#packaged-notices)): `cryptography`, `pyOpenSSL`, `httpx`, `ollama`, `zeroconf`, `psutil`, `pycrdt`, `Pillow`, `Send2Trash`, `beautifulsoup4`, `ddgs`, `pdfplumber`, `pypdf`, `python-docx`, `icalendar`, `python-dateutil`, `tzdata`, `vobject`, `SecretStorage` (Linux), `keyring` (macOS), `pywinauto` (Windows), `comtypes` (Windows), `pywin32` (Windows), `pywinpty` (Windows, MIT), `winrt-Windows.Media.Control` (Windows), `winrt-Windows.Media` (Windows), `winrt-Windows.Foundation` (Windows), `winrt-Windows.Foundation.Collections` (Windows). Optional extras `browser`, `qt` and `studio` are not part of the
packaged backend.

The packaged backend (`resources/backend`, built by `packaging/backend/build_backend.py`)
also contains:

- **CPython 3.14.8** from python-build-standalone release `20261001`. Its licence is
  PSF-2.0, plus the notices of the libraries it bundles; these ship inside the
  interpreter distribution. Source and checksums are in `packaging/backend/python-runtime.json`.
- The **transitive** distributions pinned in `packaging/backend/locks/<target>.txt`. The
  exact set installed in a given build is listed in that build's `olive-backend.json`.

## Studio developer tooling (downloaded on request, not bundled)

| Component | Licence | Evidence |
| --- | --- | --- |
| OmniSharp-Roslyn 1.39.15 | MIT (.NET Foundation and Contributors) | `scripts/provision_studio_tooling.py` (SHA-256 pinned) |
| netcoredbg 3.2.0-1092 | MIT (Samsung) | `scripts/provision_studio_tooling.py` (SHA-256 pinned) |

## OLIVE assets with their own notice

| Files | Notice |
| --- | --- |
| `assets/icons/` ("DMDO line icons", original artwork) | MIT-style permission notice, Copyright (c) 2026 DMDO contributors (`assets/icons/LICENSE.txt`) |

## Downloaded at first run (not bundled)

First-run setup downloads these from their publishers, only when the person chooses them. They
are not part of the OLIVE package and keep their own licences. Source, integrity and licence
evidence for each is in `olive/runtime_manifest/1.0.0.json`; licence identification there is
engineering evidence, not legal advice. **Setup offers an entry only after the owner approves it
for the public release** (`olive/runtime_manifest/release-approvals-1.0.0.json`).

| Component | Licence | Source | Notes |
| --- | --- | --- | --- |
| Ollama 0.34.2 (Linux, Windows) | MIT | GitHub release `ollama/ollama` v0.34.2, SHA-256 pinned | The archives carry third-party licence files under `lib/ollama`, including NVIDIA CUDA runtime libraries under NVIDIA's terms |
| qwen3:8b, qwen3.5:9b, qwen3-vl:8b, qwen3-coder:30b | Apache-2.0 | Ollama library, registry manifest digest pinned | Licence layer in each model is the Apache-2.0 text |
| gpt-oss:20b | Apache-2.0 | Ollama library, digest pinned | OpenAI's gpt-oss usage policy also applies |
| qwen3-embedding:0.6b | Apache-2.0 | Ollama library, digest pinned | The registry manifest has no licence layer; this notice supplies it |
| Playwright 1.63.0 + greenlet 3.5.6 + pyee 13.0.1 (optional) | Apache-2.0; MIT AND PSF-2.0; MIT | PyPI wheels, SHA-256 pinned | Playwright's wheel bundles a Node.js driver (MIT, with Node's own notices) |
| FLUX.2 [klein] 4B fp8, Qwen3 4B text encoder, FLUX.2 VAE (REIMAGINE) | Apache-2.0 | Hugging Face `black-forest-labs/FLUX.2-klein-4b-fp8` and the Comfy-Org repackaging `vae-text-encorder-for-flux-klein-4b`, revision and SHA-256 pinned | Owner-approved for 1.0; useful once an image engine is installed or chosen. BFL encourages deployers to use input/output filters |

## Separate runtimes and models (not installable from setup)

| Item | Licence evidence | Status |
| --- | --- | --- |
| OLIVE Creator image runtime (ComfyUI v0.35.0 + CPython 3.14.8 + hash-locked PyTorch 2.14.0 wheels) | Archive (83 wheels): GPL-3.0-only (ComfyUI), PSF-2.0, BSD-3-Clause (PyTorch) and the other archive wheels' licences, listed in the archive's `THIRD_PARTY-creator.txt`. **Not** in the archive: 20 wheels setup downloads from PyPI (`THIRD_PARTY-creator-direct-downloads.txt`, with each wheel's own licence and NOTICE texts and METADATA attribution): NVIDIA's CUDA/cuDNN/NCCL wheels under NVIDIA's terms, and triton (MIT), torchvision (BSD), comfy-kitchen (Apache-2.0) and cuda-bindings (Apache-2.0), each with the NVIDIA components it bundles | Built and validated on Linux (archive SHA-256 `ecdb6702…cff0d81`, reproducible from its runtime inputs alone), not published, not owner-approved. The archive audit finds no bundled NVIDIA runtime, tools or proprietary licence text; NVIDIA copyright lines remain only in open-source code (ComfyUI, torch's CUTLASS/cudnn-frontend notices, transformers, torchaudio, cuda-pathfinder). The GPL source offer for ComfyUI is the pinned public commit. The video runtime is defined and split the same way but not built |
| ComfyUI-GGUF-Loader (video engine) | Apache-2.0 and MIT | Inside the video runtime archive (commit pinned) |
| SDXL base 1.0 checkpoint | CreativeML Open RAIL++-M (use restrictions, acceptance) | Engineering-reviewed; owner decision and an acceptance step needed |
| FLUX.2 [klein] 9B | FLUX Non-Commercial License, gated | **Not distributable**; an existing user-supplied copy keeps working |
| LTX-2.3 official fp8 set (checkpoint, distilled LoRA 1.1, Gemma 3 12B fp4 encoder, x2 upscaler) | LTX-2 Community License (paid licence for entities with ≥ USD 10 M revenue; Attachment A use restrictions); Gemma Terms of Use | Pins recorded; no validated OLIVE workflow yet; acceptance step and owner decision needed |
| LTX 2.3 community finetunes, abliterated Gemma encoder | LTX-2 Community License; Gemma terms; uploader declares none | **Not distributable**; an existing copy keeps working |
| Qwen-Image 2.1 | research/evaluation only | **Not distributable** |
| VoiceStudio | AGPL-3.0 | Installed and run by the person (v0.5.6 release or source); OLIVE does not redistribute it |
| OmniVoice | CC-BY-NC (model card text) and the Boson Higgs Audio 2 Community License (audio tokenizer) | **Not distributable** (non-commercial) |
| MAX (`orcarouter/Qwen3.8-27B-Uncensored`), UNCENSORED routing set, `olive-*` local tags | provenance not recovered | **Not distributable** |
| FFmpeg | depends on the build (LGPL or GPL) | Used from the operating system |

## Packaged notices

Each packaged backend carries `THIRD_PARTY-backend.txt` (also copied to `resources/legal/`):
the declared licence and the licence files of every bundled Python distribution, CPython's
`LICENSE.txt`, and upstream licence texts for wheels that ship none (`packaging/legal/supplements/`).
It is generated by `packaging/legal/collect_notices.py` during `build_backend.py`. It flags for
owner/legal review: `zeroconf` (LGPL-2.1-or-later), `certifi` (MPL-2.0), `pypdfium2` and the PDFium
binary it bundles, `cryptography` (statically linked OpenSSL) and CPython's bundled libraries.

Every packaged desktop build also carries, in `resources/legal/`:

- `THIRD_PARTY-npm.txt`: every runtime npm package's declared licence and the licence files it
  ships, including the SIL OFL 1.1 texts of the three bundled fonts (generated by
  `desktop/scripts/npm-notices.cjs` during `npm run build`; packaging refuses to run without it);
- `LICENSE.electron.txt` and `LICENSES.chromium.html` from the Electron distribution (Electron,
  Chromium, Node.js and their bundled libraries);
- the backend notices above, which now also include the licence texts of the libraries compiled
  into the python-build-standalone interpreter (OpenSSL, SQLite, libffi, zlib/zlib-ng, xz, bzip2,
  mpdecimal, expat, ncurses/libedit, Tcl/Tk, libX11/libxcb, zstd, libuuid, Berkeley DB), recorded
  from the pinned release's full archives by `packaging/legal/pbs_notices.py`.

The Connect World relay bundle (`packaging/relay/`) carries its own `THIRD_PARTY_NOTICES.md` and
a **draft** relay licence.

## Remaining release work

- Owner/legal review of every flagged item above, of the model licences, and of the release
  approvals themselves (the approvals file is empty).
- A relay image published by OLIVE would redistribute the Debian base image and CPython:
  generate its notice file from the image's package list at that point.
- `react-remove-scroll-bar` declares MIT but ships no licence file; `THIRD_PARTY-npm.txt` lists
  it as declared-only.
- Show the iPhone notices (OpenSSL, yjs, lib0) inside the app before App Store release.
