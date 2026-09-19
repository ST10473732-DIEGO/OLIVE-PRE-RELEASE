# Action parity inventory

Existing implementation remains callable throughout M1. Location after redesign
is pending until tested; opening a page alone never proves parity.

| Existing action | Source | M1 location / evidence |
| --- | --- | --- |
| Chat stream, stop, regenerate | windows/chat.py; chat_controller.py | New Chat composer; shared existing methods; legacy smoke retained |
| Branch / copy / code copy / provenance | components/markdown.py; windows/chat.py | New message Copy/Sources/Alternative/Code controls; per-action new-shell audit pending |
| Conversation search/select/new/rename/delete/export/notes | windows/chat.py | New conversation list and Conversation menu; live select/retention checked |
| Model selection and project assignment | windows/chat.py | New Chat header model control / Conversation > Assign project |
| File/image attachments, Knowledge attachment, image removal | windows/chat.py | Attach menu and readable attachment chips; full new-shell action audit pending |
| Draft save/restore and reviewed send/edit/cancel | windows/chat.py; pending_draft.py | Same controller and confirmation path |
| Agent new task/history/open/pause/resume/cancel | windows/agent.py; agent_controller.py | Existing Agent retained until M2 |
| Research depth/start/history/cancel | windows/research.py | Existing Research retained until M2 |
| Research source/provenance/download/save | windows/research.py; research_data.py | Existing Research retained until M2 |
| Projects create/edit/archive/open/link | windows/data.py; data_controller.py | Existing Projects retained until M2 |
| Knowledge add/search/source inspection | windows/data.py; knowledge_controller.py | Existing Knowledge retained until M2 |
| Knowledge re-index/relink/remove/maintenance/web learning | windows/data.py; dialogs/web_knowledge.py | Existing Knowledge retained until M2 |
| Memory search/add/edit/delete/suggestion approval | windows/data.py; notifications.py | Existing Memory/notifications retained |
| Studio open workspace/file/recent/quick open | studio/window.py; studio/actions.py | Retained real native Studio |
| Save/save all/hash conflicts/dirty close | studio/window.py | Retained real native Studio |
| Cursor/selection/tabs/find/replace/indent/highlight | studio/native_editor.py | Retained real native editor |
| Run/stop/restart/output/preview | studio/actions.py; studio/preview.py | Retained authorized RunSession |
| Tests/problems and output back to agent | studio/actions.py; studio_tools.py | Retained bottom docks |
| Terminal input and bounded output | studio/window.py | Retained permission-bearing Terminal |
| Git status/diff/staged diff/log/stage/commit/branches | studio/actions.py | Retained Git dock |
| Diff review/checkpoint/rollback/concurrent modification | studio/actions.py; studio_controller.py | Retained existing services |
| Desktop inspect/plan/run/application selection | windows/desktop.py; desktop_workspace.py | Existing Desktop retained until M2 |
| Emergency Stop/focus loss/takeover/uncertain result | desktop_controller.py; gateway.py | Global Stop remains available |
| UIA/vision/browser/media/consequence details | dialogs; desktop_workspace.py | Existing details retained until M2 |
| Permission edit and consequence confirmation | dialogs/permissions.py; confirmation.py | Existing authoritative dialogs |
| Settings validation/model routing/benchmarks | windows/settings.py; dialogs/models.py | Existing Settings until M2 |
| Diagnostics/copy/export | windows/settings.py | Existing Diagnostics until M2 |
| Backup/export/restore/migration | data_controller.py; backup_service.py | Existing policy and data paths retained |
| Palette, tray, navigation/history/pop-outs | commands.py; window_manager.py | Narrow shell integration; legacy retained |

Native Contacts/Calendar/Tasks/Mail have no shipped pages at baseline. They will
be added after M1 approval, not displayed as functioning placeholder workspaces.
