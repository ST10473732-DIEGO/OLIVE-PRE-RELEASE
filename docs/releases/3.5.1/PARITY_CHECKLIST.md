# Experience refresh — action-level parity checklist

Written before replacing any component. Each item names a user action, the
service it reaches, and how it is verified after the refresh. "Kept" means the
same React handler and `window.olive`/`call` method are used; only presentation
changed.

## Shell

| Action | Service / state | Status |
| --- | --- | --- |
| Welcome → Enter OLIVE (click or Enter key) → Home; returning Home never reopens Welcome | local `entered` state | Kept |
| Show Welcome on startup preference | `localStorage.skipWelcome` | Kept (activity centre) |
| Navigate to every space: Home, Chat, Agent, Studio, Research, Desktop Control, Projects, Knowledge, Memory, Mail, Calendar, Contacts, Tasks, Reminders, Profile, Settings, Diagnostics, All Spaces | `navigate()` route state; visited workspaces stay mounted (`hidden`) | Kept; all spaces now in the spine |
| Expand/collapse navigation (persisted) | `localStorage.expandedNavigation` | Kept (`aria-expanded`, names) |
| Open activity centre from the Core; state text and approval count | `runtime.activity`, `.activity-button` | Kept |
| Cancel current request; Stop desktop control; Ctrl+Alt+Escape | `interaction.cancel`, `window.olive.stopControl` | Kept |
| Clear context | `context.clear` | Kept |
| Reduced motion, Core animation preference, theme | localStorage + `data-*` on `<html>` | Kept |
| Command palette (Ctrl+Shift+P, button): New Chat, New Project, New Calendar Event, New Personal Task, Compose Mail, Open Workspace, Open Home, Open Diagnostics, Open <space> | `chat.new`, `mail.save_draft`, `window.olive.openWorkspace`, navigation | Kept |
| Approval sheet: summary (target, recipient, content, attachments, operation, consequence), Approve / Cancel, closing = cancel, fingerprint bound | `approval.respond` with fingerprint | Kept |
| Connections dialog | `Connections` component | Kept |
| Error toast with dismiss | `role="alert"` | Kept |
| Interface scale | `window.olive.setInterfaceScale` | Kept |

## Home

Universal composer (Enter submits and opens Chat; Shift+Enter newline; busy → Cancel), context chip → activity centre, pinned space cards, recent conversations/workspaces (`chat.select`, workspace → Studio), Native Today region (`personal.today`) with record handoffs, Reminders access. Kept.

## Chat

Conversation list + search (`chat.search`), new chat (`chat.new`), select (`chat.select`), model select (`chat.model`; now shows a labelled placeholder when no model is installed), conversation options (title, notes, project, delete), attach files / drop files / add to permanent Knowledge (`window.olive.fileAction`, `attachFiles`), messages with Markdown/code/tables, source chips → source sheet, copy, regenerate (`chat.regenerate`), response branches (`chat.branch`), streaming partial text, Stop response (`interaction.cancel`), draft retention (`chat.draft`), attachment/image removal (`knowledge.remove`, `chat.remove_image`), pending action preview with Edit/Cancel semantics, native proposals. Kept.

## Agent

Objective entry (`Agent objective`), workspace/project selects, Start objective, Cancel current request, task history + search + paging (`agent.history`/`agent.get`), Pause after current tool / Resume task / Cancel Agent task (`agent.pause`, `agent.resume`, `agent.cancel`), timeline with step results, validation status, evidence, changed files, failure details, developer details, tool audit (`agent.actions`), record handoff from Projects. Kept.

## Studio

Open Workspace, recent workspaces, New Project (starters incl. C#/Java), Explorer tree with keyboard navigation, New File, Refresh files, real Monaco tabs (retained buffers, dirty markers, close with unsaved sheet: Keep / Discard / Save and close), Save (Ctrl+S, hash checked), Save all (Ctrl+Shift+S), Compare / reconcile (`studio.compare`, `studio.rebase`), Test / Review tests (`studio.validate`), Run / Stop / Restart (`studio.run`, `studio.stop`, `studio.restart`, cancel validation/command), output channels select, Git diff, TaskResult states, Problems/Tests/Git/Find/Command/Checkpoints tools, local preview, packages, open installed IDE, assistant (`interaction.studio`), Files/Assistant compact toggles, resizable explorer/assistant/output persisted (`studioPanelLayout`), save-status footer. Kept.

## Research

Question entry, project + depth, Start research, progress/pause/resume/cancel, findings/report, sources and evidence inspector, follow-ups, web library (learn website, review scope, save). Kept (page header and panel styling only).

## Desktop Control

Objective entry, Submit objective, Stop Control (independent of animation/model), Control permissions → Settings, current application/action/verification state, launch target, application/browser/visual tools, Developer Details disclosure. Kept.

## Projects / Knowledge / Memory

Create/select/edit projects, relationships navigation (`Project relationships`), knowledge search/sources/indexing/upgrade lexical indexes/retrieval inspector, memory search/save/edit/delete. Kept.

## Personal Core

Profile save/avatar; Contacts list/search/add/edit/delete/merge/import/export; Calendar Month/Week/Agenda/Day, previous/today/next, calendars, New Event editor, import/export ICS/CSV; Tasks list/views/new/complete/reopen/schedule; Reminders new/snooze/dismiss/history with record handoff. Kept.

## Mail

Folders with counts, connection scope, local folders, search + filters, list paging, message detail with safe plain/formatted (isolated iframe) views, read/star/archive/trash, reply/reply-all/forward/duplicate, Compose with autosave/manual save/conflict comparison, recipients picker, attachments, Review submission (approval bound to draft/connection revision), outbox outcomes (accepted / partially accepted / uncertain / cancelled), Import EML review, export, project references, Draft from Calendar, Mail-to-Calendar/Tasks proposals, Mail connections settings (test never sends; credentials masked). Kept.

## Settings

Search, categories, Appearance (size, theme, reduced motion, Core animation, developer mode, workspace layout reset), Chat/Models/Permissions/Connections/Memory/Knowledge/Research/Desktop Control/OCR/Studio/Backup & Data/Diagnostics, Save settings. Kept.

## Security-critical UX

Approval previews keep target/recipient/content/attachments/operation/consequence; changing an action invalidates the fingerprinted approval (server-side, unchanged); draft vs sent, local vs remote, accepted vs delivered, completed vs partial/blocked, paused vs pausing remain separately labelled; Stop controls are plain buttons wired to `window.olive.stopControl` / `interaction.cancel`; untrusted mail HTML stays in the sandboxed iframe; no new preload/IPC surface.
