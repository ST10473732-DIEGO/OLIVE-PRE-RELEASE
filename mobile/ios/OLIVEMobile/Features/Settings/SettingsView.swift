import SwiftUI

struct SettingsView: View {
    @Environment(\.dismiss) private var dismiss
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
                LabeledContent("Connection", value: "Not connected")
                    .accessibilityElement(children: .ignore).accessibilityLabel("Connection")
                    .accessibilityValue("Not connected").accessibilityIdentifier("settings.connection")
                Text("Pairing and Chat answers arrive in a later mobile update.").foregroundStyle(OliveTheme.secondary)
            } header: { Text("OLIVE Connect") }
                .listRowBackground(OliveTheme.raised)
            Section {
                Label("Your draft stays on this iPhone", systemImage: "iphone")
                Text("OLIVE saves your draft locally. No account, model or network connection is used in this version.")
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
