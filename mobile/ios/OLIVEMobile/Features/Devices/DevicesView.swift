import SwiftUI

struct DevicesView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: OliveTheme.Space.section) {
                OliveEmptyState(symbol: "laptopcomputer.and.iphone", title: "No paired devices",
                                detail: "Your computer’s capabilities, close at hand. Connect an OLIVE computer here when pairing becomes available.")
                    .accessibilityIdentifier("devices.empty")
                OliveCard {
                    VStack(alignment: .leading, spacing: 12) {
                        Label("Pairing is coming next", systemImage: "link")
                            .font(.headline).foregroundStyle(OliveTheme.accent)
                        Text("This version doesn’t connect to computers yet.")
                            .foregroundStyle(OliveTheme.secondary)
                    }
                }
                VStack(alignment: .leading, spacing: 12) {
                    OliveSectionHeader(title: "You stay in control")
                    Text("Pairing will ask you to confirm both devices. Your computer will decide which capabilities to share.")
                        .foregroundStyle(OliveTheme.secondary)
                }
            }.padding(OliveTheme.Space.page).padding(.top, 16).frame(maxWidth: 640).frame(maxWidth: .infinity)
        }.background(OliveTheme.surface).navigationTitle("Devices").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { SettingsButton() } }
    }
}
