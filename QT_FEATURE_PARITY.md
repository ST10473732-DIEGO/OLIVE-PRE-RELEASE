# OLIVE 3.2.5 feature parity and desktop verification

The inventory below was created before migration. Replacement paths are relative to `olive/ui_qt/`, except `application/` paths, which are relative to `olive/`.

Evidence labels distinguish visible desktop smoke from implementation review. A window opening does not establish that every action in it was manually clicked. Controller and backend tests additionally cover persistence, permission denial, restore safety, attachments, memory suggestions, settings validation and indexing recovery. No model download was performed.

| Existing feature / interaction | Qt replacement | Implementation | Desktop test | Known differences |
|---|---|---|---|---|
| Home: Feature cards | `windows/home.py + feature_registry.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Home: primary and secondary navigation | `windows/home.py + feature_registry.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Home: runtime status | `windows/home.py + feature_registry.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Home: Home startup | `windows/home.py + feature_registry.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Chat: New | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Chat: selection | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Chat: search | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Chat: rename | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Chat: delete | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Chat: model selection | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Chat: defaults | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Chat: streaming | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Chat: stop | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Chat: regenerate | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Chat: response branches | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Not individually exercised | Legacy text-only branches clear unavailable provenance instead of retaining stale sources |
| Chat: project association | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Chat: notes | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Chat: summary | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Chat: export | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Chat: Markdown | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Chat: copy | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Chat: sources | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Chat: provenance | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Chat: memory indicators | `windows/chat.py + application/chat_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Attachments: Native picker | `windows/chat.py + application/knowledge_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Attachments: images with vision gate | `windows/chat.py + application/knowledge_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Attachments: temporary documents | `windows/chat.py + application/knowledge_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Attachments: permanent knowledge | `windows/chat.py + application/knowledge_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Attachments: pending image removal | `windows/chat.py + application/knowledge_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Agent: Objective | `windows/agent.py + application/agent_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Agent: workspace/project | `windows/agent.py + application/agent_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Agent: plan | `windows/agent.py + application/agent_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Agent: task state | `windows/agent.py + application/agent_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Agent: tool activity | `windows/agent.py + application/agent_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Agent: cancellation | `windows/agent.py + application/agent_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Agent: task history | `windows/agent.py + application/agent_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Agent: action history | `windows/agent.py + application/agent_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Agent: changes | `windows/agent.py + application/agent_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Agent: validation | `windows/agent.py + application/agent_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Agent: confirmations | `windows/agent.py + application/agent_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Agent: remembered app approvals | `windows/agent.py + application/agent_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Projects / Workspaces: List | `windows/data.py + dialogs/projects.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Projects / Workspaces: create | `windows/data.py + dialogs/projects.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Projects / Workspaces: associate chat | `windows/data.py + dialogs/projects.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Projects / Workspaces: approved roots | `windows/data.py + dialogs/projects.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Projects / Workspaces: add workspace | `windows/data.py + dialogs/projects.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Projects / Workspaces: open IDE | `windows/data.py + dialogs/projects.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Projects / Workspaces: changes | `windows/data.py + dialogs/projects.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Projects / Workspaces: run tests | `windows/data.py + dialogs/projects.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Projects / Workspaces: checkpoint undo | `windows/data.py + dialogs/projects.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Knowledge: Document list | `windows/data.py + application/knowledge_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Knowledge: metadata | `windows/data.py + application/knowledge_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Knowledge: chunk count | `windows/data.py + application/knowledge_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Knowledge: semantic/lexical mode | `windows/data.py + application/knowledge_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Knowledge: health | `windows/data.py + application/knowledge_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Knowledge: reindex | `windows/data.py + application/knowledge_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Knowledge: relink | `windows/data.py + application/knowledge_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Knowledge: remove | `windows/data.py + application/knowledge_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Knowledge: retrieval inspector | `windows/data.py + application/knowledge_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Indexing: Jobs | `windows/data.py jobs dialog + IndexingScheduler` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Indexing: progress | `windows/data.py jobs dialog + IndexingScheduler` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Indexing: pause | `windows/data.py jobs dialog + IndexingScheduler` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Indexing: resume | `windows/data.py jobs dialog + IndexingScheduler` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Indexing: retry | `windows/data.py jobs dialog + IndexingScheduler` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Indexing: cancel | `windows/data.py jobs dialog + IndexingScheduler` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Indexing: shutdown recovery | `windows/data.py jobs dialog + IndexingScheduler` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Indexing: lexical upgrades | `windows/data.py jobs dialog + IndexingScheduler` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Memory: Search | `windows/data.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Memory: category filter | `windows/data.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Memory: add | `windows/data.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Memory: edit | `windows/data.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Memory: delete | `windows/data.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Memory: suggestion review/edit/approve/reject | `windows/data.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Memory: structured local proposals | `windows/data.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Memory: source | `windows/data.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Memory: date | `windows/data.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Memory: confidence | `windows/data.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Settings: System prompt | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Settings: presets | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Settings: temperature | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Settings: top-p | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Settings: max tokens | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Settings: history | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Settings: RAG chunks | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Settings: per-model defaults/alias | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Settings: embedding model | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Settings: lexical/semantic weights | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Settings: minimum score | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Settings: reset RAG | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Settings: workers | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Settings: Tesseract | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Configuration retained; external OCR executable not installed by migration |
| Settings: automatic suggestions | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Settings: model extraction | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Settings: auto approval | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Settings: themes | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Permissions: Global allow/ask/deny | `dialogs/permissions.py + PermissionService` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Permissions: path scopes | `dialogs/permissions.py + PermissionService` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Permissions: remembered application approvals | `dialogs/permissions.py + PermissionService` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Permissions: clear approvals | `dialogs/permissions.py + PermissionService` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Permissions: most-specific backend precedence | `dialogs/permissions.py + PermissionService` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Diagnostics: Application | `windows/settings.py DiagnosticsWindow` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Diagnostics: Ollama | `windows/settings.py DiagnosticsWindow` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Diagnostics: models | `windows/settings.py DiagnosticsWindow` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Diagnostics: RAG | `windows/settings.py DiagnosticsWindow` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Diagnostics: OCR | `windows/settings.py DiagnosticsWindow` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Diagnostics: jobs | `windows/settings.py DiagnosticsWindow` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Diagnostics: schemas | `windows/settings.py DiagnosticsWindow` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Diagnostics: integrity | `windows/settings.py DiagnosticsWindow` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Diagnostics: storage | `windows/settings.py DiagnosticsWindow` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Diagnostics: maintenance | `windows/settings.py DiagnosticsWindow` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Diagnostics: Docker availability | `windows/settings.py DiagnosticsWindow` | Implemented; reviewed | Not individually exercised | Availability checked; Docker installation/container execution not exercised |
| Backup / Data: Create backup | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Backup / Data: restore with safety backup/rollback | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Backup / Data: export chat JSON/Markdown | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Backup / Data: export memories | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Backup / Data: maintenance | `windows/settings.py + application/data_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Studio: Workspace selector | `studio/window.py + studio/actions.py + application/studio_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Studio: explorer | `studio/window.py + studio/actions.py + application/studio_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Studio: file tabs | `studio/window.py + studio/actions.py + application/studio_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Studio: drafts | `studio/window.py + studio/actions.py + application/studio_controller.py` | Implemented; reviewed | Not individually exercised | Workspace-keyed tabs retain in-memory drafts; explicit save/discard on close |
| Studio: hash-safe save | `studio/window.py + studio/actions.py + application/studio_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Studio: line numbers | `studio/window.py + studio/actions.py + application/studio_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Studio: find/replace | `studio/window.py + studio/actions.py + application/studio_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Studio: go to line | `studio/window.py + studio/actions.py + application/studio_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Studio: syntax preview | `studio/window.py + studio/actions.py + application/studio_controller.py` | Implemented; reviewed | Not individually exercised | Offline native syntax highlighting; Monaco deferred |
| Studio: search | `studio/window.py + studio/actions.py + application/studio_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Studio: assistant | `studio/window.py + studio/actions.py + application/studio_controller.py` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Studio: run/stop/restart | `studio/window.py + studio/actions.py + application/studio_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Studio: Problems | `studio/window.py + studio/actions.py + application/studio_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Studio: Output | `studio/window.py + studio/actions.py + application/studio_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Studio: Tests | `studio/window.py + studio/actions.py + application/studio_controller.py` | Implemented; reviewed | Passed visible smoke | Whole-suite execution; selected/failed-only controls disabled because backend lacks selectors |
| Studio: Git branch | `studio/window.py + studio/actions.py + application/studio_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Studio: local web opening | `studio/window.py + studio/actions.py + application/studio_controller.py` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Qt additions: Multiwindow singletons | `WindowManager + runtime + studio + themes` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Qt additions: dock layout | `WindowManager + runtime + studio + themes` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Qt additions: editor adapter | `WindowManager + runtime + studio + themes` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Qt additions: tray | `WindowManager + runtime + studio + themes` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Qt additions: command palette | `WindowManager + runtime + studio + themes` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Qt additions: shortcuts | `WindowManager + runtime + studio + themes` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Qt additions: native dialogs | `WindowManager + runtime + studio + themes` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Qt additions: light/dark | `WindowManager + runtime + studio + themes` | Implemented; reviewed | Not individually exercised | Existing dark themes plus Light; global palette updates |
| Qt additions: layout recovery | `WindowManager + runtime + studio + themes` | Implemented; reviewed | Not individually exercised | Same backend service; native presentation |
| Qt additions: safe shutdown | `WindowManager + runtime + studio + themes` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |
| Qt additions: local preview | `WindowManager + runtime + studio + themes` | Implemented; reviewed | Passed visible smoke | Same backend service; native presentation |

## Validation checkpoint

- Original stable baseline: 155 tests; preserved pre-migration reliability fixes brought the audited baseline to 164 passing tests.
- Pre-cutover automated checkpoint: 196 tests passed. After removing 12 obsolete Flet-only tests, 184 tests pass; the remaining backend safety tests are retained and Qt replacement coverage lives in the targeted suites. Compileall and pip dependency checks passed.
- Visible isolated desktop smoke passed Home and all eight feature windows, file open/edit/hash-safe save, Run/Stop/Restart, structured Tests, Problems navigation, Git, Agent persistence, Chat streaming/cancellation, confirmations, singleton reopening, shared services, tray presence and clean shutdown.
- A separate visible run used an already-installed Ollama model and passed streaming and cancellation. No model was downloaded.
- Screenshots and machine-readable results are local ignored artifacts under `.qt-smoke/`.
- This is not a clean-machine packaged-build certification. External Docker execution, OCR accuracy, OS desktop-application observation and every individual data-management dialog still require environment-specific acceptance testing.
- Following implementation parity review, automated validation and visible desktop smoke, the default entry point is now Qt (`main.py`). Obsolete Flet UI modules and its declared dependency have been removed; the old implementation remains in Git history. External-component and packaged-build acceptance limits above remain open.


OLIVE was formerly named DMDO. See [the rebrand compatibility map](docs/OLIVE_REBRAND.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
