import SwiftUI

struct SettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppState.self) private var state
    private let about = AboutInfo()
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
            Section {
                DisclosureGroup("Advanced connection diagnostics") {
                    Text("Connect 1 · Pairing TLS13/2 · Inference 1")
                    Text(state.session?.diagnostic ?? "idle").font(.caption.monospaced())
                    Text(state.session?.pairing.diagnostic ?? "idle").font(.caption.monospaced()).textSelection(.enabled)
                    if let id = state.lastRequestID { Text("Request: \(id)").font(.caption.monospaced()).textSelection(.enabled) }
                    if let seconds = state.firstResponseSeconds { Text("First visible response: \(seconds, specifier: "%.2f") s") }
                    if let seconds = state.totalResponseSeconds { Text("Complete response: \(seconds, specifier: "%.2f") s") }
                    if let seconds = state.stopSeconds { Text("Stop acknowledgement: \(seconds, specifier: "%.2f") s") }
                    Text("Unpair removes trust on this iPhone only. Your computer manages its own permissions and revocation.")
                }
            }.listRowBackground(OliveTheme.raised)
            Section {
                Label("Your draft stays on this iPhone", systemImage: "iphone")
                Text("OLIVE saves your draft locally. Paired computers provide answers over your local network.")
                    .foregroundStyle(OliveTheme.secondary)
            } header: { Text("Local storage") }
                .listRowBackground(OliveTheme.raised)
        }
        .scrollContentBackground(.hidden).background(OliveTheme.surface).foregroundStyle(OliveTheme.text)
        .navigationTitle("Settings").navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .confirmationAction) {
            Button("Done") { dismiss() }.accessibilityIdentifier("settings.done")
        } }
    }
}
