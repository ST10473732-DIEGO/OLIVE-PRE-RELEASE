# OLIVE

OLIVE is the existing local-first desktop assistant, formerly DMDO. The active
3.5.1 completion branch is `final/windows-stable-baseline`: Electron/React presentation,
one authoritative Python runtime, Calendar/Tasks/Reminders, Projects/Knowledge/Memory,
and native Mail with optional protected SMTP/IMAP connections. The blue dot-matrix
olive Core and existing green desktop icon are retained.

Open Mail from the navigation spine (**Personal → Mail**), All Spaces or the
command palette. Drafts, imported EML, local search and Personal Core composition
work without an account or model. Optional setup is in
**Settings → Connections → Mail**. See
[Mail setup and limits](MAIL_TRANSPORTS.md), [credential security](ACCOUNT_SECURITY.md),
[Personal Core](PERSONAL_CORE.md) and [M4 evidence](docs/releases/3.5.1/M4_COMPLETION.md).

For Electron, build/start from `desktop` using the pinned Node toolchain; see
[desktop instructions](desktop/README.md). The post-entry interface redesign
(navigation spine, workspace layouts, shared design tokens) is described in
[the design refresh notes](docs/releases/3.5.1/DESIGN_REFRESH.md); the Welcome
screen, Core and desktop icon are unchanged. `scripts/launch_electron_preview.ps1`
opens a separate synthetic preview profile. `run_olive.bat` launches the current
Electron design after `npm ci` and `npm run build` in `desktop`. The historical
Qt entry point remains `python main.py`. Do not run two writers against one profile. Explicit
`OLIVE_DATA_DIR` wins; fresh `.olive` and legacy `.dmdo` continuity are documented
in [the rebrand map](docs/OLIVE_REBRAND.md).

This remains an untagged development baseline. No installer or clean-machine
certification is claimed. See [Windows baseline](docs/WINDOWS_STABLE_BASELINE.md)
and [Linux preparation](docs/LINUX_PORT_READINESS.md). Current requirements and
remaining release gates are in [the plan](docs/releases/3.5.1/PLAN.md) and
[status](docs/releases/3.5.1/STATUS.md). Historical Git maintenance issues remain
separately recorded; no history repair was attempted.

## Historical release evidence

The sections below describe their original checkpoints, not current milestone
status. Welcome is an introduction, not authentication.

The 3.4.1 validation results and provider limitations are recorded in
[the acceptance report](DMDO_3_4_1_ACCEPTANCE.md). Natural-language examples describe
ordinary requests; they are not a required command syntax.

## OLIVE 3.4.1 — natural interaction

Home and Chat now share a natural-language entry point. Describe what you want to
do; OLIVE interprets the request, resolves context and uses the existing authorized
services. You do not need to enter Agent or Desktop Control before asking for an
action. Required confirmations still apply.

Selected-file follow-ups use bounded document retrieval, and Chat displays unsent
messages with their destination and Edit/Cancel controls. Reviewing Send remains a
request to the existing confirmation-protected service, never implicit approval.

File identity survives browser/application switches. Selected files can be copied,
moved, linked to project Knowledge or uploaded through the reviewed browser path.
Topic searches can use documents already indexed in the current conversation.
Browser draft preparation preserves recipient, subject and body; submission still
requires its separate verified review flow. Music controls include next/previous.
These are examples of capabilities, not required command phrases.

3.4.1 acceptance passes 514 automated tests, 49 Qt checks, 37 original semantic
cases, 145 expanded cases and four original compounds. Live browser, adapter-free
app, file/context and Windows navigation checks pass. One user-authorized Discord
hello was verified in the corrected destination. See the [acceptance report](DMDO_3_4_1_ACCEPTANCE.md)
and [provider limitations](NATURAL_LANGUAGE_ARCHITECTURE.md).

## One integrated desktop workspace

OLIVE opens Home inside one main Qt window. The persistent navigation rail, Home cards,
command palette and tray actions switch cached workspaces in that same window. Chat,
Studio, Research and Desktop Control retain their widget state while you navigate;
background tasks continue on the shared service runtime. Settings and Diagnostics
are workspaces too. Collapse the navigation rail for more Studio space.

Use Back/Forward or Alt+Left/Right for workspace history, Ctrl+1 through Ctrl+5 for
Home/Chat/Agent/Studio/Research, and Ctrl+K for commands. **Pop out** explicitly moves
Chat, Studio, Research or Desktop Control into a secondary window; closing that window
returns the same workspace to OLIVE. Previews, native dialogs and launched applications
remain separate where appropriate. See [workspace shell architecture](QT_WORKSPACE_SHELL.md).

