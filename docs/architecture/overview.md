# OLIVE 3 agent platform architecture

> **Status (OLIVE 1.0, 2026-10-02).** The agent, permission and service boundaries
> described here still hold. The product shell is the Electron app in `desktop/`,
> which spawns `python -m olive.bridge`; the Qt sections describe the earlier 3.x
> presentation, which survives only as a development fallback (`python main.py`).
> Newer subsystems have their own pages: [Connect](../connect/README.md),
> [Connect World](../connect-world/protocol.md), [cross-device](cross-device.md) and
> the [documentation index](../README.md).

## OLIVE Connect World (transport)

Paired devices can also meet through an outbound-only relay when they are not on one
network. World sits *below* OLIVE Connect: the relay (`olive/world_relay`, standard
library only) joins a pair's two WebSockets and forwards the devices' own pinned TLS 1.3
bytes, which it cannot read. `olive/world` holds the wire protocol, WebSocket codec,
client bridge and the Direct/World path policy; `olive/connect/world.py` holds desktop
provisioning, vault-backed route keys and relay presence. Direct is always preferred and
both paths share one logical peer (`LocalNetwork.adopt`). Application protocols and
permissions are unchanged. See [docs/connect-world/protocol.md](../connect-world/protocol.md).

## 3.5.1 presentation migration

Electron main and a sandboxed React renderer connect to the existing Python ServiceContainer through a private versioned pipe protocol. No hidden Qt GUI initializes the backend. Qt remains a temporary fallback with shared profile ownership. See [the concrete boundary and limits](../releases/3.5.1/ARCHITECTURE.md). The historical Qt sections below describe the retained fallback.

## 3.5 development presentation boundary

`ui_qt/experience` adds local QQuickWidget surfaces for Welcome, Home and
navigation inside the one primary QMainWindow. Chat is a content-sized Widget
view; Studio retains its real native editor, docks and permission-bearing run/file
services. WindowManager still caches pages and owns explicit pop-outs.

ExperienceController exposes only named GUI actions and bounded presentation
models. Home submits through the existing NaturalLanguageOrchestrator; neither
QML nor the new shell owns tools, permissions, persistence or an inference loop.
BackendBridge retains its single QThread/asyncio runtime. Additive `Chat.draft`
storage preserves unsent composer text without changing pending-send approval.

The legacy shell remains selectable. Native relational Personal Core, vault and
mail domains remain planned behind the M1 visual gate; see `docs/features/personal.md`.

## OLIVE 3.4.1 interaction layer

The service container owns one NaturalLanguageOrchestrator shared by Home and Chat.
It interprets actual user utterances into strict intents, resolves bounded contextual
entities, and routes them to existing application controllers and authorized tools.
The UI does not parse command keywords. Conversation data and untrusted observations
are separate from command authority. See [natural-language architecture](natural-language.md)
for implementation, validation boundaries and provider limitations.
Current measured results are in [the 3.4.1 acceptance report](../archive/releases/3.4.1/DMDO_3_4_1_ACCEPTANCE.md).

Focused schema-validated interpretation handles file constraints, references,
pending edits and validation intent. Filesystem timestamp filtering runs before
result limits. Explicit document reads preserve original-path provenance and pass
the selected document ID through Chat to bounded, conversation-scoped retrieval.
The generic unsent-draft Qt card consumes copied controller state; editing its body
preserves the destination and cannot grant a send permit.
Generic native-editor submission is a separate consequence transaction: review
the exact destination/body, submit once, then observe a new message outside the
composer and an empty editor. An unverified result blocks repeat submission.
Chromium caret placement requires a separate mouse review and fresh editor hit
testing. Neither keyboard input nor a draft correction grants communication approval.

The completion pass adds generic browser navigation/search/tab and attachment routes,
media next/previous, file copy, project document linking and bounded research context.
Provider resolution uses saved application aliases and recent browser/media state.
Topic fallback searches only existing indexed documents in the authorized folder;
source-read and destination-write checks remain distinct for file transfers.
An optional Chat developer-details view exposes copied interpretation and resolved
steps without feeding observations into command authority.

## OLIVE 3.4 desktop runtime

