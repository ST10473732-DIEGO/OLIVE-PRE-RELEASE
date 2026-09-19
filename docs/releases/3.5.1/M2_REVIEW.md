# DMDO 3.5.1 — M2 review candidate

M1 `d355f94` remains the approved design baseline. The existing-feature Electron migration is submitted for **M2 user review**, not release approval. Implementation checkpoint: `b3554c3`, branch `development/3.5.1-electron-experience`. Stop here before new Personal Core interfaces. No tag, default-launcher switch, Qt removal or installer publication.

## Feature and action parity

The [action ledger](M2_PARITY.md) names all 125 original callable actions, their old/new locations, policy boundaries, evidence and limitations. The requirements matrix retains all 1,612 rows. Backend implementation, live local tests, controlled fixtures and untested provider variants are not interchangeable acceptance claims.

| Workspace | Connected functionality | Evidence / limits |
| --- | --- | --- |
| Settings / Diagnostics | Searchable categories, validated settings/model roles, scoped permissions, OCR, data tools, backup/restore/export, appearance, Developer Mode, diagnostics copy/export; explicit accessibility sizing and layout reset | Real settings persistence, invalid-value rejection, native workspace/OCR picker handling, diagnostics export and isolated backup/restore; 125% enlargement and keyboard panel sizing checked. Downloads/large model benchmarks and writing the real user clipboard not exercised. |
| Agent | Shared natural-language objective/context; task history/search/pages, actual timeline, validation/files, pause/resume/cancel and expandable tool records | Real offline result/history handoffs; real controller controls with labelled inert work. Fixture tasks do not demonstrate autonomous model execution. |
| Research | Shared question/depth routing; sources, findings/citations, history/search/pages, pause/resume/cancel, source/report saving, website scope/learning, downloads and saved web sources | Real repository/adapter connection, preparation cancellation and approval denial; evidence/download records are fixtures. External search/learning/download providers remain unit/mocked coverage, not live external acceptance. |
| Desktop Control | Natural objective, application/action/verification, Stop, permissions/takeover state; UIA/browser/application/media/clipboard/visual/consequence controls in Developer Details | Real disabled-provider checks and main-process Stop; inert active-work fixture confirms actual cancellation. No private account, real desktop input or vision-localisation reliability claim. |
| Projects | Search/create/open, workspace approval/trust and relationships to chats/files/tasks/research/knowledge/memory | Real local creation and stable-ID handoffs, including exact Research sessions and document-owning conversations. Record lists paginate. |
| Knowledge | Sources/search/filter/health, indexing jobs, re-index/relink/remove, retrieval inspection, website material, upgrade progress/cancellation | Real file import, lexical retrieval, re-index/relink/remove and offline upgrade; controlled embedding cancellation retains earlier batches. Original files are preserved. |
| Memory | Search/filter, CRUD, source context, editable suggestions with approve/reject and export | Real persistence/export and edited suggestion review using explicitly injected suggestions; no claim that the model generated those fixtures. |
| Chat | Growing composer, streaming/cancel/regenerate/branches, history/search, notes/title/project/summary, drafts/provenance, native attachments/drop and export/delete | Real local metadata/branch/attachment/export checks; disk-backed File drops accepted, constructed files rejected. No path getter/raw IPC. Model-dependent variants are separated from ordinary tests. |
| Studio | Monaco tabs/dirty buffers, explorer hierarchy, safe save/save-all/close/compare, search, diagnostics, Git, checkpoint/IDE tools, run/test/restart/Stop, owned command output and isolated local previews | Real temporary edits/tests, retained output, concurrent-edit protection, approved/cancelled Git operations, command cancellation/no-write and a real local web preview without a preload bridge. No PTY/LSP/debugger claim. |

Placement difference submitted for review: Problems/Tests/Git details live in **Workspace tools**, with Monaco markers and retained Output, rather than reproducing Qt's floating dock arrangement. The original capabilities remain accessible. CSS-native panel sizes persist, and Settings offers keyboard sizing/reset. This is not a claim that literal legacy docking has been reproduced.

## Architecture and security

One supervised Python service graph serves the active profile through the existing versioned private process protocol. All contextual inputs use the same NaturalLanguageOrchestrator/CapabilityRouter. Python remains authoritative for permissions, approvals, domain data, edits and execution. No Qt window or hidden GUI is needed by these Electron routes.

Electron keeps sandbox/context isolation/no Node integration and validates sender, method and payload. File dialogs own paths; native drops supply disk-backed files through the narrow preload. Interface sizing accepts only four explicit enlargement factors. Preview origins must be owned by a running RunSession, use an isolated session and have no application bridge. Untrusted content is not renderer code.

Git stdin is disconnected from the protocol pipe, fixing a Windows hang. Read-only Git gestures use existing exact direct-action consent without overriding explicit denial; writes still require approval. Cancellation leaves the fixture index unchanged. Save feedback stays separate from run/test output. Restore rejects concurrent work/dirty buffers/startup work and blocks new writes until restart. SQLite backup uses its consistent backup API. Credential sentinels are excluded from the tested portable backup.

Domain formats and data locations are retained; no broad storage migration was introduced. Native Identity/Contacts/Calendar/Tasks/Reminders/Mail and optional mail transport remain later mandatory scope. Personal Core palette entries are disabled, not represented as complete. Qt remains a separate tested fallback, never an independent writer beside Electron on the same profile.

