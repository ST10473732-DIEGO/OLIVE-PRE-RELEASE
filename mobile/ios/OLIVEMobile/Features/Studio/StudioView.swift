import SwiftUI

struct StudioView: View {
    @Environment(AppState.self) private var state
    @State private var discard = false
    var body: some View {
        @Bindable var model = state.studio
        List {
            Section("Shared workspaces") {
                Button("Refresh workspaces") { Task { await model.refresh() } }.disabled(!model.available || model.busy || model.running)
                ForEach(model.workspaces, id: \.digest) { item in
                    Button(item["display_name"].string ?? "Workspace") { Task { await model.open(item) } }
                }
            }
            if let workspace = model.workspace {
                Section(workspace["display_name"].string ?? "Workspace") {
                    ForEach(["view", "edit", "build", "test", "run"], id: \.self) { capability in
                        let decision = workspace["permissions"]["studio." + capability].string ?? ""
                        Text(capability.capitalized + " · " + (["deny": "Off", "ask": "Ask on computer", "allow": "Allow"][decision] ?? "Unknown")).font(.caption)
                    }
                    ForEach(model.entries, id: \.digest) { item in
                        if item["directory"].boolean != true {
                            Button(item["path"].string ?? "File") { Task { await model.read(item["path"].string ?? "") } }
                        }
                    }
                }
                if let path = model.filePath {
                    Section(path) {
                        TextEditor(text: $model.text).font(.system(.body, design: .monospaced)).frame(minHeight: 260)
                            .autocorrectionDisabled().textInputAutocapitalization(.never).accessibilityIdentifier("studio.editor")
                        if let remote = model.remoteText { DisclosureGroup("Current computer version") { Text(remote).font(.system(.caption, design: .monospaced)).textSelection(.enabled) } }
                        if model.dirty { Text("Unsaved local draft").foregroundStyle(OliveTheme.attention) }
                        Button("Save with revision check") { Task { await model.save() } }
                            .disabled(!model.dirty || !model.allowed("edit") || model.busy || model.running)
                        Button("Discard draft", role: .destructive) { discard = true }.disabled(!model.dirty)
                    }
                }
                Section("Actions") {
                    ForEach(["build", "test", "run"], id: \.self) { operation in
                        Button(operation.capitalized) { Task { await model.run(operation) } }
                            .disabled(!model.allowed(operation) || model.dirty || model.busy || model.running || state.background?.active != nil)
                    }
                    if model.running { Button("Cancel operation", role: .destructive) { model.cancel() } }
                }
            }
            if !model.notice.isEmpty { Section { Text(model.notice).accessibilityIdentifier("studio.status") } }
            if !model.output.isEmpty { Section("Results") { Text(model.output).font(.system(.caption, design: .monospaced)).textSelection(.enabled) } }
            Section { Text("Only explicitly shared workspaces and configured Build, Test and Run actions are available.").font(.footnote) }
        }.navigationTitle("Studio")
            .confirmationDialog("Discard this unsaved draft?", isPresented: $discard) { Button("Discard", role: .destructive) { model.discard() } }
    }
}
