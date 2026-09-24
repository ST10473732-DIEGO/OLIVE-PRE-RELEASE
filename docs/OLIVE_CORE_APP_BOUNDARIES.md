# OLIVE Core and app boundaries

This repair preserves V2 and prepares existing in-process boundaries; it does
not implement an OS, extra services or separately privileged agents.

Core owns conversation orchestration, model routing/residency, typed tool
registry/executor, task grants, cancellation, shared identity and Connect.
`ToolDefinition` names are stable capability IDs; labels and model prose are
not authority. App controllers retain their repositories, records and UI state.
The private local bridge is the authenticated front door; remote Connect keeps
its separate C1–C8 contracts.

Chat requests answers or typed app capabilities. Studio retains workspace,
open-document, run/test and toolchain state. GO retains isolated remote content;
it cannot call the trusted Chat clipboard route. Mail, Files, Tasks, Calendar
and Reminders retain their existing stores/controllers. Selected files are
references, not permission to copy an unrelated project into model context.

Owner Mode changes the executor's ordinary local Ask decision for a finite
explicit task; it does not replace the registry, permission checks or app trust
requirements. The file-tool/executor contract is exercised by real owned-file
move/edit tests, explicit Deny, changed target and remote-context tests. Studio
uses detected commands and approved workspace references. Native desktop tasks
retain their independent helper lease and Stop path. This demonstrates a policy/
app boundary, not certification that every app can already run standalone.

A future independently launched app should connect to the one authenticated
Core owner and pass typed scoped references. It must not start a duplicate model
server, copy shared databases, import owner task authority from remote requests,
or gain root. Any future privileged capability service needs typed operations,
OS-native authorization and a private authenticated channel; none is installed
by this milestone.

## Navigation/control inventory

| Before this repair | Current change |
|---|---|
| Existing Chat/Home Ask routes | Retained as the one answer/action entry; code answers no longer require Studio setup |
| Chat public preset selector | Retained; internal candidate profiles do not add public modes |
| Message/block Copy | Native trusted clipboard route, exact content and truthful success/error |
| Chat Stop and tray Stop | Retained; owner grant cancellation joins existing cancellation |
| Settings → Privacy & Security → Permissions | Adds the requested Owner Mode setting; remote controls remain |
| Studio, GO, Mail, Devices and other workspaces | Retained with saved routes/data; no navigation reorganization |
| Advanced desktop diagnostics in Settings | Retained; no execution prerequisite or new ritual |

No control was removed merely because it resembled another control. A later
separate-app design proposal can simplify navigation with usage evidence; this
repair makes no broad layout, typography, icon or colour changes. Historical
freeze manifests remain immutable; the repair scope ledger records actual edits.
