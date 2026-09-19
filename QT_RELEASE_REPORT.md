# DMDO 3.2.5 release report

DMDO now launches through native PySide6 / Qt 6. The migration reuses the DMDO 3.2 backend, preserves existing data formats and removes the old Flet presentation dependency. This is a desktop migration, not DMDO 3.3.

## Requested completion report

| # | Area | Result |
|---|---|---|
| 1 | Pre-migration audit | Initial worktree contained preceding authorized reliability fixes. Preserved as 5d7de1b; clean baseline then compiled and passed 164 tests (155 original plus nine fixes). Requested documents and the 140-module repository inventory were reviewed before migration edits. |
| 2 | Migration architecture | Core services -> UI-neutral application controllers/state -> queued Qt bridge -> widgets. See QT_MIGRATION.md. |
| 3 | Framework | PySide6 / Qt 6; tested PySide6 6.11.2. |
| 4 | Widgets versus QML | Widgets throughout: native windows, docks, splitters, tables, trees and dialogs. No QML build/runtime boundary. |
| 5 | Service container | One shared service graph for Ollama, repositories, Agent, memory, RAG, projects, workspaces and indexing. A data-directory lock prevents duplicate Qt runtimes. |
| 6 | Windows | Lazy Home, Chat, Agent, Studio, Projects, Knowledge, Memory, Settings and Diagnostics. Singleton reopening retains state; geometry/docks are separately recoverable. |
| 7 | Thread/async model | One QThread-hosted asyncio loop; copied events/results reach queued GUI slots. Extraction uses executor work; generation and process output stream asynchronously. |
| 8 | Home | Registry-generated six primary cards, Settings/Diagnostics, subtle version/runtime status and missing-model guidance. |
| 9 | Chat | Conversation navigation/search, streaming/Stop/regenerate, branches, models, attachments, project links, notes/summary, Markdown/code copy, sources/provenance, memory and persistence. Latest 80 messages initially rendered with load-earlier support. |
| 10 | Agent | Objective/project/workspace, plan/progress, pause/resume/cancel, task/action history, changes and validation. Decisions use existing permissions and confirmations. |
| 11 | Projects | Search/create/detail tables plus approved workspace management, IDE opening, changes, validation and checkpoint restore. |
| 12 | Knowledge | Source details, health/index state/chunk count, attach/reindex/relink/remove, retrieval inspector and indexing job controls. |
| 13 | Memory | Backend search/category filtering, add/edit/delete, suggestion review/edit/approve/reject, source details, confidence and export. |
| 14 | Settings/Diagnostics | Fourteen settings categories retain reachable generation, RAG, model, OCR, memory, permission and data controls. Grouped diagnostics and copy summary. |
| 15 | Studio | Docked Explorer/Assistant/Problems/Terminal/Output/Tests/Git, workspace-keyed tabs, dirty prompts, save-all, recent files, layout reset and persistence. |
| 16 | Editor | Offline native EditorAdapter: line numbers, lightweight syntax/current-line highlighting, diagnostics, find/replace, go-to-line, indentation, tab width, fonts, selection/cursor/read-only state. Writes retain hash/checkpoint safety. |
| 17 | Monaco | Deferred. No CDN or JavaScript editor bridge. Future provider must bundle assets locally and expose only explicit editor events. |
| 18 | Preview | Private Qt WebEngine profile for exact HTTP(S) loopback origin, restricted navigation/subresources, no downloads/host bridge and clean teardown. Existing RunSession observation contracts remain. |
| 19 | Tray | Open Home/Chat/Agent/Studio, active tasks and Exit. Does not opt users into permanent background runtime. |
| 20 | Command palette | Ctrl+K / Ctrl+Shift+P with registry navigation, New Chat and project access; Studio save/quick-open/search/terminal shortcuts. |
| 21 | Feature parity | All inventoried original interactions have mapped Qt replacements. QT_FEATURE_PARITY.md records implementation review separately from individual desktop exercise and known differences. |
| 22 | Flet removal | Removed legacy dmdo/app.py, dmdo/ui, temporary Qt launcher and declared Flet dependency after review, tests and visible smoke. Historical implementation remains in Git. Backend Flet-project detection/process safety strings remain intentionally UI-independent. |
| 23 | Files added | Detailed manifest below; application controllers, focused Qt modules, targeted tests, desktop smoke script and migration/report documents. |
| 24 | Files modified | Detailed manifest below. Backend changes are limited to integration injection, streaming/cancellation, confirmation presentation data and concrete reliability fixes. |
| 25 | Dependencies | Added PySide6 >=6.10,<6.12; removed Flet requirement. No paid/cloud dependency, model download, Docker installation, Monaco or Node toolchain. Ruff was used as a local development tool. |
| 26 | Tests added | 32 controller/Qt/preview tests. Twelve obsolete Flet-specific tests retired; backend Studio safety tests retained. |
| 27 | Full tests | 184 tests pass after cutover; compileall passes. Before retiring Flet tests, all 196 passed. |
| 28 | Qt tests | 16 targeted Qt/preview tests pass offscreen, plus 16 UI-neutral application-controller tests. Includes worker-to-GUI delivery and failed-startup shutdown. |
| 29 | Desktop smoke | 27 visible scripted checks passed with an installed Ollama model, including streaming/Stop, all windows, approved file edit/save, Run/Stop/Restart, Tests, Problems, Git, confirmations, preview, singleton reopening/shared runtime and clean shutdown. Screenshots visually inspected. This is not a claim that every dialog was manually clicked. |
| 30 | Packaging | Qt platform/plugins and WebEngine subprocess/resources audited in PACKAGING_WINDOWS.md. No production installer or clean-machine certification. |
| 31 | Git | Migration branch with preserved baseline and logical foundation/reliability/cutover/documentation commits; no history rewrite or push. See commit list below. |
| 32 | Limitations | External OCR/Docker execution, packaged clean-machine behavior and broad display/accessibility acceptance remain unverified. Native syntax highlighting is lightweight. Failed/selected-test execution stays disabled where backend lacks selectors. Legacy text-only response branches cannot reconstruct missing provenance. |
| 33 | Before 3.3 | Complete clean-machine packaging/display acceptance; retain backend and Qt regression gates; benchmark long chats/output and shutdown under load; specify a separately authorized Research interface without expanding the preview's origin policy. |

