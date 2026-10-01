import SwiftUI

struct SettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppState.self) private var state
    private let about = AboutInfo()
    @State private var confirmIdentityReset = false
    @State private var identityResetNotice: String?
    @State private var mediaBytes: Int64?
    @State private var confirmClearMedia = false
    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 12) {
                    OliveMark(size: 64)
                    Text(about.name).font(OliveTheme.TypeStyle.heading)
                    Text("A companion to your OLIVE computer.").foregroundStyle(OliveTheme.secondary)
                }.padding(.vertical, 12)
                LabeledContent("Version", value: about.versionDescription)
                    .accessibilityElement(children: .ignore).accessibilityLabel("Version")
                    .accessibilityValue(about.versionDescription).accessibilityIdentifier("settings.version")
            } header: { Text("About") }
                .listRowBackground(OliveTheme.raised)
            Section {
                LabeledContent("Connection", value: state.connection.title)
                    .accessibilityElement(children: .ignore).accessibilityLabel("Connection")
                    .accessibilityValue(state.connection.title).accessibilityIdentifier("settings.connection")
                Text("Pair computers and manage connections in Devices.").foregroundStyle(OliveTheme.secondary)
            if let fingerprint = state.session?.fingerprint { Text("Identity: \(fingerprint.prefix(23))…").font(.caption.monospaced()) }
                Text("Paired devices: \(state.session?.peers.count ?? 0)")
            } header: { Text("OLIVE Connect") }
                .listRowBackground(OliveTheme.raised)
            if let session = state.session {
                Section {
                    Toggle("OLIVE Connect World", isOn: Binding(get: { session.worldEnabled }, set: { session.worldEnabled = $0 }))
                        .accessibilityIdentifier("settings.world")
                    LabeledContent("Status", value: session.worldEnabled ? session.worldStatus : "Off")
                        .accessibilityElement(children: .ignore).accessibilityLabel("Connect World status")
                        .accessibilityValue(session.worldEnabled ? session.worldStatus : "Off").accessibilityIdentifier("settings.worldStatus")
                    Text("Uses a secure relay when your computer isn’t reachable directly. Your computer still runs everything; the relay can’t read your chats, notes, drawings or files. Each computer sets this up the first time this iPhone connects to it on your local network.")
                        .font(.footnote).foregroundStyle(OliveTheme.secondary)
                } header: { Text("OLIVE Connect World") }
                    .listRowBackground(OliveTheme.raised)
            }
            Section {
                Toggle("Sync notes with your computer", isOn: Binding(get: { state.notes.sync.enabled }, set: { state.notes.sync.enabled = $0 }))
                    .accessibilityIdentifier("settings.notesSync")
                Text("Notes are saved on this phone first. When this is on and your computer allows Notes sync for this phone, changes sync over OLIVE Connect while OLIVE is open. Copying text never syncs anything.")
                    .font(.footnote).foregroundStyle(OliveTheme.secondary)
            } header: { Text("OLIVE DrawNote · Notes") }
                .listRowBackground(OliveTheme.raised)
            Section {
                Toggle("Sync drawings with your computer", isOn: Binding(get: { state.draw.sync.enabled }, set: { state.draw.sync.enabled = $0 }))
                    .accessibilityIdentifier("settings.drawSync")
                Text("Drawings are saved on this phone first. When this is on and your computer allows Draw sync for this phone (Devices › this iPhone › Draw sync on the computer), completed strokes and imported images sync over OLIVE Connect while OLIVE is open. Notes and Draw permissions are separate.")
                    .font(.footnote).foregroundStyle(OliveTheme.secondary)
            } header: { Text("OLIVE DrawNote · Draw") }
                .listRowBackground(OliveTheme.raised)
            if let notifications = state.background?.notifications {
                Section("Notifications") {
                    Toggle("Operation completion", isOn: Binding(get: { notifications.enabled }, set: { value in
                        Task { await notifications.setEnabled(value) }
                    }))
                    Text("Private labels only: response ready, file transfer complete or Studio operation finished.").font(.footnote)
                    if !notifications.notice.isEmpty { Text(notifications.notice) }
                }
            }
            Section {
                DisclosureGroup("Advanced connection diagnostics") {
                    Text("Connect 1 · Pairing TLS13/2 · Inference 1" + (state.chatCapabilities != nil ? " · Chat 1" : ""))
                    Text(state.session?.diagnostic ?? "idle").font(.caption.monospaced())
                    if let session = state.session {
                        // World diagnostics: states only. Never the route, its secret or any key.
                        Text("World: " + (session.worldSupported.map { $0 ? "supported" : "not supported" } ?? "unknown")
                             + " · " + (session.worldProvisioned ? "provisioned" : "not provisioned")
                             + " · path " + (session.path?.rawValue ?? "none")).font(.caption.monospaced())
                    }
                    Text(state.session?.pairing.diagnostic ?? "idle").font(.caption.monospaced()).textSelection(.enabled)
                    if let id = state.lastRequestID { Text("Request: \(id)").font(.caption.monospaced()).textSelection(.enabled) }
                    if let seconds = state.firstResponseSeconds { Text("First visible response: \(seconds, specifier: "%.2f") s") }
                    if let seconds = state.totalResponseSeconds { Text("Complete response: \(seconds, specifier: "%.2f") s") }
                    if let seconds = state.stopSeconds { Text("Stop acknowledgement: \(seconds, specifier: "%.2f") s") }
                    if let operation = state.background?.records.last {
                        Text("Latest work: \(operation.label) · \(operation.state.rawValue)")
                        if let failure = operation.failure { Text(failure.localizedDescription) }
                        if let finished = operation.finishedAt {
                            Text("Finished: \(finished.formatted(date: .abbreviated, time: .standard))")
                        }
                    }
                    Text("Unpair removes trust on this iPhone only. Your computer manages its own permissions and revocation.")
                    if let session = state.session {
                        Button("Reset this iPhone’s Connect identity", role: .destructive) { confirmIdentityReset = true }
                            .disabled(!session.canResetIdentity || state.active)
                            .accessibilityIdentifier("settings.resetIdentity")
                        Text("Unpair all computers first. Reset is needed before pairing again with a computer that already knows or has revoked this iPhone.")
                            .font(.caption)
                        if session.resettingIdentity { ProgressView("Resetting identity…") }
                        if let identityResetNotice { Text(identityResetNotice).font(.callout) }
                    }
                }
            }.listRowBackground(OliveTheme.raised)
            Section {
                LabeledContent("Downloaded Chat media", value: mediaBytes.map { ByteCountFormatter.string(fromByteCount: $0, countStyle: .file) } ?? "…")
                    .accessibilityIdentifier("settings.chatMedia")
                Button("Clear downloaded Chat media", role: .destructive) { confirmClearMedia = true }
                    .disabled((mediaBytes ?? 0) == 0 || state.active)
                    .accessibilityIdentifier("settings.clearChatMedia")
                Text("Images, speech and videos from your computer are kept on this iPhone so Chat can show them offline. Clearing removes only these copies; your computer keeps its results, and Chat can download them again when connected. Notes and drawings are not affected.")
                    .font(.footnote).foregroundStyle(OliveTheme.secondary)
            } header: { Text("Chat media") }
                .listRowBackground(OliveTheme.raised)
            Section {
                Label("Your draft stays on this iPhone", systemImage: "iphone")
                Text("OLIVE saves your draft locally. Paired computers provide answers over your local network or OLIVE Connect World.")
                    .foregroundStyle(OliveTheme.secondary)
            } header: { Text("Local storage") }
                .listRowBackground(OliveTheme.raised)
        }
        .scrollContentBackground(.hidden).background(OliveTheme.surface).foregroundStyle(OliveTheme.text)
        .navigationTitle("Settings").navigationBarTitleDisplayMode(.inline)
        .confirmationDialog("Reset this iPhone’s Connect identity?", isPresented: $confirmIdentityReset, titleVisibility: .visible) {
            Button("Reset identity", role: .destructive) {
                guard let session = state.session, !state.active else { return }
                Task {
                    do {
                        try await session.resetIdentity()
                        identityResetNotice = "Identity reset. Pair again from Devices and set permissions on your computer."
                    } catch {
                        identityResetNotice = "Could not reset identity. Unlock this iPhone and try again."
                    }
                }
            }
        } message: {
            Text("This replaces your saved device key and discards unfinished pairing confirmations. You must pair again and receive new permissions on each computer. Computer-side trust records are unchanged. Your draft stays on this iPhone.")
        }
        .task { mediaBytes = await state.mediaStore.totalBytes() }
        .confirmationDialog("Clear downloaded Chat media?", isPresented: $confirmClearMedia, titleVisibility: .visible) {
            Button("Clear media", role: .destructive) {
                Task { await state.clearDownloadedMedia(); mediaBytes = await state.mediaStore.totalBytes() }
            }
        } message: { Text("Chat keeps its messages. Media downloads again from your computer when you open those messages while connected.") }
        .toolbar { ToolbarItem(placement: .confirmationAction) {
            Button("Done") { dismiss() }.accessibilityIdentifier("settings.done")
        } }
    }
}
