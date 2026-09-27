import SwiftUI
import UniformTypeIdentifiers

struct FilesView: View {
    @Environment(AppState.self) private var state
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var picker = false
    @State private var export: ExportItem?
    @State private var error: String?
    @State private var confirmingClear = false
    private struct ExportItem: Identifiable { let id = UUID(); let url: URL }
    var body: some View {
        let model = state.files
        let active = model.active, history = model.history
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                sendCard(model).oliveAppear(0)
                if !model.notice.isEmpty {
                    OliveNotice(text: model.notice, identifier: "files.status").transition(.opacity)
                }
                if let error {
                    OliveNotice(text: error, symbol: "exclamationmark.triangle", tint: OliveTheme.attention).transition(.opacity)
                }
                if !active.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        OliveSectionHeader(title: "In progress")
                        ForEach(active) { row in
                            transferCard(row, model: model)
                                .transition(.asymmetric(insertion: .opacity.combined(with: .move(edge: .top)),
                                                        removal: .opacity.combined(with: .scale(scale: 0.96))))
                        }
                    }
                }
                if active.isEmpty && history.isEmpty {
                    OliveEmptyState(symbol: "doc.on.doc", title: "No file transfers yet.",
                                    detail: "Files you send or receive show up here.")
                        .accessibilityIdentifier("files.empty").oliveAppear(1)
                }
                if !history.isEmpty {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack(alignment: .firstTextBaseline) {
                            OliveSectionHeader(title: "History")
                            Button("Clear") { confirmingClear = true }
                                .font(.subheadline.weight(.medium)).foregroundStyle(OliveTheme.accent)
                                .frame(minHeight: 44).disabled(!model.available)
                                .accessibilityLabel("Clear history").accessibilityIdentifier("files.clearHistory")
                        }
                        OliveRowGroup {
                            ForEach(Array(history.enumerated()), id: \.element.id) { index, row in
                                if index > 0 { OliveRowDivider(inset: 48) }
                                historyLine(row, model: model).transition(.opacity.combined(with: .move(edge: .top)))
                            }
                        }
                    }.oliveAppear(2)
                }
            }
            .olivePage()
            .animation(reduceMotion ? nil : OliveTheme.Motion.settle, value: model.receipts.map { $0.state + ($0.hidden == true ? "h" : "") })
            .animation(reduceMotion ? nil : OliveTheme.Motion.settle, value: model.notice)
        }
        .background(OliveTheme.surface).navigationTitle("Files").navigationBarTitleDisplayMode(.inline)
        .fileImporter(isPresented: $picker, allowedContentTypes: [.item]) { result in
            switch result { case .success(let url): error = nil; Task { await model.select(url) }; case .failure: error = "File selection was cancelled or unavailable." }
        }
        .sheet(item: $export) { item in FileExportPicker(url: item.url) }
        .confirmationDialog("Clear file history?", isPresented: $confirmingClear, titleVisibility: .visible) {
            Button("Clear history", role: .destructive) { model.clearHistory() }.accessibilityIdentifier("files.clearHistoryConfirm")
        } message: {
            Text("Finished transfers are removed from this list. Received files you haven’t saved are deleted from this iPhone. Transfers in progress are not affected.")
        }
    }

    private func sendCard(_ model: FilesModel) -> some View {
        OliveCard(padding: 20) {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 12) {
                    OliveIcon(symbol: "desktopcomputer", size: 40, tint: state.session?.connected == true ? OliveTheme.accent : OliveTheme.muted)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(state.session?.selected?.displayName ?? "Choose a paired computer in Devices").font(.headline)
                        Text(state.session?.connected == true ? "Connected" : "Not connected").font(.caption).foregroundStyle(OliveTheme.muted)
                    }
                }
                Button("Choose file to send", systemImage: "doc.badge.plus") { picker = true }
                    .buttonStyle(OliveButtonStyle(fullWidth: true))
                    .disabled(state.session?.connected != true || model.preparing || !model.available)
                Text("Up to 64 MiB per file. Interrupted transfers require a fresh explicit send.")
                    .font(.caption).foregroundStyle(OliveTheme.muted)
            }
        }
    }

    private func transferCard(_ row: MobileFileReceipt, model: FilesModel) -> some View {
        let connected = state.session?.connected == true, busy = state.background?.active != nil
        return OliveCard {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 12) {
                    OliveIcon(symbol: row.incoming ? "arrow.down.doc" : "arrow.up.doc", size: 36,
                              tint: row.incoming ? OliveTheme.information : OliveTheme.accent)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(row.metadata.name).font(.subheadline.weight(.semibold)).lineLimit(2).truncationMode(.middle)
                        Text(row.incoming ? "From computer" : "To computer").font(.caption).foregroundStyle(OliveTheme.muted)
                    }
                    Spacer(minLength: 8)
                    Text(FilesView.status(row)).font(.caption.weight(.semibold)).foregroundStyle(FilesView.tint(row))
                        .multilineTextAlignment(.trailing).accessibilityIdentifier("files.state." + row.id)
                }
                if row.metadata.size > 0 {
                    VStack(alignment: .leading, spacing: 4) {
                        ProgressView(value: Double(row.received), total: Double(row.metadata.size)).tint(OliveTheme.accent)
                            .animation(.easeOut(duration: 0.25), value: row.received)
                        Text("\(FilesView.bytes(row.received)) of \(FilesView.bytes(row.metadata.size))")
                            .font(.caption.monospacedDigit()).foregroundStyle(OliveTheme.muted)
                    }
                }
                HStack(spacing: 10) {
                    if row.state == "awaiting_approval", row.incoming {
                        Button("Accept transfer") { model.accept(row.id) }
                            .buttonStyle(OliveButtonStyle(fullWidth: true)).disabled(busy)
                    }
                    if row.state == "offered", !row.incoming {
                        Button("Send reviewed file") { Task { await model.send(row.id) } }
                            .buttonStyle(OliveButtonStyle(fullWidth: true))
                            .accessibilityIdentifier("files.send." + row.id)
                            .disabled(!connected || busy)
                    }
                    Button("Cancel transfer", role: .destructive) { Task { await model.cancel(row.id) } }
                        .buttonStyle(OliveButtonStyle(kind: .destructive, fullWidth: true))
                }
            }
        }
    }

    private func historyLine(_ row: MobileFileReceipt, model: FilesModel) -> some View {
        HStack(spacing: 12) {
            Image(systemName: row.incoming ? "arrow.down.circle" : "arrow.up.circle").font(.body)
                .foregroundStyle(row.state == "completed" ? OliveTheme.accent : OliveTheme.muted).frame(width: 22)
                .accessibilityLabel(row.incoming ? "Received" : "Sent")
            VStack(alignment: .leading, spacing: 2) {
                Text(row.metadata.name).font(.subheadline).foregroundStyle(OliveTheme.text).lineLimit(1).truncationMode(.middle)
                Text(FilesView.status(row)).font(.caption).foregroundStyle(FilesView.tint(row)).lineLimit(1)
                    .accessibilityIdentifier("files.state." + row.id)
            }
            Spacer(minLength: 8)
            if row.state == "completed", row.incoming {
                Button {
                    do { export = ExportItem(url: try model.exportURL(row.id)) } catch { self.error = error.localizedDescription }
                } label: {
                    Image(systemName: "square.and.arrow.down").font(.body.weight(.medium)).foregroundStyle(OliveTheme.accent)
                        .frame(width: 44, height: 44)
                }.accessibilityLabel("Save / Export to Files").accessibilityIdentifier("files.export")
            } else if !row.incoming, row.state != "completed" {
                Button { Task { await model.reconcile(row.id) } } label: {
                    Image(systemName: "arrow.clockwise").font(.body.weight(.medium)).foregroundStyle(OliveTheme.secondary)
                        .frame(width: 44, height: 44)
                }.disabled(state.session?.connected != true)
                    .accessibilityLabel("Check computer receipt")
            }
        }
        .padding(.leading, 14).padding(.trailing, 4).frame(minHeight: 52)
    }

    static func status(_ row: MobileFileReceipt) -> String {
        switch row.state {
        case "offered": row.incoming ? "Offered" : "Ready to send"
        case "awaiting_approval": row.incoming ? "Waiting for you" : "Waiting for computer"
        case "accepted": "Starting…"
        case "transferring":
            (row.incoming ? "Receiving" : "Sending") + (row.metadata.size > 0 ? " · \(Int(Double(row.received) / Double(row.metadata.size) * 100))%" : "")
        case "verifying": "Verifying"
        case "completed": row.incoming ? "Transfer verified · Ready to Save" : "Sent · Verified by computer"
        default: row.state.prefix(1).uppercased() + row.state.dropFirst()
        }
    }
    static func tint(_ row: MobileFileReceipt) -> Color {
        switch row.state {
        case "completed": OliveTheme.accent
        case "failed", "declined", "interrupted": OliveTheme.attention
        case "cancelled", "dismissed": OliveTheme.muted
        default: OliveTheme.information
        }
    }
    static func bytes(_ count: Int64) -> String { ByteCountFormatter.string(fromByteCount: count, countStyle: .file) }
}

private struct FileExportPicker: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        UIDocumentPickerViewController(forExporting: [url], asCopy: true)
    }
    func updateUIViewController(_ controller: UIDocumentPickerViewController, context: Context) {}
}
