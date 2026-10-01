import SwiftUI

struct DevicesView: View {
    @Environment(AppState.self) private var state
    @State private var pairingPresented = false
    @State private var unpairID: String?
    @State private var notice: String?
    @State private var completionCode = ""
    @State private var detailsExpanded = false
    private func permission(_ session: ConnectSession, _ capability: String) -> String {
        guard let value = session.companionCapability else { return "Unknown" }
        guard value["supported"][capability] == .bool(true) else { return "Unavailable" }
        return ["deny": "Off", "ask": "Ask on computer", "allow": "Allow"][value["permissions"][capability].string ?? ""] ?? "Unknown"
    }
    private func tint(_ value: String) -> Color {
        value == "Allow" || value == "Available" ? OliveTheme.accent : value == "Off" ? OliveTheme.attention : OliveTheme.secondary
    }
    private func lifecycleTitle(_ lifecycle: MobileLifecycleState) -> String {
        switch lifecycle {
        case .foregroundConnected: "Active"
        case .foregroundConnecting: "Connecting"
        case .backgroundActiveTask: "Working in background"
        case .backgroundSuspendedExpected: "Paused in background"
        case .pairedOffline: "Offline"
        case .reconnecting: "Reconnecting"
        case .revoked: "Revoked"
        case .unpaired: "Not paired"
        }
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                if let session = state.session {
                    if !session.repository.isAvailable {
                        Label("Saved device trust could not be opened. The original data has been preserved.", systemImage: "exclamationmark.triangle")
                            .foregroundStyle(OliveTheme.attention)
                    } else if session.peers.isEmpty {
                        OliveEmptyState(symbol: "laptopcomputer.and.iphone", title: "No paired devices",
                            detail: "Pair your OLIVE computer to bring its answers here.").accessibilityIdentifier("devices.empty")
                            .oliveAppear()
                    } else {
                        VStack(alignment: .leading, spacing: 12) {
                            OliveSectionHeader(title: "Paired")
                            ForEach(Array(session.peers.enumerated()), id: \.element.id) { index, peer in
                                peerCard(peer, session: session).oliveAppear(index)
                            }
                        }
                    }
                    addComputer(session).oliveAppear(1)
                    nearby(session).oliveAppear(2)
                    if !session.repository.interruptedSessions.isEmpty { interrupted(session) }
                    if let notice {
                        Label(notice, systemImage: "info.circle").font(.footnote).foregroundStyle(OliveTheme.attention)
                            .transition(.opacity)
                    }
                } else {
                    OliveEmptyState(symbol: "laptopcomputer.and.iphone", title: "No paired devices", detail: "Pair an OLIVE computer to chat.")
                        .accessibilityIdentifier("devices.empty").oliveAppear()
                }
            }.olivePage().animation(OliveTheme.Motion.settle, value: state.session?.peers.count)
                .animation(OliveTheme.Motion.settle, value: state.session?.discovery.nearby.count)
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

