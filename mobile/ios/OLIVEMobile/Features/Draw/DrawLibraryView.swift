import SwiftUI

/// OLIVE Draw library: drawings, Recently Deleted, new/rename/duplicate/delete.
struct DrawLibraryView: View {
    @Environment(AppState.self) private var state
    @State private var showTrash = false
    @State private var path: [String] = []
    @State private var purge: DrawSummary?
    @State private var renaming: DrawSummary?

    private var model: DrawModel { state.draw }

    var body: some View {
        NavigationStack(path: $path) {
            List {
                Section { DrawNoteSectionPicker() }.listRowBackground(Color.clear).listRowInsets(EdgeInsets(top: 4, leading: 0, bottom: 4, trailing: 0))
                Section { DrawSyncLine(sync: model.sync) }.listRowBackground(OliveTheme.raised)
                if let notice = model.notice {
                    Section {
                        OliveNotice(text: notice, symbol: "exclamationmark.triangle", tint: OliveTheme.attention)
                            .onTapGesture { model.notice = nil }
                    }.listRowBackground(Color.clear)
                }
                if !model.available {
                    Section {
                        OliveNotice(text: model.unavailableReason, symbol: "externaldrive.badge.exclamationmark", tint: OliveTheme.attention,
                                    identifier: "draw.unavailable")
                    }.listRowBackground(Color.clear)
                } else if showTrash {
                    trashSection
                } else if model.drawings.isEmpty {
                    Section {
                        OliveEmptyState(symbol: "scribble.variable", title: "No drawings yet",
                                        detail: "Drawings save as you draw and stay on this phone. They sync with your paired computer when you allow it.")
                        newMenu(label: Label("New drawing", systemImage: "plus")).buttonStyle(OliveButtonStyle())
                    }.listRowBackground(Color.clear)
                } else {
                    Section { ForEach(model.drawings) { row($0) } }.listRowBackground(OliveTheme.raised)
                }
            }
            .oliveListStyle()
            .navigationTitle(showTrash ? "Recently Deleted" : "OLIVE DrawNote")
            .navigationDestination(for: String.self) { id in DrawEditorView(drawingID: id) }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(showTrash ? "Drawings" : "Recently Deleted") { showTrash.toggle() }
                        .accessibilityLabel(showTrash ? "Show drawings" : "Show recently deleted drawings")
                        .accessibilityIdentifier("draw.trashToggle")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    newMenu(label: Image(systemName: "plus")).accessibilityLabel("New drawing").accessibilityIdentifier("draw.new")
                        .disabled(!model.available)
                }
            }
            .refreshable { await model.refresh(); model.sync.kick() }
            .confirmationDialog("Delete permanently?", isPresented: Binding(get: { purge != nil }, set: { if !$0 { purge = nil } }),
                                titleVisibility: .visible, presenting: purge) { row in
                Button("Delete permanently", role: .destructive) { Task { await model.purge(row.id) } }
            } message: { _ in Text("It is removed here and from your computer when they sync. This cannot be undone.") }
            .sheet(item: $renaming) { row in
                DrawRenameSheet(title: row.title) { title in Task { await model.rename(row.id, title) } }
            }
        }
    }

    private func newMenu<L: View>(label: L) -> some View {
        Menu {
            ForEach(DrawCanvas.presets) { preset in
                Button(preset.label) { create(preset) }
            }
        } label: { label }
    }

    private func create(_ preset: DrawCanvas.Preset) {
        showTrash = false
        Task { if let made = await model.create(preset) { path.append(made.id) } }
    }

    private var trashSection: some View {
        Section {
            if model.trash.isEmpty { Text("Nothing recently deleted.").foregroundStyle(OliveTheme.muted) }
            ForEach(model.trash) { row in
                DrawRow(summary: row, thumbnail: model.thumbnail(for: row))
                    .swipeActions(edge: .trailing) {
                        Button(role: .destructive) { purge = row } label: { Label("Delete permanently", systemImage: "trash.slash") }
                        Button { Task { await model.restore(row.id) } } label: { Label("Restore", systemImage: "arrow.uturn.backward") }.tint(OliveTheme.accent)
                    }
                    .contextMenu {
                        Button { Task { await model.restore(row.id) } } label: { Label("Restore", systemImage: "arrow.uturn.backward") }
                        Button(role: .destructive) { purge = row } label: { Label("Delete permanently", systemImage: "trash.slash") }
                    }
            }
        } footer: { Text("Deleted drawings stay here until you delete them permanently.") }
        .listRowBackground(OliveTheme.raised)
    }

    private func row(_ summary: DrawSummary) -> some View {
        NavigationLink(value: summary.id) { DrawRow(summary: summary, thumbnail: model.thumbnail(for: summary)) }
            .swipeActions(edge: .trailing) {
                Button(role: .destructive) { Task { await model.moveToTrash(summary.id) } } label: { Label("Delete", systemImage: "trash") }
                Button { Task { _ = await model.duplicate(summary.id) } } label: { Label("Duplicate", systemImage: "plus.square.on.square") }
            }
            .contextMenu {
                Button { renaming = summary } label: { Label("Rename", systemImage: "pencil") }
                Button { Task { _ = await model.duplicate(summary.id) } } label: { Label("Duplicate", systemImage: "plus.square.on.square") }
                Button(role: .destructive) { Task { await model.moveToTrash(summary.id) } } label: { Label("Delete", systemImage: "trash") }
            }
    }
}