The shared ServiceContainer owns DesktopController, DesktopGateway, DesktopWorkflow,
WindowsUIAutomationProvider and InteractiveController. Qt sends controller operations through
the existing asyncio runtime. Tools require an internal gateway capability, deterministic
permissions and confirmations; models cannot call provider primitives through ToolRegistry.
UIA runs in a bounded COM helper. A named Windows event propagates emergency stop into helpers.
ApplicationSessions preserve per-app identity and untrusted observations across a task.
The strict planner references existing control IDs and validates postconditions.
Interactive browsing owns a visible persistent OLIVE profile separate from Research contexts.
UniversalWorkflow sequences bounded cross-provider phases through the same controllers;
provider methods are not model-callable tools. Reviewed browser sends bind read-back fields,
uploads bind immutable bytes, and downloads reuse quarantine plus the existing filesystem
export boundary. Windows media-session and clipboard services are separately permissioned.
Shutdown drains cancelled operations before closing their provider resources.
Final acceptance adds explicit vision coordinates, non-authorizing label verification,
login-required state, viewport-verified scroll and an approved app-switch handoff.
UIA reaches sixteen levels while preserving node/time limits. Store and media use
generic provider paths.

## OLIVE 3.3 Research

The shared application container owns ResearchController, ResearchOrchestrator, search/browser providers, a bounded page cache and WebKnowledgeService. Qt Research uses the existing QThread/asyncio bridge; network activity never runs on the GUI thread. Research is a separate task/evidence lifecycle and does not replace Chat or the coding planner.

All outbound Research actions enter ToolRegistry and the existing permission/confirmation executor. Page text is untrusted observation data, never a tool program or authorization. A strict planner emits subquestions and queries. Deterministic extraction, hashing and evidence offsets preserve provenance; synthesis must cite read evidence IDs. Exact source quotes, source claims, inferences, uncertainty and possible disagreement remain distinct.

ResearchSession JSON and approved Web Knowledge metadata are additive. Existing KnowledgeSource fields gain optional web provenance; existing records continue loading. Web chunks use the existing RAG database in global/project namespaces. See docs/architecture/research.md for storage, limits, browser isolation and remaining evaluation limits.

## OLIVE 3.2 coding intelligence

The coding path is deterministic fast path, then structured Ollama planning when needed, strict schema validation, ToolRegistry, PermissionService, ConfirmationService, execution, observation, and bounded replanning or completion. Model text cannot create permissions or bypass registered tool schemas.

RepositoryMapService, CodeRetrievalService, and CodingContextService keep orientation, retrieval, and context budgeting separate. Repository files and build output are enclosed as untrusted observations. Incremental hashes prevent unchanged symbols and embeddings from being regenerated.

Execution is selected through ExecutionProviderRegistry. Trusted and approved projects use the native provider. Untrusted execution requires the optional Docker provider and fails closed when it is unavailable. Docker receives a single workspace mount, non-root identity, CPU, memory and process limits, a temporary filesystem, filtered environment, and disabled networking by default.

Studio consumes the same editing, checkpoint, run, problem, test, repository, and agent services as the rest of OLIVE. Optional LSP and visual-observation interfaces degrade cleanly when no provider is installed.

OLIVE 3 begins the transition from a chat application to a local-first personal assistant platform. Normal Chat mode retains the v2 conversation, memory, context, and RAG pipeline. Agent mode adds controlled planning and actions without treating model output as authorization.

## OLIVE 3.1 workspace boundary

`WorkspaceService` persists normalized approved roots and bounded discovery metadata. Every relative coding path is resolved through `Workspace.resolve`; traversal or absolute paths outside the root fail before file access. `RepositoryService`, `CodeIndexService`, `EditingService`, `CheckpointService`, `BuildAndTestService`, and `IDEService` remain UI-independent.

The coding flow is `resolve workspace → inspect/search → plan → checkpoint → hash-checked edit → validate → diff → summarize`. Workspace files and repository instructions are explicitly untrusted context. They can inform a plan but cannot alter permissions or directly invoke tools.

Code indexes are incremental local metadata keyed by size, modification time, and content hash. Generated/dependency directories are excluded by default. Task checkpoints are temporary file snapshots, not full backups, and restore only files listed for that OLIVE task.

## Agent lifecycle

`request → fast path → plan → permission evaluation → confirmation → tool execution → observation → evaluation → complete`

`AgentOrchestrator` owns bounded PLAN/ACT/OBSERVE iterations. Tasks have explicit state, a maximum of eight tool iterations by default, a runtime limit, and a cancellation event. Interrupted tasks are persisted as paused and never automatically resume a risky action.

`Planner` is a provider boundary. OLIVE 3 ships deterministic level-0 routing and interfaces for local-model planners. Future planners may use the generic `ModelRouter`, but every proposed action still passes through `ToolExecutor`.

