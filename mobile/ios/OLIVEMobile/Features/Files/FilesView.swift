import SwiftUI
import UniformTypeIdentifiers

struct FilesView: View {
    @Environment(AppState.self) private var state
    @State private var picker = false
    @State private var export: ExportItem?
    @State private var error: String?
    private struct ExportItem: Identifiable { let id = UUID(); let url: URL }
    var body: some View {
        let model = state.files
        List {
            Section {
                Text(state.session?.selected?.displayName ?? "Choose a paired computer in Devices")
                Button("Choose file to send", systemImage: "doc.badge.plus") { picker = true }
                    .disabled(state.session?.connected != true || model.preparing || !model.available)
                Text("Up to 64 MiB per file. Interrupted transfers require a fresh explicit send.").font(.footnote)
            }
            if !model.notice.isEmpty { Section { Text(model.notice).accessibilityIdentifier("files.status") } }
            if let error { Section { Text(error).foregroundStyle(OliveTheme.attention) } }
            if model.recent.isEmpty { Text("No file transfers yet.").accessibilityIdentifier("files.empty") }
            ForEach(model.recent) { row in
                Section(row.metadata.name) {
                    Text(row.incoming ? "Incoming" : "To computer")
                    Text(row.state == "completed" && row.incoming ? "Transfer verified · Ready to Save" : row.state)
                        .accessibilityIdentifier("files.state." + row.id)
                    Text("\(row.received) of \(row.metadata.size) bytes").font(.caption.monospacedDigit())
                    if row.metadata.size > 0 { ProgressView(value: Double(row.received), total: Double(row.metadata.size)) }
                    if row.state == "awaiting_approval", row.incoming {
                        Button("Accept transfer") { model.accept(row.id) }.disabled(state.background?.active != nil)
                    }
                    if row.state == "offered", !row.incoming {
                        Button("Send reviewed file") { Task { await model.send(row.id) } }
                            .accessibilityIdentifier("files.send." + row.id)
                            .disabled(state.session?.connected != true || state.background?.active != nil)
                    }
                    if !FileWire.terminal.contains(row.state) {
                        Button("Cancel transfer", role: .destructive) { Task { await model.cancel(row.id) } }
                    }
                    if row.state == "completed", row.incoming {
                        Button("Save / Export to Files") {
                            do { export = ExportItem(url: try model.exportURL(row.id)) } catch { self.error = error.localizedDescription }
                        }.accessibilityIdentifier("files.export")
                    }
                    if !row.incoming, FileWire.terminal.contains(row.state) {
                        Button("Check computer receipt") { Task { await model.reconcile(row.id) } }.disabled(state.session?.connected != true)
                    }
                }
            }
        }.navigationTitle("Files")
            .fileImporter(isPresented: $picker, allowedContentTypes: [.item]) { result in
                switch result { case .success(let url): Task { await model.select(url) }; case .failure: error = "File selection was cancelled or unavailable." }
            }
            .sheet(item: $export) { item in FileExportPicker(url: item.url) }
    }
}

private struct FileExportPicker: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        UIDocumentPickerViewController(forExporting: [url], asCopy: true)
    }
    func updateUIViewController(_ controller: UIDocumentPickerViewController, context: Context) {}
}
