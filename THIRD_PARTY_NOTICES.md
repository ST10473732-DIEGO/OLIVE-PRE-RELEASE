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

Runtime dependencies declared in `pyproject.toml` (licences **not yet aggregated**;
see below): `cryptography`, `pyOpenSSL`, `httpx`, `ollama`, `zeroconf`, `psutil`, `pycrdt`, `Pillow`, `Send2Trash`, `beautifulsoup4`, `ddgs`, `pdfplumber`, `pypdf`, `python-docx`, `icalendar`, `python-dateutil`, `tzdata`, `vobject`, `SecretStorage` (Linux), `pywinauto` (Windows), `comtypes` (Windows), `pywin32` (Windows), `winrt-Windows.Media.Control` (Windows), `winrt-Windows.Media` (Windows), `winrt-Windows.Foundation` (Windows), `winrt-Windows.Foundation.Collections` (Windows). Optional extras `browser`, `qt` and `studio` are not part of the
packaged backend.

## Studio developer tooling (downloaded on request, not bundled)

| Component | Licence | Evidence |
| --- | --- | --- |
| OmniSharp-Roslyn 1.39.15 | MIT (.NET Foundation and Contributors) | `scripts/provision_studio_tooling.py` (SHA-256 pinned) |
| netcoredbg 3.2.0-1092 | MIT (Samsung) | `scripts/provision_studio_tooling.py` (SHA-256 pinned) |

## OLIVE assets with their own notice

| Files | Notice |
| --- | --- |
| `assets/icons/` ("DMDO line icons", original artwork) | MIT-style permission notice, Copyright (c) 2026 DMDO contributors (`assets/icons/LICENSE.txt`) |

## Separate runtimes and models (not part of OLIVE)

OLIVE talks to these over local interfaces; they are installed separately and keep
their own licences. Their licences are **not recorded in this repository**, so none
is asserted here.

| Item | Source recorded in the repository | Status |
| --- | --- | --- |
| Ollama | none | User-installed runtime |
| ComfyUI 0.35.0 (Windows portable archive) | GitHub release URL, size and SHA-256 in `scripts/install_approved_media.py` | Licence to be recorded before any installer downloads it |
| SDXL base 1.0 checkpoint | Hugging Face URL, size and SHA-256 in `scripts/install_approved_media.py` | Licence to be recorded and accepted per its terms before distribution |
| Ollama models for FAST, NORMAL, NOW, DEEP, roles | Registry tags in `olive/services/presets.py`, `model_policy.py`; MAX pinned by digest | Licence per model to be recorded in the runtime manifest |
| UNCENSORED `olive-*` local models | none (built locally) | **Not yet distributable** |
| FLUX.2 Klein 9B, LTX 2.3 video, Gemma-derived text encoder, Qwen-Image 2.1 | file names only (`olive/services/media_workflows.py`) | **Not yet distributable**: source, checksum and licence unresolved (Qwen-Image 2.1's recorded licence is research/evaluation only) |
| VoiceStudio and its engines | none | **Not yet distributable**: redistribution terms unresolved |

## Remaining release work

- Aggregate licence texts for every Python package in the packaged backend
  (generate from the built artifact's installed metadata, not by hand).
- Include Electron/Chromium/Node notices from the packaged Electron distribution.
- Ship each npm package's licence text with the renderer bundle.
- Record source, checksum and licence for every model and runtime in the 1.0
  runtime manifest; nothing without them enters an installer profile.
- Show the iPhone notices (OpenSSL, yjs, lib0) inside the app before App Store release.
