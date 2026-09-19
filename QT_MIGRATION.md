# OLIVE 3.2.5 Qt migration

This document records the 3.2.5 migration. The default multi-window navigation described
below is superseded in 3.4 by the [single-window workspace shell](QT_WORKSPACE_SHELL.md).
Qt, shared services, Studio docking and secondary previews remain in use.

## Pre-migration audit - 2026-09-05

Initial HEAD: `637d947`. The initial worktree was **not clean**: eight modified files and one new regression-test file from the preceding authorized reliability work. Preserved separately as `5d7de1b`; migration branch: `migration/qt-3.2.5`. The worktree was then clean before migration edits.

Baseline compileall succeeded. All **164 tests** passed (the earlier 155 plus nine reliability regressions). All Python modules were inventoried by AST/import inspection; current Flet pages, mixins, settings, dialogs and service boundaries were inspected. No existing core data formats need changing.

The previous Flet architecture combines a service graph in `olive/app.py` with UI mixins that also coordinate generation, indexing and user decisions. Core modules under agent, tools, services, storage, knowledge and desktop are reusable without Qt or Flet. The migration moves application coordination into `olive/application/`, with a single container per process and UI-neutral operations/events. Qt widgets consume snapshots and submit controller operations; they do not become service owners.

## Release gate

Flet coexisted with Qt during development. Following the feature mapping review, passing automated checks and visible desktop smoke, main.py launches Qt and the legacy presentation modules and declared Flet dependency are removed. The inventory below records the pre-migration repository, including historical paths. QT_FEATURE_PARITY.md distinguishes individually exercised desktop interactions from implementation review and records external-component acceptance limits.

## Framework and thread decisions

Qt Widgets first; no QML dependency. Native dock widgets and a QPlainTextEdit EditorAdapter are the initial editor provider. Monaco is deferred: offline bundling, bridge review and WebEngine deployment must be demonstrated before changing editor provider. Local preview, if enabled, uses an isolated WebEngine profile and exact-origin allowlisting without a host bridge.

One background asyncio loop owns the service container and mutable application state. Qt signals deliver copied snapshots to GUI-thread QObject slots. GUI callbacks never access service objects directly. Blocking parsing and external inspection use bounded background work. Feature windows are lazy singletons; closing one does not stop shared tasks. UI geometry/dock state is a separate recoverable JSON file.