## Measurements and evidence

Final visible installed-model smoke completed in 77.97 seconds with no recorded errors. Home construction measured 1341.6 ms in that run while validation work was also running; earlier source runs measured approximately 427-473 ms. These are source-run Home construction measurements, not clean-machine cold-start guarantees.

Local ignored evidence: `.qt-smoke/final-3.2.5/results.json`, Home/Chat/Studio/Preview PNG captures, and full test logs under `.qt-smoke/`. The smoke uses temporary application data and a harmless local project. Its auto-approval helper applies only to that opt-in fixture; production authorization is unchanged.

Core repositories, v2/v3 migration logic, local-first Ollama default, permissions and portable backup format remain in place. Existing virtual environments may retain unused Flet packages; application imports and declared dependencies no longer need them. No personal data, models or credentials are included in the source change.

## Commits

- `5d7de1b` DMDO 3.2 preserve UI reliability baseline
- `e79b9b1` DMDO 3.2.5 shared application controllers and Qt runtime dependencies
- `02ec207` DMDO 3.2.5 native Qt windows Studio editor and preview foundation
- `a93ae1a` DMDO 3.2.5 Qt reliability GUI polish and desktop validation
- `47741c4` DMDO 3.2.5 launch Qt and remove legacy Flet presentation
- Documentation commit: DMDO 3.2.5 migration report and Windows packaging audit

## File manifest

Compared with the preserved pre-migration baseline (`5d7de1b`). A = added, M = modified, D = removed. The removed paths are presentation modules or obsolete presentation tests; backend services are retained.