## OLIVE 3.4 — Universal Windows desktop control

The current branch adds local model roles/benchmarks and a Qt Desktop Control workspace.
Enable Desktop Control in Settings, inspect an application, select an accessible control,
then review an action and its expected result. A reviewed plan can use multiple inspected
applications; Agent accepts an explicit `desktop:` objective. STOP CONTROL sets a shared
stop event immediately. Windows may also register Ctrl+Alt+Escape when control is enabled.

Interactive Chrome uses a separate visible OLIVE profile. It supports inspected DOM fields
and controls with permission checks; it does not import your normal browser credentials.
Research remains separate. Live fixtures have verified Notepad text, an adapter-free Qt app,
Explorer location, Settings navigation, local Chrome interaction and window/vision observation.
Reviewed uploads, quarantined downloads, local-fixture communication previews and bounded
multi-app workflows are connected. Calculator also passes generic control without an adapter.
Final acceptance passes generic UIA, single-window Qt, interactive Chrome, real system
media, Store search/install preview and multi-app workflows. Gmail correctly reaches
manual login. Vision verifies labels; localization remains a measured limitation.
No real email, installation or purchase was performed. See [final acceptance](DMDO_3_4_ACCEPTANCE.md).

OLIVE is a private, local-first personal AI assistant platform powered by Ollama. OLIVE 3.3 adds Research, public-web reading and approved Web Knowledge to the existing PySide6 / Qt 6 desktop.

## OLIVE 3.3 Research

Open Research from Home or the command palette. Choose a project and Quick, Standard or Deep depth, then start an investigation. Plans, sources, evidence and reports persist locally; interrupted sessions reopen paused. Citations open the source/evidence inspector. Studio's Research action supplies bounded selection/error context, and Chat offers an explicit Research entry without slowing ordinary conversations.

Knowledge → Web sources / Learn website supports single pages, selected URLs, documentation subsections and bounded page sitemaps. Review the exact scope before saving. Existing Ollama embeddings and lexical fallback are reused. Unchanged content is not re-embedded; source hashes, dates, project association and update history are retained. Permanent learning always requires approval.

Settings → Research controls resource limits and providers. DDGS supplies free public search; optional SearXNG JSON search is configurable. Static reading is the default first step; isolated Playwright/Edge contexts handle rendered pages. Missing browser binaries produce manual setup guidance, never an automatic download. Web material has no authority to approve tools, run commands or change policies. Downloads remain quarantined until an explicit read/save/import decision.

See [Research architecture and limitations](RESEARCH_ARCHITECTURE.md). Opt-in smoke scripts use disposable data: `python scripts/research_live_smoke.py` and `python scripts/qt_desktop_smoke.py`. Ordinary unit tests require no internet.

## OLIVE 3.2.5 native desktop

Run `run_olive.bat` or `.venv\Scripts\python.exe main.py`. The 3.2.5 migration established the Qt backend boundary; 3.4 now hosts features in the shared main window described above. Studio uses native docks, an offline Qt editor, Ctrl+S save, Ctrl+P quick open and Ctrl+Shift+F workspace search.

The editor supports line numbers, highlighting, find/replace, auto-indent and hash-checked saves. Monaco is deferred; no editor content is fetched from a CDN. Closing the main window exits the shared runtime after unsaved-file checks. Layout is stored separately in `ui-qt-state.json` and can be reset safely. No model download, Docker installation or cloud service is required by this migration.

See [migration architecture](QT_MIGRATION.md), [feature parity and validation limits](QT_FEATURE_PARITY.md), [release report](QT_RELEASE_REPORT.md), and [Windows packaging](PACKAGING_WINDOWS.md).

## OLIVE 3.2 intelligent coding

- Complex workspace requests can use an installed coding-role Ollama model to produce strict JSON plans. Every proposed step is validated against the registered tool schema before the deterministic permission and confirmation boundary.
- Failed observations may trigger bounded replanning; identical failed tool calls, runtime limits, cancellation, and iteration limits prevent uncontrolled loops.
- Tasks separately record implementation status, validation status, completion conditions, evidence, and concise reasoning summaries.
- Incremental repository maps and hybrid exact/symbol/semantic code retrieval orient the planner without loading an entire repository into a prompt.
- Native execution remains the default for trusted and approved workspaces. Untrusted execution requires Docker Desktop with no network by default, resource limits, a filtered environment, and no Docker socket.
- Studio adds workspace-aware AI requests, language/symbol state, find/replace, go-to-line, syntax-highlighted previews, structured test results, and deduplicated Problems.
- Application observation is limited to a OLIVE RunSession process. Optional vision results use strict validated states and never authorize actions.

