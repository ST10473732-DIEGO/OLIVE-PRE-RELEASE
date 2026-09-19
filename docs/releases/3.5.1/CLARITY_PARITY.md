# Clarity redesign — action-level parity ledger

Every user action that existed before this redesign, where it lives now, and how
it is verified. "Kept" means the same handler and `window.olive`/`call` method;
only the presentation moved.

## Shell and navigation

| Action | Now reached by | Status |
| --- | --- | --- |
| Welcome → Enter OLIVE → Home; returning Home never reopens Welcome | Unchanged flow, redesigned composition | Kept |
| Show Welcome on startup preference | Activity sheet (`localStorage.skipWelcome`) | Kept |
| Open any feature (Home, Chat, Studio, Agent, Research, Desktop Control, Projects, Knowledge, Memory, Mail, Calendar, Tasks, Reminders, Contacts, Profile, Settings) | Labelled navigation row **and** Home launcher tile **and** palette | Kept, more discoverable |
| Diagnostics | Navigation → Settings → Diagnostics, palette "Open Diagnostics" | Kept (moved inside Settings by design) |
| Developer Mode adds a Diagnostics shortcut to navigation | `navigationRows(developer)` in the same registry | Kept |
| Connections | Navigation/launcher row opens the existing dialog | Kept |
| Collapse/expand navigation (persisted) | `nav-compact-toggle`, `localStorage.navigationCompact` | Kept |
| Navigation on narrow windows | Same pane as a dismissable overlay (Ctrl+Shift+O, Home button) | New |
| Activity centre, state text, approval count | Navigation identity button (`.activity-button`) | Kept |
| Cancel request, Stop desktop control, Ctrl+Alt+Escape | Activity sheet | Kept |
| Clear context | Activity sheet | Kept |
| Reduced motion, Core animation, theme | Activity sheet | Kept |
| Command palette (Ctrl+Shift+P) | "Find anything" row; entries now come from the feature registry | Kept, renamed |
| New conversation / calendar event / task / mail draft / open folder | Palette "Start" group | Kept |
| New code project | Palette + Studio header + switcher + Ctrl+Alt+N | New |
| New OLIVE Project (grouping) | Palette "New OLIVE Project" → Projects | Kept, disambiguated |
| Approval sheet with fingerprint binding | Unchanged | Kept |
| Error toast, interface scale | Unchanged | Kept |

## Home

The universal composer (Enter submits and opens Chat, Shift+Enter newline, busy →
Cancel) is kept. Pinned space cards, "Open now" tiles, the Right now panel and
the separate All Spaces page are **replaced** by one launcher plus one Continue
list; every destination they offered is still reachable, and recent work opens
the same `chat.select` / Studio workspace handlers. Native Today is kept as a
restrained module.

## Studio

| Action | Status |
| --- | --- |
| Open workspace (native picker), recent workspaces | Kept; opening never replaces another open workspace |
| Switch workspace | New readable selector listing open workspaces and other approved folders |
| Close a workspace | New; names unsaved files and running work, offers Save / Discard / Cancel |
| New project (language, template, name, location, options) | New wizard; creates real files and opens a separate workspace |
| Add project to this solution / add existing project / startup project | Kept, relabelled so they cannot be confused with New project |
| Save, Save all, Compare, rebase/conflict checks, discard buffer | Kept |
| Build / Rebuild / Clean / Restore, Run, Start Debugging, Stop | Kept; "Debug build" configuration and "Start Debugging" no longer share a label |
| Test (reviewed validation) and the structured Tests panel | Kept |
| Terminal, Problems, Output, Git, Debug, Web, References | Kept; one tool-tab strip in the status bar, the dock shows only the open panel's title |
| Monaco language features, DAP debugging, ConPTY terminals, local preview, packages, checkpoints, workspace tools | Kept |
| Ask OLIVE assistant (on demand, pinnable) | Kept |
| Reopen the workspace that was showing after a restart | New; nothing that was *running* in it resumes |

## Other features

Chat, Agent, Research, Mail, Calendar, Tasks, Contacts, Reminders, Profile,
Projects, Knowledge, Memory and Settings keep their existing pages, handlers and
services; only their entry point changed from the tab shelf to navigation.
Settings gains `diagnosticsRequest` in place of `initialCategory`; no parallel
configuration system was introduced.
