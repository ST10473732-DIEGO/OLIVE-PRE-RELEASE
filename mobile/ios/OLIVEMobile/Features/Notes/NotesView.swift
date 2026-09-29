import SwiftUI

/// OLIVE Notes on the phone: a local notepad that syncs with the paired computer.
struct NotesView: View {
    @Environment(AppState.self) private var state
    @State private var showTrash = false
    @State private var path: [String] = []
    @State private var purge: NoteRow?

    private var model: NotesModel { state.notes }

    var body: some View {
        @Bindable var model = state.notes
        NavigationStack(path: $path) {
            List {
                Section { SyncLine(sync: model.sync) }.listRowBackground(OliveTheme.raised)
                if !model.available {
                    Section {
                        OliveNotice(text: model.unavailableReason, symbol: "externaldrive.badge.exclamationmark", tint: OliveTheme.attention)
                    }.listRowBackground(Color.clear)
                } else if showTrash {
                    trashSection
                } else if let results = model.results {
                    Section("Results") {
                        if results.isEmpty { Text("No notes match “\(model.query)”.").foregroundStyle(OliveTheme.muted) }
                        ForEach(results) { row in link(row) }
                    }.listRowBackground(OliveTheme.raised)
                } else if model.notes.isEmpty {
                    Section {
                        OliveEmptyState(symbol: "note.text", title: "No notes yet",
                                        detail: "Notes save as you type and stay on this phone. They sync with your paired computer when you allow it.")
                        Button { newNote() } label: { Label("New note", systemImage: "square.and.pencil") }
                            .buttonStyle(OliveButtonStyle())
                    }.listRowBackground(Color.clear)
                } else {
                    let pinned = model.notes.filter(\.pinned), others = model.notes.filter { !$0.pinned }
                    if !pinned.isEmpty { Section("Pinned") { ForEach(pinned) { link($0) } }.listRowBackground(OliveTheme.raised) }
                    Section(pinned.isEmpty ? "" : "Notes") { ForEach(others) { link($0) } }.listRowBackground(OliveTheme.raised)
                }
            }
            .oliveListStyle()
            .searchable(text: $model.query, prompt: "Search notes")
            .navigationTitle(showTrash ? "Recently Deleted" : "OLIVE Notes")
            .navigationDestination(for: String.self) { id in NoteEditorView(noteID: id) }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(showTrash ? "Notes" : "Recently Deleted") { showTrash.toggle() }
                        .accessibilityLabel(showTrash ? "Show notes" : "Show recently deleted notes")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { newNote() } label: { Image(systemName: "square.and.pencil") }
                        .accessibilityLabel("New note").disabled(!model.available)
                }
            }
            .refreshable { model.refresh(); model.sync.kick() }
            .confirmationDialog("Delete permanently?", isPresented: Binding(get: { purge != nil }, set: { if !$0 { purge = nil } }),
                                titleVisibility: .visible, presenting: purge) { row in
                Button("Delete permanently", role: .destructive) { model.purge(row.id) }
            } message: { _ in Text("It is removed here and from your computer when they sync. This cannot be undone.") }
        }
    }

    private var trashSection: some View {
        Section {
            if model.trash.isEmpty { Text("Nothing recently deleted.").foregroundStyle(OliveTheme.muted) }
            ForEach(model.trash) { row in
                link(row)
                    .swipeActions(edge: .trailing) {
                        Button(role: .destructive) { purge = row } label: { Label("Delete permanently", systemImage: "trash.slash") }
                        Button { model.restore(row.id) } label: { Label("Restore", systemImage: "arrow.uturn.backward") }.tint(OliveTheme.accent)
                    }
            }
        } footer: { Text("Deleted notes stay here until you delete them permanently.") }
        .listRowBackground(OliveTheme.raised)
    }

    private func link(_ row: NoteRow) -> some View {
        NavigationLink(value: row.id) {
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    if row.pinned { Image(systemName: "pin.fill").font(.caption).foregroundStyle(OliveTheme.accent).accessibilityLabel("Pinned") }
                    Text(row.displayTitle).font(.body.weight(.semibold)).foregroundStyle(OliveTheme.text).lineLimit(1)
                }
                Text(row.snippet.isEmpty ? (row.status == "ok" ? (row.preview.isEmpty ? "No additional text" : row.preview) : "Note data corrupted") : row.snippet)
                    .font(.subheadline).foregroundStyle(OliveTheme.secondary).lineLimit(2)
                Text(when(row.trashed ? row.trashedAt : row.editedAt)).font(.caption).foregroundStyle(OliveTheme.muted)
            }
            .padding(.vertical, 2)
            .accessibilityElement(children: .combine)
        }
        .swipeActions(edge: .leading) {
            if !row.trashed {
                Button { model.pin(row.id, !row.pinned) } label: { Label(row.pinned ? "Unpin" : "Pin", systemImage: row.pinned ? "pin.slash" : "pin") }
                    .tint(OliveTheme.accent)
            }
        }
        .swipeActions(edge: .trailing) {
            if !row.trashed {
                Button(role: .destructive) { model.moveToTrash(row.id) } label: { Label("Delete", systemImage: "trash") }
            }
        }
    }

    private func newNote() {
        showTrash = false
        model.query = ""
        if let id = model.create() { path.append(id) }
    }

    private func when(_ value: String) -> String {
        let parser = ISO8601DateFormatter(); parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = parser.date(from: value) ?? ISO8601DateFormatter().date(from: value) else { return "" }
        return date.formatted(.relative(presentation: .named))
    }
}

/// One quiet line: local saving is separate from syncing with the computer.
private struct SyncLine: View {
    let sync: NotesSync
    var body: some View {
        HStack(spacing: 10) {
            StatusDot(color: tint, pulsing: sync.state == .syncing)
            Text(label).font(.subheadline).foregroundStyle(OliveTheme.secondary)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("notes.sync")
    }
    private var label: String {
        switch sync.state {
        case .off: "Saved on this phone · Notes sync is off"
        case .unsupported: "Saved on this phone · this computer’s OLIVE doesn’t sync Notes yet"
        case .notAllowed: "Saved on this phone · allow Notes sync for this phone in Devices on your computer"
        case .offline: sync.pending > 0 ? "Offline — \(sync.pending) change(s) will sync later" : "Saved on this phone"
        case .syncing: "Syncing…"
        case .synced: "Synced with your computer"
        case .error(let code): "Sync issue (\(code)) · changes are saved on this phone"
        }
    }
    private var tint: Color {
        switch sync.state {
        case .synced: OliveTheme.accent
        case .syncing: OliveTheme.information
        case .error: OliveTheme.attention
        default: OliveTheme.muted
        }
    }
}
