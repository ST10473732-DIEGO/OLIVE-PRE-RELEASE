import SwiftUI

struct StudioView: View {
    @Environment(AppState.self) private var state
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var discard = false
    private let actions = [("build", "hammer"), ("test", "checkmark.seal"), ("run", "play.fill")]
    var body: some View {
        @Bindable var model = state.studio
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                workspaces(model).oliveAppear(0)
                if model.workspaces.isEmpty && model.workspace == nil {
                    OliveEmptyState(symbol: "hammer", title: "No workspace open",
                                    detail: "Refresh to see workspaces your computer has shared with this iPhone.").oliveAppear(1)
                }
                if let workspace = model.workspace {
                    workspaceCard(workspace, model: model).transition(.opacity.combined(with: .move(edge: .top)))
                    if let path = model.filePath { editor(path, model: model).transition(.opacity) }
                    actionsCard(model)
                }
                if !model.notice.isEmpty {
                    OliveNotice(text: model.notice, symbol: noticeSymbol(model), tint: noticeTint(model), busy: model.running || model.busy,
                                identifier: "studio.status")
                }
                if !model.output.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        OliveSectionHeader(title: "Results")
                        ScrollView(.horizontal, showsIndicators: false) {
                            Text(model.output).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                                .fixedSize(horizontal: true, vertical: false).padding(14)
                        }
                        .background(OliveTheme.ground, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous).stroke(OliveTheme.border))
                    }.transition(.opacity)
                }
                Label("Only explicitly shared workspaces and configured Build, Test and Run actions are available.", systemImage: "lock.shield")
                    .font(.footnote).foregroundStyle(OliveTheme.muted)
            }
            .olivePage()
            .animation(reduceMotion ? nil : OliveTheme.Motion.settle, value: model.workspace?["workspace_id"].string)
            .animation(reduceMotion ? nil : OliveTheme.Motion.settle, value: model.filePath)
            .animation(reduceMotion ? nil : OliveTheme.Motion.settle, value: model.running)
        }
        .scrollDismissesKeyboard(.interactively)
        .background(OliveTheme.surface).navigationTitle("Studio").navigationBarTitleDisplayMode(.inline)
        .confirmationDialog("Discard this unsaved draft?", isPresented: $discard) { Button("Discard", role: .destructive) { model.discard() } }
    }

    private func workspaces(_ model: StudioModel) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center) {
                OliveSectionHeader(title: "Shared workspaces", detail: model.available ? nil : "Connect to your computer to browse.")
                Button { Task { await model.refresh() } } label: {
                    Image(systemName: "arrow.clockwise").font(.body.weight(.semibold)).frame(width: 44, height: 44)
                        .rotationEffect(.degrees(model.busy && !reduceMotion ? 360 : 0))
                        .animation(model.busy && !reduceMotion ? .linear(duration: 1).repeatForever(autoreverses: false) : .default, value: model.busy)
                }
                .foregroundStyle(OliveTheme.accent).opacity(!model.available || model.busy || model.running ? 0.4 : 1)
                .disabled(!model.available || model.busy || model.running)
                .accessibilityLabel("Refresh workspaces")
            }
            if !model.workspaces.isEmpty {
                OliveRowGroup {
                    ForEach(Array(model.workspaces.enumerated()), id: \.element.digest) { index, item in
                        if index > 0 { OliveRowDivider() }
                        let selected = item["workspace_id"].string != nil && item["workspace_id"].string == model.workspace?["workspace_id"].string
                        Button { Task { await model.open(item) } } label: {
                            OliveRow(symbol: "folder", tint: selected ? OliveTheme.accent : OliveTheme.secondary,
                                     title: item["display_name"].string ?? "Workspace") {
                                if selected { Image(systemName: "checkmark").foregroundStyle(OliveTheme.accent).accessibilityHidden(true) } else { OliveChevron() }
                            }
                        }.buttonStyle(OlivePressableStyle())
                            .accessibilityLabel(item["display_name"].string ?? "Workspace")
                            .accessibilityAddTraits(selected ? .isSelected : [])
                    }
                }
            }
        }
    }

    private func workspaceCard(_ workspace: ConnectJSON, model: StudioModel) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            OliveSectionHeader(title: workspace["display_name"].string ?? "Workspace")
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(["view", "edit", "build", "test", "run"], id: \.self) { capability in
                        let decision = workspace["permissions"]["studio." + capability].string ?? ""
                        let value = ["deny": "Off", "ask": "Ask", "allow": "Allow"][decision] ?? "Unknown"
                        OliveStatusPill(text: capability.capitalized + " · " + value,
                                        tint: decision == "allow" ? OliveTheme.accent : decision == "deny" ? OliveTheme.attention : OliveTheme.secondary)
                            .accessibilityLabel(capability.capitalized + " · " + (["deny": "Off", "ask": "Ask on computer", "allow": "Allow"][decision] ?? "Unknown"))
                    }
                }.padding(.horizontal, 4)
            }
            let files = model.entries.filter { $0["directory"].boolean != true }
            if !files.isEmpty {
                OliveRowGroup {
                    ForEach(Array(files.enumerated()), id: \.element.digest) { index, item in
                        if index > 0 { OliveRowDivider() }
                        let path = item["path"].string ?? "File"
                        Button { Task { await model.read(item["path"].string ?? "") } } label: {
                            OliveRow(symbol: "doc.text", tint: path == model.filePath ? OliveTheme.accent : OliveTheme.information, title: path)
                        }.buttonStyle(OlivePressableStyle())
                            .accessibilityLabel(path)
                    }
                }
            }
        }
    }

    private func editor(_ path: String, model: StudioModel) -> some View {
        @Bindable var model = model
        return VStack(alignment: .leading, spacing: 12) {
            HStack {
                Label(path, systemImage: "chevron.left.forwardslash.chevron.right").font(.subheadline.weight(.semibold))
                    .foregroundStyle(OliveTheme.text).lineLimit(1).truncationMode(.middle)
                Spacer(minLength: 8)
                if model.dirty { OliveStatusPill(text: "Unsaved local draft", tint: OliveTheme.attention).transition(.scale.combined(with: .opacity)) }
            }
            TextEditor(text: $model.text).font(.system(.callout, design: .monospaced)).frame(minHeight: 260)
                .scrollContentBackground(.hidden).padding(10)
                .background(OliveTheme.ground, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous)
                    .stroke(model.dirty ? OliveTheme.attention.opacity(0.5) : OliveTheme.border))
                .autocorrectionDisabled().textInputAutocapitalization(.never).accessibilityIdentifier("studio.editor")
            if let remote = model.remoteText {
                OliveCard {
                    DisclosureGroup {
                        Text(remote).font(.system(.caption, design: .monospaced)).textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 8)
                    } label: {
                        Label("Current computer version", systemImage: "desktopcomputer").font(.subheadline.weight(.medium))
                            .foregroundStyle(OliveTheme.text)
                    }.tint(OliveTheme.muted)
                }
            }
            VStack(spacing: 10) { saveButton(model); discardButton(model) }
        }.animation(OliveTheme.Motion.press, value: model.dirty)
    }

    private func saveButton(_ model: StudioModel) -> some View {
        Button("Save with revision check") { Task { await model.save() } }
            .buttonStyle(OliveButtonStyle(fullWidth: true))
            .disabled(!model.dirty || !model.allowed("edit") || model.busy || model.running)
    }
    private func discardButton(_ model: StudioModel) -> some View {
        Button("Discard draft", role: .destructive) { discard = true }
            .buttonStyle(OliveButtonStyle(kind: .destructive, fullWidth: true)).disabled(!model.dirty)
    }

    private func actionsCard(_ model: StudioModel) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            OliveSectionHeader(title: "Actions")
            HStack(spacing: 10) {
                ForEach(actions, id: \.0) { operation, symbol in
                    Button(operation.capitalized, systemImage: symbol) { Task { await model.run(operation) } }
                        .buttonStyle(OliveButtonStyle(kind: .secondary, fullWidth: true))
                        .disabled(!model.allowed(operation) || model.dirty || model.busy || model.running || state.background?.active != nil)
                }
            }
            if model.running {
                Button("Cancel operation", role: .destructive) { model.cancel() }
                    .buttonStyle(OliveButtonStyle(kind: .destructive, fullWidth: true))
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
    }

    private func noticeSymbol(_ model: StudioModel) -> String {
        let text = model.notice.lowercased()
        return text.hasPrefix("completed") ? "checkmark.circle" : text.contains("conflict") || text.contains("fail") || text.contains("unavailable") ? "exclamationmark.triangle" : "info.circle"
    }
    private func noticeTint(_ model: StudioModel) -> Color {
        let text = model.notice.lowercased()
        return text.hasPrefix("completed") ? OliveTheme.accent : text.contains("conflict") || text.contains("fail") || text.contains("unavailable") ? OliveTheme.attention : OliveTheme.information
    }
}
