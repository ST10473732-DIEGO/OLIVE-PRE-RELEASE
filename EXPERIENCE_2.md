# Experience 2.0

## Current authority: DMDO 3.5.1

The Electron master brief supersedes Qt/QML as the final presentation. The earlier Qt prototype below remains a fallback and historical checkpoint. [Electron M1 evidence and approval status](docs/releases/3.5.1/ACCEPTANCE.md). Full feature parity and native Personal Core remain mandatory.

M0 is verified; the M1 working prototype is ready for review and not user approved. Later workspace
redesign and Personal Core interfaces must wait at the mandatory M1 visual gate.

One QApplication / QMainWindow hosts QQuickWidget Welcome/Home/navigation plus
cached QWidget workspaces. Studio retains its real docked native editor and
existing RunSession/permission path. The existing BackendBridge owns one worker
thread and asyncio loop; QML receives narrow GUI-thread view models only.

The initial spike supports Qt's Windows Direct3D11 backend including local
WebEngine coexistence. QQuickWidget has extra offscreen-render and nonthreaded
render-loop costs; actual measurements are recorded in the release ledger.
[Qt's documented QQuickWidget limitations](https://doc.qt.io/qt-6/qquickwidget.html).

Legacy presentation stays available during migration. Welcome is an introduction,
not authentication. Optional AI/network availability does not lock local navigation.
No new native Personal Core implementation is claimed before M3/M4.

The default development entry selects Midnight; `DMDO_PRESENTATION=legacy`
selects the preserved presentation. Cached pages retain backend/service ownership.
Home dispatches only through `interaction.submit`; no QML command interpreter or
generic service bridge exists. Request identities block duplicate submissions,
ignore stale callbacks and retain Stop while model streaming continues.

Chat uses content-sized safe Markdown and retains conversation menus, branches,
regeneration, attachments, projects and provenance. Unsent composer text has an
additive `Chat.draft` field, saved behind ChatController; old records default to an
empty draft. Draft saves do not create messages or approve pending actions. Exit
waits for in-flight draft saves rather than silently dropping the text.

The Core observes agent/research/chat/desktop/indexing events and authoritative
approval requests. Appearance stores light/dark, Reduced Motion and startup
Welcome preferences in the noncritical UI state store. All Spaces searches and
pins shipped features. Personal Core pages have not been added as placeholders.

See `docs/releases/3.5/M1_REVIEW.md` for evidence and outstanding polish. The M1
gate is a request for user review, not assistant approval of the release.