Docker is optional and is never installed automatically. When Docker is unavailable, untrusted execution fails closed while approved local development continues normally.

## OLIVE 3.1 workspace and coding platform

- Approved workspaces are normalized filesystem roots linked optionally to existing OLIVE projects.
- Bounded discovery recognizes Python, .NET, Node, Java, Rust, and Git project markers without crawling the whole PC.
- Git tools provide status, diffs, logs, branches, add, commit, branch creation, and checkout. Destructive reset/clean/force-push shortcuts are intentionally unavailable.
- Incremental code indexing extracts lightweight symbols and skips virtual environments, dependencies, Git data, and build output.
- Coding tools use bounded line reads, targeted searches, line-aware results, expected hashes, and atomic targeted edits.
- Task checkpoints restore only files changed by OLIVE; they never use destructive Git resets.
- Known Python and .NET validation is detected locally. Unknown package scripts remain approval-required.
- Visual Studio and VS Code can be detected and opened without keyboard or mouse automation.
- Workspace content is treated as untrusted input and never grants tool authorization.

## Home and OLIVE Studio

OLIVE opens to a modular Home dashboard. FeatureRegistry supplies the navigation and cards.
Qt creates feature workspaces lazily inside one main window and caches them for reuse.
All workspaces and explicit pop-outs share one application service container and background runtime.

OLIVE Studio edits the same approved workspace files used by the coding agent. It provides a project explorer, multiple file tabs, unsaved indicators, line numbers, workspace search, safe save/checkpoints, Git branch status, Problems, Output and Tests panels, and Run/Stop/Restart controls. Local web previews use an isolated Qt WebEngine profile restricted to the exact development origin; desktop GUI applications launch as their own process. Generated processes receive a filtered environment and bounded runtime by default.

## OLIVE 3.0 agent platform

- Chat mode remains conversation-oriented and uses the existing generation pipeline.
- Agent mode supports bounded plan/action/observation tasks and deterministic fast paths.
- Every action passes through the tool registry, scoped permission engine, and reusable confirmation engine.
- Foundational Windows tools cover bounded filesystem operations, controlled PowerShell/CMD/Python execution, application/path opening, and process listing.
- Projects and agent tasks persist locally; interrupted risky tasks recover paused.
- Generalized knowledge provenance and explicit-approval learning stores underpin 3.3 public-web Research. Cloud inference remains unnecessary; authenticated and Tor providers remain future work.
- See [ARCHITECTURE_3.md](ARCHITECTURE_3.md) and [DEPLOYMENT_DESIGN.md](DEPLOYMENT_DESIGN.md).

## What changed in v2

- Renamed the application and all current branding to **OLIVE**.
- Moved new application data to `~/.olive`.
- Imports existing chats, model defaults, aliases and theme settings from the older local data directory on first run without deleting the old files.
- Replaced the large single-file architecture with separate services, storage, utilities and UI helpers.
- Fixed the missing dialog helper problem by centralising dialog open/close behaviour.
- Fixed summarisation so the hidden summary request is not inserted into chat history.
- Reworked regeneration so generated alternatives are actually tracked as branches.
- Replaced large-document prompt dumping with local RAG.
- Added PDF page-aware chunking, DOCX support, source labels, SQLite storage and optional Ollama embeddings.
- Kept a lexical retrieval fallback, so document search still works if the embedding model is not installed.
- Uses Ollama model metadata/capabilities when available instead of relying only on model-name keywords.

## Project layout

```text
OLIVE/
  main.py                 # native Qt entry point
  olive/
    application/          # UI-neutral controllers and shared services
    ui_qt/                # native windows, docks, dialogs and editor
    agent/ tools/         # deterministic authorization and orchestration
    services/ storage/    # reusable backend and local persistence
  tests/
  scripts/qt_desktop_smoke.py
```

## Windows setup

1. Install and start Ollama.
2. Open Command Prompt in this folder.
3. Run:

```bat
setup_windows.bat
```

