import SwiftUI

struct HomeView: View {
    @Environment(AppState.self) private var state
    private var greeting: String {
        switch Calendar.current.component(.hour, from: .now) {
        case 5..<12: "Good morning"
        case 12..<17: "Good afternoon"
        default: "Good evening"
        }
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                header.oliveAppear(0)
                askCard.oliveAppear(1)
                connectionCard.oliveAppear(2)
                if let background = state.background, background.active != nil || background.notice != nil {
                    backgroundWork(background).transition(.move(edge: .top).combined(with: .opacity))
                }
                companion.oliveAppear(3)
                Label("Drafts stay on this iPhone.", systemImage: "lock.iphone")
                    .font(.footnote).foregroundStyle(OliveTheme.muted)
                    .frame(maxWidth: .infinity).oliveAppear(4)
            }.olivePage().animation(OliveTheme.Motion.settle, value: state.background?.active?.label)
        }
        .background(OliveTheme.surface).navigationTitle("Home").navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .principal) {
                HStack(spacing: 8) { OliveMark(size: 26); Text("OLIVE").font(.subheadline.weight(.semibold)).tracking(3) }
                    .accessibilityElement(children: .combine)
            }
            ToolbarItem(placement: .topBarTrailing) { SettingsButton() }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(greeting).font(.subheadline.weight(.medium)).foregroundStyle(OliveTheme.accent)
            Text("A little space\nfor big ideas.").font(OliveTheme.TypeStyle.display)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("home.heading")
            Text("Your OLIVE, close at hand.").foregroundStyle(OliveTheme.secondary)
        }.padding(.top, 8)
    }

    private var askCard: some View {
        Button(action: state.openChat) {
            HStack(alignment: .center, spacing: 16) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(state.draft.isEmpty ? "Ask OLIVE…" : state.draft)
                        .font(.title3.weight(.medium)).foregroundStyle(OliveTheme.text).lineLimit(3)
                        .multilineTextAlignment(.leading)
                    Text(state.draft.isEmpty ? "Start with a thought" : "Continue your local draft")
                        .font(.subheadline).foregroundStyle(OliveTheme.secondary)
                }
                Spacer(minLength: 0)
                Image(systemName: "arrow.up.right").font(.headline).foregroundStyle(OliveTheme.accentInk)
                    .frame(width: 44, height: 44).background(OliveTheme.accent, in: Circle())
            }
            .padding(20).frame(maxWidth: .infinity, alignment: .leading)
            .background(
                LinearGradient(colors: [OliveTheme.accent.opacity(0.16), OliveTheme.raised], startPoint: .topLeading, endPoint: .bottomTrailing),
                in: RoundedRectangle(cornerRadius: OliveTheme.Radius.card, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: OliveTheme.Radius.card, style: .continuous).stroke(OliveTheme.accent.opacity(0.3)))
        }.buttonStyle(OlivePressableStyle())
            .accessibilityLabel(state.draft.isEmpty ? "Ask OLIVE" : "Continue your local draft")
            .accessibilityIdentifier("home.ask")
    }

    private var connectionCard: some View {
        OliveCard(padding: 20) {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .center) {
                    Text("Your computer").font(.headline)
                    Spacer()
                    ConnectionBadge(state: state.connection)
                }
                Text(state.connection.explanation).font(.subheadline).foregroundStyle(OliveTheme.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                Button("View devices") { state.destination = .devices }
                    .buttonStyle(OliveButtonStyle(kind: state.connection == .connected ? .secondary : .primary, fullWidth: true))
                    .accessibilityIdentifier("home.devices")
            }
        }
    }

    private var companion: some View {
        VStack(alignment: .leading, spacing: 12) {
            OliveSectionHeader(title: "Companion")
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 12)], spacing: 12) {
                tile("Today", detail: "Agenda and tasks", symbol: "calendar") { TodayView() }
                tile("Selected Chat", detail: "Shared conversations", symbol: "bubble.left.and.bubble.right") { SelectedChatView() }
                tile("Files", detail: "Send and receive", symbol: "folder") { FilesView() }
                tile("Remote Studio", detail: "Build, test and run", symbol: "hammer") { StudioView() }
            }
        }
    }

    private func tile<Destination: View>(_ title: String, detail: String, symbol: String,
                                         @ViewBuilder destination: @escaping () -> Destination) -> some View {
        NavigationLink(destination: destination) {
            VStack(alignment: .leading, spacing: 12) {
                OliveIcon(symbol: symbol, size: 36)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(OliveTheme.text)
                    Text(detail).font(.caption).foregroundStyle(OliveTheme.muted)
                }.multilineTextAlignment(.leading)
            }
            .padding(14).frame(maxWidth: .infinity, minHeight: 112, alignment: .topLeading)
            .background(OliveTheme.raised, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.card, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: OliveTheme.Radius.card, style: .continuous).stroke(OliveTheme.border))
        }.buttonStyle(OlivePressableStyle())
            .accessibilityLabel(title).accessibilityHint(detail).accessibilityIdentifier(title)
    }

    @ViewBuilder private func backgroundWork(_ background: BackgroundWorkCoordinator) -> some View {
        if let operation = background.active {
            OliveCard(padding: 20) {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(spacing: 12) {
                        OliveIcon(symbol: "arrow.triangle.2.circlepath", size: 32, tint: OliveTheme.information)
                        Text(operation.label).font(.headline)
                    }
                    if let total = operation.totalUnits, total > 0 {
                        ProgressView(value: Double(operation.verifiedUnits), total: Double(total)).tint(OliveTheme.accent)
                    } else { ProgressView().tint(OliveTheme.accent).frame(maxWidth: .infinity) }
                    Text(background.continuationGranted ? "Background continuation active" : "Keep OLIVE open to finish")
                        .font(.footnote).foregroundStyle(OliveTheme.secondary)
                    Button("Cancel work", role: .destructive) { Task { await background.cancel() } }
                        .buttonStyle(OliveButtonStyle(kind: .destructive, fullWidth: true))
                }
            }.accessibilityIdentifier("home.backgroundWork")
        }
        if let notice = background.notice {
            Label(notice, systemImage: "exclamationmark.circle").font(.footnote).foregroundStyle(OliveTheme.attention)
        }
    }
}
