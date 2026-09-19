# OLIVE Windows Forms designer

Studio → New project → C# → Windows Forms visual application creates a real
Windows desktop project with the installed SDK. Ordinary console, Python and
ASP.NET projects remain separate templates. The initial adapter requires Windows
and an installed Windows Forms template; it does not download an SDK or runtime.

Design form opens Design / Code / Preview. Drag controls from Toolbox, select
and move them, resize the corner, edit Properties, or Shift-select controls for
alignment. Snapping uses an 8-pixel grid. Undo/redo retains 100 design snapshots.
Form and control names, text, dimensions, hierarchy, docking, ComboBox items,
CheckBox state and event bindings have bounded validated fields. Panel,
FlowLayoutPanel and a single-column TableLayoutPanel are supported. The canvas
represents design bounds; native docking/flow/table arrangement is applied by
Windows Forms when the application runs. This is not Visual Studio parity.

Enter an event-handler name and choose Edit event code to create/open its C#
method in Monaco. Build and run native app uses the existing approved Studio run
service. Preview itself never loads assemblies or executes project constructors.

`.olive/designer.json` and `MainForm.Designer.cs` are owned generated layout.
`MainForm.cs` and `Events/*.cs` belong to the user. Saving never rewrites or deletes
existing event files. Renamed/unbound event files remain available for manual
cleanup. Unknown hand-written forms are code-only. The safely recognized subset
is exactly the deterministic generated format, not arbitrary C# parsing.

Saves bind the loaded layout/code revision, honor file-scoped Deny and dirty Code
buffers, use existing checkpoints, and recheck hashes before each file write.
External layout edits block Design save and expose both versions for comparison.
A partial multi-file failure can require reconciliation using its checkpoint;
the application does not overwrite externally changed code to force a rollback.
Unsaved layout drafts are retained in the current desktop profile's local storage,
scoped by workspace ID. A changed disk revision blocks restoration from overwriting
newer content. Discard design changes explicitly reloads disk content.

Actual acceptance: `desktop/tests/e2e/winforms-designer.spec.ts` dragged five
controls, changed properties, moved/resized/aligned controls, used undo/redo,
entered real C# event code in Monaco, saved/reopened, built and launched App.exe.
The exact run process was verified before UIA entered calculator inputs: 2+3=5,
8/2=4, 9/0=Cannot divide by zero, then 2*3=6. External generated-code divergence
blocked saving and preserved event bytes. The latest expanded run passed in
27.3 seconds. Native and normal/smaller-window captures were inspected.

`tests/test_winforms_designer.py` additionally compiles all eight control types,
tests revision/dirty-buffer/Deny guards, preserves user event code and rejects
unknown properties, path-escaping handlers and cyclic hierarchy.

`scripts/studio_service_acceptance.py` exercises three actual independent Studio
workspaces: C# console output, Python unittest, and an ASP.NET endpoint returning
five forecast records over owned loopback HTTP. A dirty console buffer survives
creation of the other projects. Fixture run settings disable Windows Event Log
writes and use a dynamic loopback port; all required SDK assets are installed.
No third-party packages are downloaded for these templates. Test-framework
templates may still require package restore and state that requirement.

Official implementation references: [Windows Forms](https://learn.microsoft.com/en-us/dotnet/desktop/winforms/),
[SDK templates](https://learn.microsoft.com/en-us/dotnet/core/tools/dotnet-new-sdk-templates).
No proprietary Visual Studio designer component is used.