References: [Qt thread affinity](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QObject.html), [Qt deployment](https://doc.qt.io/qtforpython-6/deployment/index.html), [WebEngine deployment](https://doc.qt.io/QT-6/qtwebengine-deploying.html).

## Module responsibility inventory

| Module | Responsibility |
|---|---|
| `olive/__init__.py` | UI-neutral backend / contracts |
| `olive/agent/__init__.py` | UI-neutral backend / contracts |
| `olive/agent/agent_session.py` | UI-neutral backend / contracts |
| `olive/agent/agent_task.py` | UI-neutral backend / contracts |
| `olive/agent/audit_service.py` | UI-neutral backend / contracts |
| `olive/agent/coding_agent.py` | UI-neutral backend / contracts |
| `olive/agent/coding_plan.py` | UI-neutral backend / contracts |
| `olive/agent/confirmation_service.py` | UI-neutral backend / contracts |
| `olive/agent/deterministic_planner.py` | UI-neutral backend / contracts |
| `olive/agent/executor.py` | UI-neutral backend / contracts |
| `olive/agent/fast_path.py` | UI-neutral backend / contracts |
| `olive/agent/model_router.py` | UI-neutral backend / contracts |
| `olive/agent/orchestrator.py` | UI-neutral backend / contracts |
| `olive/agent/permission_service.py` | UI-neutral backend / contracts |
| `olive/agent/planner.py` | UI-neutral backend / contracts |
| `olive/agent/structured_coding_planner.py` | UI-neutral backend / contracts |
| `olive/agent/tool_registry.py` | UI-neutral backend / contracts |
| `olive/agent/tool_result.py` | UI-neutral backend / contracts |
| `olive/agent/tool_schema.py` | UI-neutral backend / contracts |
| `olive/agent/workspace_planner.py` | UI-neutral backend / contracts |
| `olive/app.py` | Service composition + Flet lifecycle (extract composition) |
| `olive/config.py` | UI-neutral backend / contracts |
| `olive/desktop/__init__.py` | UI-neutral backend / contracts |
| `olive/desktop/adapters.py` | UI-neutral backend / contracts |
| `olive/desktop/communication.py` | UI-neutral backend / contracts |
| `olive/desktop/control.py` | UI-neutral backend / contracts |
| `olive/evaluation/__init__.py` | UI-neutral backend / contracts |
| `olive/evaluation/coding_integration.py` | UI-neutral backend / contracts |
| `olive/evaluation/rag_benchmark.py` | UI-neutral backend / contracts |
| `olive/indexing_job.py` | UI-neutral backend / contracts |
| `olive/knowledge/__init__.py` | UI-neutral backend / contracts |
| `olive/knowledge/learning_service.py` | UI-neutral backend / contracts |
| `olive/knowledge/provider.py` | UI-neutral backend / contracts |
| `olive/knowledge/research.py` | UI-neutral backend / contracts |
| `olive/knowledge/source.py` | UI-neutral backend / contracts |
| `olive/knowledge/training_store.py` | UI-neutral backend / contracts |
| `olive/logging_config.py` | UI-neutral backend / contracts |
| `olive/memory.py` | UI-neutral backend / contracts |
| `olive/models.py` | UI-neutral backend / contracts |
| `olive/projects.py` | UI-neutral backend / contracts |
| `olive/services/__init__.py` | UI-neutral backend / contracts |
| `olive/services/application_observation_service.py` | UI-neutral backend / contracts |
| `olive/services/backup_service.py` | UI-neutral backend / contracts |
| `olive/services/build_session_service.py` | UI-neutral backend / contracts |
| `olive/services/build_test_service.py` | UI-neutral backend / contracts |
| `olive/services/chat_service.py` | UI-neutral backend / contracts |
| `olive/services/checkpoint_service.py` | UI-neutral backend / contracts |
| `olive/services/code_index_service.py` | UI-neutral backend / contracts |
| `olive/services/code_retrieval_service.py` | UI-neutral backend / contracts |
| `olive/services/coding_context_service.py` | UI-neutral backend / contracts |
| `olive/services/context_service.py` | UI-neutral backend / contracts |
| `olive/services/dependency_service.py` | UI-neutral backend / contracts |
| `olive/services/diagnostics_service.py` | UI-neutral backend / contracts |
| `olive/services/diff_review_service.py` | UI-neutral backend / contracts |
| `olive/services/document_health_service.py` | UI-neutral backend / contracts |
| `olive/services/document_service.py` | UI-neutral backend / contracts |
| `olive/services/editing_service.py` | UI-neutral backend / contracts |
| `olive/services/editor_intelligence_service.py` | UI-neutral backend / contracts |
| `olive/services/execution_provider.py` | UI-neutral backend / contracts |
| `olive/services/file_search_service.py` | UI-neutral backend / contracts |
| `olive/services/generation_pipeline.py` | UI-neutral backend / contracts |
| `olive/services/grounding_service.py` | UI-neutral backend / contracts |
| `olive/services/ide_service.py` | UI-neutral backend / contracts |
| `olive/services/indexing_job_service.py` | UI-neutral backend / contracts |
| `olive/services/indexing_scheduler.py` | UI-neutral backend / contracts |
| `olive/services/language_server_service.py` | UI-neutral backend / contracts |
| `olive/services/maintenance_service.py` | UI-neutral backend / contracts |
| `olive/services/memory_service.py` | UI-neutral backend / contracts |
| `olive/services/memory_suggestion_service.py` | UI-neutral backend / contracts |
| `olive/services/model_metrics_service.py` | UI-neutral backend / contracts |
| `olive/services/model_registry.py` | UI-neutral backend / contracts |
| `olive/services/ocr_service.py` | UI-neutral backend / contracts |
| `olive/services/ollama_service.py` | UI-neutral backend / contracts |
| `olive/services/problem_service.py` | UI-neutral backend / contracts |
| `olive/services/prompt_service.py` | UI-neutral backend / contracts |
| `olive/services/rag_service.py` | UI-neutral backend / contracts |
| `olive/services/rag_settings.py` | UI-neutral backend / contracts |
| `olive/services/repository_map_service.py` | UI-neutral backend / contracts |
| `olive/services/repository_service.py` | UI-neutral backend / contracts |
| `olive/services/retrieval_evaluation.py` | UI-neutral backend / contracts |
| `olive/services/run_service.py` | UI-neutral backend / contracts |
| `olive/services/studio_service.py` | UI-neutral backend / contracts |
| `olive/services/syntax_highlight_service.py` | UI-neutral backend / contracts |
| `olive/services/terminal_session_service.py` | UI-neutral backend / contracts |
| `olive/services/test_result_service.py` | UI-neutral backend / contracts |
| `olive/services/web_preview_service.py` | UI-neutral backend / contracts |
| `olive/services/workspace_service.py` | UI-neutral backend / contracts |
| `olive/storage/__init__.py` | Repository / persistence |
| `olive/storage/agent_task_repository.py` | Repository / persistence |
| `olive/storage/chat_repository.py` | Repository / persistence |
| `olive/storage/indexing_job_repository.py` | Repository / persistence |
| `olive/storage/json_store.py` | Repository / persistence |
| `olive/storage/knowledge_source_repository.py` | Repository / persistence |
| `olive/storage/memory_repository.py` | Repository / persistence |
| `olive/storage/migration.py` | Repository / persistence |
| `olive/storage/project_repository.py` | Repository / persistence |
| `olive/storage/rag_store.py` | Repository / persistence |
| `olive/storage/settings_repository.py` | Repository / persistence |
| `olive/storage/workspace_repository.py` | Repository / persistence |
| `olive/themes.py` | UI-neutral backend / contracts |
| `olive/tools/__init__.py` | UI-neutral backend / contracts |
| `olive/tools/code.py` | UI-neutral backend / contracts |
| `olive/tools/filesystem.py` | UI-neutral backend / contracts |
| `olive/tools/git.py` | UI-neutral backend / contracts |
| `olive/tools/host.py` | UI-neutral backend / contracts |
| `olive/tools/ide.py` | UI-neutral backend / contracts |
| `olive/tools/studio.py` | UI-neutral backend / contracts |
| `olive/tools/system.py` | UI-neutral backend / contracts |
| `olive/tools/terminal.py` | UI-neutral backend / contracts |
| `olive/tools/workspace.py` | UI-neutral backend / contracts |
| `olive/ui/__init__.py` | Presentation support (UI-neutral types where possible) |
| `olive/ui/agent_mixin.py` | Flet presentation / orchestration |
| `olive/ui/app_shell.py` | Flet presentation / orchestration |
| `olive/ui/attachments_mixin.py` | Flet presentation / orchestration |
| `olive/ui/chat_mixin.py` | Flet presentation / orchestration |
| `olive/ui/components.py` | Flet presentation / orchestration |
| `olive/ui/dashboard_components.py` | Flet presentation / orchestration |
| `olive/ui/design_system.py` | Presentation support (UI-neutral types where possible) |
| `olive/ui/dialogs.py` | Flet presentation / orchestration |
| `olive/ui/dialogs_mixin.py` | Flet presentation / orchestration |
| `olive/ui/feature_registry.py` | Presentation support (UI-neutral types where possible) |
| `olive/ui/file_dialog_service.py` | Flet presentation / orchestration |
| `olive/ui/layout_mixin.py` | Flet presentation / orchestration |
| `olive/ui/navigation.py` | Presentation support (UI-neutral types where possible) |
| `olive/ui/navigation_mixin.py` | Flet presentation / orchestration |
| `olive/ui/notifications.py` | Flet presentation / orchestration |
| `olive/ui/pages/__init__.py` | Presentation support (UI-neutral types where possible) |
| `olive/ui/pages/agent_page.py` | Flet presentation / orchestration |
| `olive/ui/pages/dashboard_page.py` | Flet presentation / orchestration |
| `olive/ui/pages/diagnostics_page.py` | Flet presentation / orchestration |
| `olive/ui/pages/home_page.py` | Flet presentation / orchestration |
| `olive/ui/pages/knowledge_page.py` | Flet presentation / orchestration |
| `olive/ui/pages/memory_page.py` | Flet presentation / orchestration |
| `olive/ui/pages/projects_page.py` | Flet presentation / orchestration |
| `olive/ui/pages/settings_page.py` | Flet presentation / orchestration |
| `olive/ui/pages/studio_page.py` | Flet presentation / orchestration |
| `olive/utils/__init__.py` | UI-neutral backend / contracts |
| `olive/utils/chunking.py` | UI-neutral backend / contracts |
| `olive/utils/files.py` | UI-neutral backend / contracts |
| `olive/workspace.py` | UI-neutral backend / contracts |

## Implemented module boundaries

- `application/service_container.py` constructs one service graph, reuses existing stores and migrators, and dispatches named UI-neutral controller operations.
- Chat, Agent, Knowledge, Data and Studio controllers coordinate existing backend services. Permission decisions stay in PermissionService; confirmations stay in ConfirmationService; editor writes pass through ToolRegistry, EditingService and CheckpointService.
- `ui_qt/runtime.py` owns transport and a QThread-hosted asyncio loop. Queued signals deliver copied snapshots and callbacks to GUI slots. Confirmations use futures resolved on that loop. Blocking document extraction uses a worker executor.
- `ui_qt/window_manager.py` owns lazy feature singletons, safe restoration, confirmations and tray actions. Closing a feature hides its window without destroying shared services. Closing Home exits the runtime rather than silently leaving a permanent background process.
- `ui_qt/studio/` contains the native editor adapter, dock workspace, actions and exact-origin WebEngine preview. No JS host bridge, runtime CDN or Monaco dependency exists.

## Responsiveness and shutdown

Chat stream events are batched at roughly 50 ms intervals and appended incrementally. Initial history rendering is limited to the latest 80 messages with a load-earlier action. Run/terminal drains are incremental and bounded. Studio source files retain the existing size limit and expected-hash concurrency check. Pending saves prevent tab/window destruction. Duplicate Run requests are rejected even while confirmation is pending.

Shutdown cancels generation, agent/direct-tool work, indexing and controlled run sessions before ending the event loop. Pending confirmations resolve as cancellation. Async generators and executor work are joined. Preview pages are disposed before their isolated profiles. Failed startup remains closable. Optional layout-write failures are logged without treating them as core data corruption.

Restore refuses active work, uses the existing safety-backup mechanism, reloads restored chats and blocks mutations until restart. Shutdown does not overwrite restored chats with stale snapshots. Export uses persisted formats, excluding Qt display-only state.

## Editor and preview decisions

Widgets fit Studio's dock, tree, table and editor requirements without introducing a QML build/runtime boundary. The native QPlainTextEdit provider supports line numbers, syntax/current-line highlighting, diagnostics, selection, cursor, find/replace, go-to-line, auto-indent, tab width and font settings. Monaco remains a future provider: locally bundle versioned assets, expose only explicit editor events, prohibit filesystem/terminal/eval bridges and validate frozen-build behavior before adoption.

Preview is for a single HTTP(S) loopback origin. Navigation and subresources are constrained, profiles are temporary, permissions/downloads are denied and no ordinary browser profile is shared. General browsing remains reserved for 3.3.

## Validation and migration debt

See QT_FEATURE_PARITY.md and QT_RELEASE_REPORT.md. The visible smoke script uses a temporary data directory and harmless local fixture; its confirmation auto-approval exists only inside that opt-in test script. One separate run used an installed Ollama model. No models were downloaded.

Remaining acceptance work includes clean-machine packaging, external OCR/Docker execution, and wider visual/accessibility testing across display configurations. Native highlighting is lightweight; Monaco and richer language intelligence are follow-ups. Test selectors remain unavailable where the existing backend supports only whole-suite execution. These differences are explicit rather than silently dropping controls or bypassing services.


OLIVE was formerly named DMDO. See [the rebrand compatibility map](docs/OLIVE_REBRAND.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