4. Start OLIVE:

```bat
run_olive.bat
```

You can also run it manually:

```bat
.venv\Scripts\activate
python main.py
```

## Document retrieval

When a PDF, DOCX or text/code file is attached, OLIVE:

1. copies the attachment into its local data cache;
2. extracts page-aware text where possible;
3. chunks the text;
4. stores the chunks in a local SQLite index;
5. creates embeddings through the configured Ollama embedding model if that model is installed;
6. falls back to lexical retrieval if embeddings are unavailable;
7. sends only the most relevant chunks to the chat model.

OLIVE prefers the configured embedding model, otherwise selects an installed embedding-capable Ollama model. Without one, it continues with local lexical retrieval. OLIVE never downloads a model automatically.

## Local data schemas

- `chats.json` uses schema version 2. New message source/memory metadata and document status fields are optional, so v2.0/v2.1 records remain readable.
- `memories.json` uses schema version 1 and is separate from chat history.
- `rag.sqlite3` records its component schema in the `schema_info` table. Version 1 adds metadata only and initializes idempotently without replacing existing document or chunk tables.
- Existing chunks without embeddings are upgraded in place when an installed embedding model becomes available; chunk rows and source files are not deleted or duplicated.
- `indexing_jobs.json` uses schema version 1. Interrupted running jobs recover as queued and completed document versions are not repeated.

## OLIVE 2.3 reliability

- Indexing jobs persist locally and can be inspected, paused, resumed, cancelled, or retried.
- PDFs use native text and table extraction first. Image-bearing pages with insufficient text are marked as OCR candidates.
- Optional OCR uses a local `tesseract.exe` installation. OLIVE continues without OCR when Tesseract is unavailable.
- OCR, native PDF text, and table text retain page and origin provenance in the RAG index.
- Retrieval quality can be measured with Recall@K, Precision@K, MRR, and hit rate using local fixtures.
- The Retrieval Inspector shows lexical, semantic, and final hybrid scores without exposing embeddings.
- Document-grounding labels are heuristic estimates, not proof of factual correctness.
- Optional model-generated memory proposals use strict JSON validation and always require review by default.
- Source files have content hashes and change detection; missing originals never cause an existing index to be deleted.

To enable OCR, install Tesseract OCR for Windows and ensure `tesseract.exe` is on `PATH`. No OCR package or model is downloaded by OLIVE.

## OLIVE 2.4 operations and data safety

- Full portable ZIP backups include chats, memories, settings, persistent indexing jobs, and the RAG database while excluding temporary attachment caches.
- Backup format version 1 includes a manifest and schema versions. Restore validates and stages all data, creates an automatic safety backup, and rolls back replaced files on failure.
- A bounded local scheduler defaults to one indexing worker (maximum three), recovers interrupted jobs, and supports pause, resume, cancel, and retry.
- Missing or changed document sources retain their working index and can be relinked from the knowledge bar.
- Tesseract is discovered from `PATH`, standard Windows Program Files locations, or an optional validated Settings path. TSV output preserves line order and records confidence when available.
- Advanced RAG controls are validated and can be reset without re-indexing.
- Response provenance is available without adding metadata to generated answer text.
- Run the benchmark with `.venv\\Scripts\\python.exe -m olive.evaluation.rag_benchmark`.

Backups created by OLIVE 2.4 use backup format version 1. Restore accepts only supported manifests; legacy v2.0–v2.3 live data remains readable through existing migrations.

OLIVE 3.1 retains backup format version 1 and adds workspaces and task-scoped terminal-session metadata when those files exist. Incremental code indexes and temporary checkpoints are reproducible caches and are not included.

## Local data

Fresh OLIVE profiles use:

```text
%USERPROFILE%\.olive
```

Existing `%USERPROFILE%\.dmdo` profiles are reused in place. `OLIVE_DATA_DIR` (or its legacy `DMDO_DATA_DIR` alias) selects an explicit custom profile. If both default locations contain data, startup requires an explicit choice; it does not merge or move anything. Settings > Diagnostics shows the actual data location.

## Development

Run checks from the repository root:

```bat
python -m compileall -q .
python -m unittest discover -s tests -v
```

For OpenAI Codex, the repository includes `AGENTS.md`, which tells coding sessions to preserve OLIVE's local-first architecture and data-safety rules.


OLIVE was formerly named DMDO. See [the rebrand compatibility map](docs/OLIVE_REBRAND.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