```text
M	.gitignore
M	ARCHITECTURE_3.md
M	DEPLOYMENT_DESIGN.md
M	PACKAGING_WINDOWS.md
A	QT_FEATURE_PARITY.md
A	QT_MIGRATION.md
M	README.md
M	ROADMAP.md
M	UI_FEATURE_PARITY.md
M	dmdo/agent/confirmation_service.py
M	dmdo/agent/executor.py
M	dmdo/agent/tool_schema.py
D	dmdo/app.py
A	dmdo/application/__init__.py
A	dmdo/application/agent_controller.py
A	dmdo/application/chat_controller.py
A	dmdo/application/data_controller.py
A	dmdo/application/knowledge_controller.py
A	dmdo/application/service_container.py
A	dmdo/application/studio_controller.py
A	dmdo/application/studio_tools.py
M	dmdo/config.py
M	dmdo/services/backup_service.py
M	dmdo/services/document_service.py
M	dmdo/services/model_registry.py
M	dmdo/services/run_service.py
M	dmdo/tools/terminal.py
D	dmdo/ui/__init__.py
D	dmdo/ui/agent_mixin.py
D	dmdo/ui/app_shell.py
D	dmdo/ui/attachments_mixin.py
D	dmdo/ui/chat_mixin.py
D	dmdo/ui/components.py
D	dmdo/ui/dashboard_components.py
D	dmdo/ui/design_system.py
D	dmdo/ui/dialogs.py
D	dmdo/ui/dialogs_mixin.py
D	dmdo/ui/feature_registry.py
D	dmdo/ui/file_dialog_service.py
D	dmdo/ui/layout_mixin.py
D	dmdo/ui/navigation.py
D	dmdo/ui/navigation_mixin.py
D	dmdo/ui/notifications.py
D	dmdo/ui/pages/__init__.py
D	dmdo/ui/pages/agent_page.py
D	dmdo/ui/pages/dashboard_page.py
D	dmdo/ui/pages/diagnostics_page.py
D	dmdo/ui/pages/home_page.py
D	dmdo/ui/pages/knowledge_page.py
D	dmdo/ui/pages/memory_page.py
D	dmdo/ui/pages/projects_page.py
D	dmdo/ui/pages/settings_page.py
D	dmdo/ui/pages/studio_page.py
A	dmdo/ui_qt/__init__.py
A	dmdo/ui_qt/application.py
A	dmdo/ui_qt/commands.py
A	dmdo/ui_qt/components/__init__.py
A	dmdo/ui_qt/components/common.py
A	dmdo/ui_qt/components/markdown.py
A	dmdo/ui_qt/dialogs/__init__.py
A	dmdo/ui_qt/dialogs/confirmation.py
A	dmdo/ui_qt/dialogs/permissions.py
A	dmdo/ui_qt/dialogs/projects.py
A	dmdo/ui_qt/feature_registry.py
A	dmdo/ui_qt/icons.py
A	dmdo/ui_qt/notifications.py
A	dmdo/ui_qt/runtime.py
A	dmdo/ui_qt/studio/__init__.py
A	dmdo/ui_qt/studio/actions.py
A	dmdo/ui_qt/studio/editor_adapter.py
A	dmdo/ui_qt/studio/native_editor.py
A	dmdo/ui_qt/studio/preview.py
A	dmdo/ui_qt/studio/window.py
A	dmdo/ui_qt/themes.py
A	dmdo/ui_qt/window_manager.py
A	dmdo/ui_qt/window_state.py
A	dmdo/ui_qt/windows/__init__.py
A	dmdo/ui_qt/windows/agent.py
A	dmdo/ui_qt/windows/base.py
A	dmdo/ui_qt/windows/chat.py
A	dmdo/ui_qt/windows/data.py
A	dmdo/ui_qt/windows/home.py
A	dmdo/ui_qt/windows/settings.py
M	dmdo/utils/files.py
M	main.py
M	pyproject.toml
M	requirements.txt
A	scripts/qt_desktop_smoke.py
D	tests/test_app.py
A	tests/test_application_controllers.py
D	tests/test_dialogs.py
A	tests/test_qt_preview.py
A	tests/test_qt_ui.py
M	tests/test_studio_run_ui.py
M	tests/test_ui_regressions.py
A	QT_RELEASE_REPORT.md
```
