import SwiftUI

struct DevicesView: View {
    @Environment(AppState.self) private var state
    @State private var pairingPresented = false
    @State private var unpairID: String?
    @State private var notice: String?
    @State private var completionCode = ""
    private func permission(_ session: ConnectSession, _ capability: String) -> String {
        guard let value = session.companionCapability else { return "Unknown · C9.3 desktop status unavailable" }
        guard value["supported"][capability] == .bool(true) else { return "Unavailable" }
        return ["deny": "Off", "ask": "Ask on computer", "allow": "Allow"][value["permissions"][capability].string ?? ""] ?? "Unknown"
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: OliveTheme.Space.section) {
                if let session = state.session {
                    if !session.repository.isAvailable {
                        Text("Saved device trust could not be opened. The original data has been preserved.").foregroundStyle(OliveTheme.attention)
                    } else if session.peers.isEmpty {
                        OliveEmptyState(symbol: "laptopcomputer.and.iphone", title: "No paired devices",
                            detail: "Pair your OLIVE computer to bring its answers here.").accessibilityIdentifier("devices.empty")
                    } else {
                        OliveSectionHeader(title: "Paired")
                        ForEach(session.peers) { peer in
                            OliveCard {
                                VStack(alignment: .leading, spacing: 12) {
                                    Text(peer.displayName).font(.headline)
                                    Text(peer.id == session.selectedID ? session.status : "Offline").foregroundStyle(OliveTheme.secondary)
                                    if peer.id == session.selectedID, let capability = session.capability {
                                        Text("Remote AI · \(capability["permission"].string == "allow" ? "Allow" : capability["permission"].string == "ask" ? "Ask on computer" : "Off")")
                                    }
                                    if peer.id == session.selectedID {
                                        Text("Connect 1 · TLS 1.3").font(.caption)
                                        Text("Lifecycle · " + session.lifecycle.rawValue).font(.caption)
                                        ForEach(["tasks", "calendar", "reminders", "chat"], id: \.self) { domain in
                                            Text("Sync \(domain) · \(permission(session, "sync." + domain))").font(.caption)
                                        }
                                        Text("Send to computer · " + permission(session, "files.receive"))
                                        Text("Receive from computer · " + permission(session, "files.send")).font(.caption)
                                        Text("Studio · permissions shown per shared workspace").font(.caption)
                                        if let work = state.background?.active { Text("Active · " + work.label) }
                                    }
                                    HStack {
                                        Button(peer.id == session.selectedID ? "Reconnect" : "Use for Chat") {
                                            if peer.id == session.selectedID { session.retry() } else { session.select(peer.id) }
                                        }
                                        Spacer()
                                        Button("Unpair", role: .destructive) { unpairID = peer.id }
                                    }
                                }
                            }
                        }
                    }
                    OliveSectionHeader(title: "Nearby")
                    Text(session.discovery.status).font(.callout).foregroundStyle(OliveTheme.secondary)
                    ForEach(session.discovery.nearby) { peer in
                        OliveCard {
                            VStack(alignment: .leading, spacing: 12) {
                                Label(peer.title, systemImage: "desktopcomputer").font(.headline)
                                Text("Discovered · identity not yet verified").font(.caption).foregroundStyle(OliveTheme.secondary)
                                Button("Pair computer") { session.pairing.cancel(); pairingPresented = true }.buttonStyle(OliveButtonStyle())
                            }
                        }.accessibilityIdentifier("devices.nearby")
                    }
                    Button("Scan or paste pairing code", systemImage: "qrcode") { session.pairing.cancel(); pairingPresented = true }
                    Text("Create a pairing code in your computer’s Devices screen. Both devices must confirm the same value.")
                        .foregroundStyle(OliveTheme.secondary)
                    if !session.repository.interruptedSessions.isEmpty {
                        DisclosureGroup("Finish an interrupted confirmation") {
                            Text("Only a pairing you already confirmed on this iPhone can be recovered. Paste the computer’s completion code.").font(.callout)
                            TextEditor(text: $completionCode).frame(minHeight: 100).font(.caption.monospaced())
                            Button("Finish pairing") {
                                do {
                                    try session.repository.importCompletion(Data(completionCode.utf8))
                                    completionCode = ""; session.refreshPeers(); notice = "Pairing recovered."
                                } catch { notice = "The completion code does not match a saved local confirmation." }
                            }.disabled(completionCode.isEmpty || completionCode.utf8.count > 12288)
                            Button("Copy this iPhone’s completion code") {
                                if let sid = session.repository.interruptedSessions.first {
                                    do { UIPasteboard.general.string = try session.repository.completionCode(sid) }
                                    catch { notice = "The saved confirmation could not be opened." }
                                }
                            }
                        }
                    }
                    if let notice { Text(notice).foregroundStyle(OliveTheme.attention) }
                } else {
                    OliveEmptyState(symbol: "laptopcomputer.and.iphone", title: "No paired devices", detail: "Pair an OLIVE computer to chat.")
                        .accessibilityIdentifier("devices.empty")
                }
            }.padding(OliveTheme.Space.page).padding(.top, 16).frame(maxWidth: 640).frame(maxWidth: .infinity)
        }.background(OliveTheme.surface).navigationTitle("Devices").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { SettingsButton() } }
            .sheet(isPresented: $pairingPresented) {
                if let session = state.session { PairingSheet(pairing: session.pairing) { session.refreshPeers() } }
            }
            .confirmationDialog("Unpair this computer? This removes trust on this iPhone only.", isPresented: Binding(get: { unpairID != nil }, set: { if !$0 { unpairID = nil } })) {
                Button("Unpair", role: .destructive) {
                    if let id = unpairID { do { try state.session?.unpair(id) } catch { notice = "Could not remove saved trust." } }
                    unpairID = nil
                }
            } message: {
                Text("Your computer keeps its device record. To pair with it again, reset this iPhone’s Connect identity in Settings after unpairing all computers, then confirm a new pairing on both devices.")
            }
    }
}