## Fresh verification

| Class | Result |
| --- | --- |
| Python unit/isolated integration, including security, language and Qt tests | **597 passed**; `python -m unittest discover -s tests -v` |
| Python compilation | `python -m compileall -q .` passed |
| Frontend | **12 passed**; TypeScript, lint and production build passed |
| Ordinary Electron integration | **21 passed**, one opt-in live-model test skipped in this run |
| Separate opt-in live local Ollama | **1 passed** on the current build: qwen3:8b streaming, cancellation and route retention in an isolated profile; no download or external message |
| Qt legacy fallback smoke | **49 checks passed**, zero recorded errors; separate temporary profile, deterministic stream fixture |
| Qt experience checkpoint | **17 checks passed**; two existing `QQuickStyle::setStyle()` ordering warnings printed, not hidden |
| Diff review | No generated review artifacts, credentials or personal data staged; original release tags untouched |

The full Electron run covers real temporary file/project/data operations, cancellation, approvals, hash conflicts, retained editor/output/context, renderer reload, sandbox/bridge restrictions, local preview ownership and offline operation. Active Agent/Desktop work is explicitly test-controlled, with no model tool or actual desktop input. Ordinary tests do not install software, send messages or access private accounts.

## Visual evidence and measurements

Review artifacts are ignored under `artifacts/ui-review/M2/`. The ZIP contains actual Electron screenshots and the **22.04-second** `cross-feature/m2-cross-feature-navigation.mp4`, plus notes/measurements. It excludes Qt screenshots and fixture databases. The recording shows Welcome/Enter, Home/All Spaces, existing workspaces, real Studio editing/saving/testing and Home → Studio state retention. Additional captures show controlled active work, approval/denial, empty states, Git tools, real command cancellation and the isolated local preview.

Normal outer window: **1440×920**; content: **1424×881** at 100%. Small outer window: **1366×768**; content: **1350×729**. Home/Studio and all newly migrated routes were checked at the smaller size without changing Windows display settings. Core handoff additionally passed 640×480, rapid navigation and reduced-motion checks. Appearance/keyboard coverage is representative, not accessibility certification. Diagnostic settings below the fold remain reachable by normal scrolling.

Visual inspection covered the actual normal/small workspace captures, populated Studio/output, fixture task/approval states, palette/navigation consistency and explicit 125% enlargement. Research's empty capture has an empty new investigation while fixture history remains visible. Settings/Diagnostics show real configuration rather than invented empty data.

Observed warm developer-environment figures: Electron Welcome visible to automation **415 ms**; recorded navigation checks **52–865 ms**, including automation/transition overhead; summed Electron process private allocation at the captured checkpoint **316.7 MiB**. These are single observations, not cold-start/steady-idle benchmarks. The Qt experience harness reported first Home-surface paint including Qt imports **2298.6 ms**, cached callback mean **4.98 ms**, RSS **331.3 MiB** and hidden-idle one-core CPU **1.3%**. The timings and memory definitions differ, so no direct speed/memory ratio is asserted. The separate real Ollama check observed first visible streamed output after **17.30 seconds**; this includes interpretation/model work and is not a renderer-only latency or a cold/warm model benchmark. GPU utilisation/VRAM, combined Ollama use and display frame rate were not measured. Event-driven recordings are not frame-rate evidence.

Pinned frontend dependencies remain unchanged during M2: Electron 44.3.0, React 19.3.0, TypeScript 6.0.3, Vite 8.3.0, Monaco 0.56.0, xterm.js 6.0.0 and Motion 13.2.0, with the existing Radix/lucide foundation and committed lockfile. The native-file drop integration follows Electron?s [webUtils documentation](https://www.electronjs.org/docs/latest/api/web-utils); no generic filesystem bridge was added.

## Remaining limitations and review gate

- External Research/desktop/browser/application providers and optional package/IDE workflows have not all been exercised live through Electron; existing service/security tests and explicit action availability are retained.
- No new native Personal Core interface is implemented or claimed complete. M3 awaits M2 acceptance.
- No interactive PTY, optional language server or debugger is connected. Read-only output is labelled accordingly.
- Existing generated-code execution boundaries still depend on approved/trusted workspace policy and available isolation providers. A terminal component or working directory does not provide filesystem/network isolation. General descendant-process cleanup and adversarial sandbox stress require the final security gate.
- Very large profile/snapshot stress, matched Qt/Electron performance benchmarks, GPU/combined-model measurements, multiple-monitor and Windows DPI variants remain final acceptance work. Transport fails closed at its existing bounds; no unlimited recovery claim.
- Development uses the repository Python environment. Portable backend packaging, clean-machine validation and installer/signing/update validation are not complete. No default switch is justified by M2 alone.
- No protection claim against every malicious same-user process, no accessibility certification and no universal intelligence/vision claim.

Commits since M1: `43b83f7` (Core/settings/local data), `cc727a4` (task workspaces/Chat), `725a2fc` (Studio/isolated previews), `b3554c3` (handoffs/recovery/action verification). The following documentation-only commit records this review evidence. **Await M2 user review before continuing to new Personal Core interfaces.**