    private func peerCard(_ peer: TrustedConnectPeer, session: ConnectSession) -> some View {
        let selected = peer.id == session.selectedID
        // "Connected · Direct" or "Connected · World" only once OLIVE authenticated the computer.
        let status = selected ? (session.connected ? session.path.map { "Connected · " + $0.rawValue } ?? session.status : session.status) : "Offline"
        let online = selected && session.connected
        return OliveCard(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 14) {
                    OliveIcon(symbol: "desktopcomputer", size: 44, tint: online ? OliveTheme.accent : OliveTheme.muted)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(peer.displayName).font(.headline).lineLimit(2)
                        HStack(spacing: 6) {
                            StatusDot(color: online ? OliveTheme.accent : status == "Revoked" || status == "Identity rejected" ? OliveTheme.attention : OliveTheme.muted,
                                      pulsing: online || status == "Connecting")
                            Text(status).font(.subheadline).foregroundStyle(OliveTheme.secondary)
                        }
                    }
                    Spacer(minLength: 0)
                    if selected {
                        Text("In use").font(.caption.weight(.semibold)).foregroundStyle(OliveTheme.accent)
                            .padding(.horizontal, 8).padding(.vertical, 4).background(OliveTheme.accent.opacity(0.12), in: Capsule())
                    }
                }.padding(16)
                if selected { details(session).padding(.horizontal, 16) }
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: 10) { primaryAction(peer, session: session); unpairButton(peer) }
                    VStack(spacing: 10) { primaryAction(peer, session: session); unpairButton(peer) }
                }.padding(16)
            }
        }
    }

    private func primaryAction(_ peer: TrustedConnectPeer, session: ConnectSession) -> some View {
        let selected = peer.id == session.selectedID
        return Button(selected ? "Reconnect" : "Use for Chat", systemImage: selected ? "arrow.clockwise" : "bubble.left") {
            if selected { session.retry() } else { session.select(peer.id) }
        }.buttonStyle(OliveButtonStyle(kind: selected ? .secondary : .primary, fullWidth: true))
    }

    private func unpairButton(_ peer: TrustedConnectPeer) -> some View {
        Button("Unpair", role: .destructive) { unpairID = peer.id }
            .buttonStyle(OliveButtonStyle(kind: .destructive, fullWidth: true))
    }

    private func details(_ session: ConnectSession) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Divider().overlay(OliveTheme.border)
            Button {
                withAnimation(OliveTheme.Motion.settle) { detailsExpanded.toggle() }
            } label: {
                HStack {
                    Text("Permissions & details").font(.subheadline.weight(.medium)).foregroundStyle(OliveTheme.text)
                    Spacer()
                    Image(systemName: "chevron.down").font(.caption.weight(.semibold)).foregroundStyle(OliveTheme.muted)
                        .rotationEffect(.degrees(detailsExpanded ? 180 : 0))
                }.padding(.vertical, 14).contentShape(Rectangle())
            }.buttonStyle(.plain).accessibilityValue(detailsExpanded ? "Expanded" : "Collapsed")
            if detailsExpanded {
                VStack(alignment: .leading, spacing: 14) {
                    detailGroup("Assistant") {
                        if let capability = session.capability {
                            let value = capability["permission"].string == "allow" ? "Allow" : capability["permission"].string == "ask" ? "Ask on computer" : "Off"
                            OliveDetailRow(symbol: "sparkles", title: "Remote AI", value: value, valueTint: tint(value))
                        }
                        let studio = session.companionCapability.map { $0["supported"]["studio"] == .bool(true) ? "Available" : "Unavailable" } ?? "Unknown"
                        OliveDetailRow(symbol: "hammer", title: "Studio", value: studio, valueTint: tint(studio))
                    }
                    detailGroup("Sync") {
                        ForEach([("tasks", "checklist"), ("calendar", "calendar"), ("reminders", "bell"), ("chat", "bubble.left.and.bubble.right")], id: \.0) { domain, symbol in
                            let value = permission(session, "sync." + domain)
                            OliveDetailRow(symbol: symbol, title: domain.capitalized, value: value, valueTint: tint(value))
                        }
                    }
                    detailGroup("Files") {
                        let send = permission(session, "files.receive"), receive = permission(session, "files.send")
                        OliveDetailRow(symbol: "arrow.up.doc", title: "Send to computer", value: send, valueTint: tint(send))
                        OliveDetailRow(symbol: "arrow.down.doc", title: "Receive from computer", value: receive, valueTint: tint(receive))
                    }
                    detailGroup("Connection") {
                        OliveDetailRow(symbol: "lock.shield", title: "Security", value: "Connect 1 · TLS 1.3")
                        OliveDetailRow(symbol: session.path == .world ? "globe" : "wifi", title: "Path",
                                       value: session.connected ? session.path?.rawValue ?? "—" : "—")
                        OliveDetailRow(symbol: "globe", title: "OLIVE Connect World", value: session.worldStatus)
                            .accessibilityIdentifier("devices.world")
                        OliveDetailRow(symbol: "waveform.path.ecg", title: "State", value: lifecycleTitle(session.lifecycle))
                        if let work = state.background?.active {
                            OliveDetailRow(symbol: "arrow.triangle.2.circlepath", title: "Active", value: work.label)
                        }
                    }
                    if session.companionCapability == nil {
                        Text("Your computer hasn’t shared its feature status yet. Permissions are managed in its Devices screen.")
                            .font(.caption).foregroundStyle(OliveTheme.muted)
                    } else {
                        Text("Studio permissions apply per workspace. Change permissions in your computer’s Devices screen.")
                            .font(.caption).foregroundStyle(OliveTheme.muted)
                    }
                }.padding(.bottom, 4).transition(.opacity.combined(with: .move(edge: .top)))
            }
        }.clipped()
    }

    private func detailGroup<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title.uppercased()).font(.caption2.weight(.semibold)).tracking(1).foregroundStyle(OliveTheme.muted)
                .accessibilityAddTraits(.isHeader)
            content()
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
        .background(OliveTheme.surface, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous))
    }

    private func addComputer(_ session: ConnectSession) -> some View {
        OliveCard(padding: 20) {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 14) {
                    OliveIcon(symbol: "qrcode.viewfinder", size: 44)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Add a computer").font(.headline)
                        Text("Open Devices on your computer to show a pairing code.")
                            .font(.subheadline).foregroundStyle(OliveTheme.secondary).fixedSize(horizontal: false, vertical: true)
                    }
                }
                Button("Scan or paste pairing code", systemImage: "qrcode") { session.pairing.cancel(); pairingPresented = true }
                    .buttonStyle(OliveButtonStyle(kind: session.peers.isEmpty ? .primary : .secondary, fullWidth: true))
            }
        }
    }

    private func nearby(_ session: ConnectSession) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center, spacing: 8) {
                OliveSectionHeader(title: "Nearby", detail: session.discovery.status)
                if session.discovery.status.hasPrefix("Looking") { ProgressView().controlSize(.small).tint(OliveTheme.muted) }
            }
            ForEach(session.discovery.nearby) { peer in
                OliveCard {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 14) { nearbyLabel(peer); Spacer(minLength: 8); pairNearby(session) }
                        VStack(alignment: .leading, spacing: 12) { nearbyLabel(peer); pairNearby(session) }
                    }
                }.accessibilityIdentifier("devices.nearby").transition(.opacity.combined(with: .scale(scale: 0.96)))
            }
        }
    }

    private func nearbyLabel(_ peer: NearbyConnectPeer) -> some View {
        HStack(spacing: 14) {
            OliveIcon(symbol: "desktopcomputer", size: 40, tint: OliveTheme.information)
            VStack(alignment: .leading, spacing: 2) {
                Text(peer.title).font(.headline).lineLimit(2)
                Text("Not yet verified").font(.caption).foregroundStyle(OliveTheme.muted)
            }
        }
    }

    private func pairNearby(_ session: ConnectSession) -> some View {
        Button("Pair") { session.pairing.cancel(); pairingPresented = true }.buttonStyle(OliveButtonStyle())
            .accessibilityLabel("Pair computer")
    }

    private func interrupted(_ session: ConnectSession) -> some View {
        OliveCard {
            DisclosureGroup {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Only a pairing you already confirmed on this iPhone can be recovered. Paste the computer’s completion code.")
                        .font(.callout).foregroundStyle(OliveTheme.secondary)
                    TextEditor(text: $completionCode).frame(minHeight: 100).font(.caption.monospaced())
                        .scrollContentBackground(.hidden).padding(8)
                        .background(OliveTheme.surface, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.control))
                    Button("Finish pairing") {
                        do {
                            try session.repository.importCompletion(Data(completionCode.utf8))
                            completionCode = ""; session.refreshPeers(); notice = "Pairing recovered."
                        } catch { notice = "The completion code does not match a saved local confirmation." }
                    }.buttonStyle(OliveButtonStyle(fullWidth: true))
                        .disabled(completionCode.isEmpty || completionCode.utf8.count > 12288)
                    Button("Copy this iPhone’s completion code") {
                        if let sid = session.repository.interruptedSessions.first {
                            do { UIPasteboard.general.string = try session.repository.completionCode(sid) }
                            catch { notice = "The saved confirmation could not be opened." }
                        }
                    }.buttonStyle(OliveButtonStyle(kind: .secondary, fullWidth: true))
                }.padding(.top, 12)
            } label: {
                Label("Finish an interrupted confirmation", systemImage: "exclamationmark.arrow.circlepath")
                    .font(.subheadline.weight(.medium)).foregroundStyle(OliveTheme.text)
            }.tint(OliveTheme.muted)
        }
    }
}