/// Rename a drawing: a small sheet (return or Save commits; plain text only).
struct DrawRenameSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var title: String
    @FocusState private var focused: Bool
    let save: (String) -> Void
    init(title: String, save: @escaping (String) -> Void) { _title = State(initialValue: title); self.save = save }
    var body: some View {
        NavigationStack {
            Form {
                TextField("Title", text: $title)
                    .focused($focused).submitLabel(.done).autocorrectionDisabled()
                    .onSubmit(commit)
                    .accessibilityIdentifier("draw.renameField")
            }
            .scrollContentBackground(.hidden).background(OliveTheme.surface)
            .navigationTitle("Rename drawing").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Save", action: commit).accessibilityIdentifier("draw.renameSave") }
            }
            .onAppear { focused = true }
        }
        .presentationDetents([.height(200), .medium])
    }
    private func commit() { save(title); dismiss() }
}

/// One drawing: thumbnail, title, canvas size and last edit.
struct DrawRow: View {
    let summary: DrawSummary
    let thumbnail: UIImage?
    var body: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 6).fill(summary.background == "transparent" ? OliveTheme.surface : Color.white)
                if let thumbnail { Image(uiImage: thumbnail).resizable().scaledToFit().clipShape(RoundedRectangle(cornerRadius: 4)) }
            }
            .frame(width: 64, height: 48)
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(OliveTheme.border))
            .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                Text(summary.title).font(.body.weight(.semibold)).foregroundStyle(OliveTheme.text).lineLimit(1)
                Text("\(summary.width) × \(summary.height)" + (summary.status == "ok" ? "" : " · " + (summary.status == "unsupported" ? "made by a newer OLIVE" : "could not load")))
                    .font(.subheadline).foregroundStyle(OliveTheme.secondary)
                Text(when(summary.trashed ? summary.trashedAt : summary.updatedAt)).font(.caption).foregroundStyle(OliveTheme.muted)
            }
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(summary.title), drawing, \(summary.width) by \(summary.height)")
    }
    private func when(_ value: String) -> String {
        let parser = ISO8601DateFormatter(); parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = parser.date(from: value) ?? ISO8601DateFormatter().date(from: value) else { return "" }
        return "Edited " + date.formatted(.relative(presentation: .named))
    }
}

/// One quiet line: local saving is separate from syncing with the computer.
struct DrawSyncLine: View {
    let sync: DrawSync
    var body: some View {
        HStack(spacing: 10) {
            StatusDot(color: tint, pulsing: sync.state == .syncing)
            Text(sync.label).font(.subheadline).foregroundStyle(OliveTheme.secondary)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("draw.sync")
    }
    private var tint: Color {
        switch sync.state {
        case .synced: OliveTheme.accent
        case .syncing, .checking: OliveTheme.information
        case .error: OliveTheme.attention
        default: OliveTheme.muted
        }
    }
}
