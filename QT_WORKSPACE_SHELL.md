# OLIVE 3.4 workspace shell

The default desktop is one `MainWindow` with a persistent navigation rail and
`QStackedWidget`. Home is always the initial workspace. Heavy features are created
on first navigation and retained for the process lifetime.

## Ownership and navigation

`NavigationController` owns bounded Back/Forward history and an optional project ID
with a context-change signal. Repeated navigation to the current page adds no history.
Project selection remains feature-specific today; the global context is a foundation,
not an automatic reassignment of existing chats, workspaces or tasks.

`WindowManager` owns the shell, cached workspaces, confirmations, tray and explicit
pop-outs. `open(feature_id)` routes navigation. Its legacy `windows` mapping aliases
`pages`; those entries are embedded workspaces, not top-level windows.

Existing feature `QMainWindow` classes are embedded as Qt child widgets. This retains
Studio's native docking, toolbars, editor ownership and save safety without rewriting
backend or IDE functionality. Pages refresh on first construction and receive backend
events while inactive. Navigation does not reload conversations or reset selections.
Explicit refresh controls continue to work.

The shell supplies Ctrl+1–5, Alt+Left/Right and the command palette. Local editor
shortcuts remain on feature widgets. The rail collapses to icons with accessible
names and tooltips. STOP CONTROL is available in the shared toolbar while enabled.

## Secondary windows and shutdown

Chat, Studio, Research and Desktop Control can explicitly pop out. The same widget
is reparented into a secondary host; no duplicate backend or editor is constructed.
Closing the pop-out reattaches it with draft/session state intact. Selecting that
feature in main navigation also returns it to the shell. This moves the whole
workspace; concurrent per-conversation Chat views are not implemented.

Confirmation dialogs, file pickers, screenshot viewers, Studio previews and launched
applications retain their separate-window behavior. Closing the main window checks
cached Studio documents, including inactive/popped-out workspaces, before invoking
the existing shared graceful shutdown.

## Persistence and verification

The shell uses a new `main` entry in the existing non-critical UI state file. Old
feature dock/document metadata remains readable. Old per-feature geometry does not
resize the main window. Invalid state falls back safely. Page instances retain drafts,
cursors, tabs and selected sources while navigating; no core-data schema changes.

Offline Qt tests cover the primary host, lazy creation, history branching, dirty editor,
cursor/dock retention, chat drafts, background output, pop-out return and global stop.
The live smoke harness verifies Home-card/tray navigation, Studio/Research state,
pop-outs, shared services, streaming, Run/Stop/Restart, preview and clean shutdown.
Shell acceptance does not imply the broader universal-control release is complete.

Validation on this source environment: 331 automated tests and 40 visible Qt smoke
checks passed; Home construction measured 488 ms in one fixture run. This is not a
clean-machine packaging or cold-start certification.


OLIVE was formerly named DMDO. See [the rebrand compatibility map](docs/OLIVE_REBRAND.md) for legacy profile, import, launcher and security identities. Historical evidence retains its original name.