## Authorization boundary

`ToolRegistry → PermissionService → ConfirmationService → Tool.execute`

Permissions are local JSON policies with ALLOW, ASK, and DENY decisions plus most-specific path scopes. Unknown permissions default to DENY. Delete, move, terminal, application launching, and other consequential definitions require confirmation. UI/system prompts cannot bypass this code path.

## Tools and Tool Host

Every tool has a namespaced identity, description, JSON-style input/output schemas, category, risk, permissions, confirmation flag, and timeout. `ToolResult` normalizes summaries, structured data, errors, artifacts, timing, and call IDs.

Tools currently run through `InProcessToolHost`. Its contract can later be implemented by an authenticated Windows background service while retaining the same registry and result types.

## Data domains

- Conversation history: existing chats repository.
- Personal memory: existing searchable memory repository.
- Persistent knowledge: existing RAG plus generalized `KnowledgeSource` provenance records.
- Projects: root folders, chats, knowledge, memories, tasks, and instructions.
- Agent tasks/audit: recoverable task state and privacy-filtered action metadata.
- Future training examples: explicit-approval-only store; no automatic fine-tuning.

All v2 files remain unchanged and readable. New stores are additive schema-version-1 JSON/JSONL files under `~/.olive` and are included in v2.4-compatible ZIP backup format 1 when present.

OLIVE 3.1 adds `workspaces.json` and `terminal_sessions.json` as optional schema-version-1 stores. Existing records need no rewrite. Code indexes and task checkpoints are rebuildable operational data and are excluded from portable backup archives.

## Home, Studio, and execution

The presentation path is `main.py -> OLIVEApplication -> ServiceContainer -> BackendBridge -> MainWindow + NavigationController -> cached Qt workspaces`. Qt Widgets supply native splitters, tables and docks. There is no QML dependency. One asyncio loop in a QThread owns the service graph and mutable application state; copied events arrive at GUI-thread slots through queued connections. Widgets submit controller operations and never instantiate repositories or Ollama clients. Home appears first; heavy pages are lazy and retained. Navigation uses a stack and history inside one main window. Explicit pop-outs move existing workspace instances; previews and dialogs remain separate. See [workspace shell](../archive/qt/QT_WORKSPACE_SHELL.md).

Qt-specific geometry, dock and open-tab metadata use a separate recoverable `ui-qt-state.json`. The offline native EditorAdapter has no filesystem authority: open/save/search actions use registered Studio tools and existing permission, confirmation, editing and checkpoint services. Local previews use off-the-record WebEngine profiles and exact loopback-origin restrictions, with no Python/JavaScript bridge. See docs/archive/qt/QT_MIGRATION.md for shutdown, restore and threading details.

`StudioService` operates directly on approved workspace files and delegates saves to hash-checked `EditingService` plus `CheckpointService`. `RunService` owns bounded asynchronous `RunSession` processes, filtered environments, output/error capture, localhost URL discovery, stop/restart, and workspace-contained artifacts. `ProblemService` converts supported Python/.NET/compiler output into clickable file/line diagnostics.

Future desktop interaction uses registered application adapters and `DesktopControlService` with an explicit ACT/OBSERVE/VERIFY lifecycle. No keyboard, mouse, screen-capture, or Discord self-bot provider ships in 3.1. Application observations are untrusted input. External messages use `communication.send` and an exact-message preview contract.

## Research architecture

The research registry is topic-neutral and supports provenance, competing claims, source identifiers, reliability notes, and uncertainty. OLIVE 3.3 implements public-web search and reading. Authenticated web, archives, Git/RSS source providers and Tor remain future contracts with no implicit host authority.
# M3 native runtime addition

The Electron Personal Core uses `olive/personal/` for transactional native records,
interchange, scheduling and policy-bearing tools. `PersonalController` is owned by
the same ServiceContainer as Chat/Agent/Research; routes do not create extra
backends. Strict bridge envelopes dispatch to shared registered tools. The shared
NaturalLanguageOrchestrator/CapabilityRouter maintains revisioned native proposals
and selected record IDs. React keeps presentation/draft state, not an authoritative
personal database. See [docs/features/personal.md](../features/personal.md) for schema, permission,
timezone, import and recovery boundaries. M3 implementation and internal acceptance are complete; classified evidence is in docs/releases/3.5.1/M3_COMPLETION.md.


OLIVE was formerly named DMDO. See [the rebrand compatibility map](legacy-dmdo-compatibility.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
