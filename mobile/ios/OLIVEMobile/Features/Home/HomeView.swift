import SwiftUI

struct HomeView: View {
    @Environment(AppState.self) private var state
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: OliveTheme.Space.section) {
                HStack(spacing: 10) {
                    OliveMark(size: 38)
                    Text("OLIVE").font(.headline).tracking(4)
                    Spacer()
                }.accessibilityElement(children: .combine)
                VStack(alignment: .leading, spacing: 12) {
                    Text("A little space\nfor big ideas.").font(OliveTheme.TypeStyle.display)
                        .accessibilityIdentifier("home.heading")
                    Text("Your OLIVE, close at hand.").foregroundStyle(OliveTheme.secondary)
                }
                Button(action: state.openChat) {
                    OliveCard {
                        VStack(alignment: .leading, spacing: 24) {
                            Text(state.draft.isEmpty ? "Ask OLIVE…" : state.draft)
                                .font(.title3).foregroundStyle(OliveTheme.text).lineLimit(3)
                            HStack {
                                Text(state.draft.isEmpty ? "Start with a thought" : "Continue your local draft")
                                    .font(.subheadline).foregroundStyle(OliveTheme.secondary)
                                Spacer()
                                Image(systemName: "arrow.up.right").font(.headline).foregroundStyle(OliveTheme.accent)
                            }
                        }
                    }
                }.buttonStyle(.plain).accessibilityLabel(state.draft.isEmpty ? "Ask OLIVE" : "Continue your local draft")
                    .accessibilityIdentifier("home.ask")
                VStack(alignment: .leading, spacing: 16) {
                    OliveSectionHeader(title: "Your connection")
                    OliveCard {
                        VStack(alignment: .leading, spacing: 16) {
                            ConnectionBadge(state: state.connection)
                            Text("Bring your computer along.").font(.headline)
                            Text(state.connection.explanation)
                                .foregroundStyle(OliveTheme.secondary)
                            Button("View devices") { state.destination = .devices }
                                .buttonStyle(OliveButtonStyle()).accessibilityIdentifier("home.devices")
                        }
                    }
                }
                NavigationLink { TodayView() } label: { Label("Today", systemImage: "calendar") }
                NavigationLink { SelectedChatView() } label: { Label("Selected Chat", systemImage: "bubble.left.and.bubble.right") }
                NavigationLink { FilesView() } label: { Label("Files", systemImage: "folder") }
                NavigationLink { StudioView() } label: { Label("Remote Studio", systemImage: "hammer") }
                if let background = state.background {
                    if let operation = background.active {
                        OliveCard {
                            VStack(alignment: .leading, spacing: 12) {
                                Text(operation.label).font(.headline)
                                if let total = operation.totalUnits, total > 0 {
                                    ProgressView(value: Double(operation.verifiedUnits), total: Double(total))
                                } else { ProgressView() }
                                Text(background.continuationGranted ? "Background continuation active" : "Keep OLIVE open to finish")
                                Button("Cancel work", role: .destructive) { Task { await background.cancel() } }
                            }
                        }.accessibilityIdentifier("home.backgroundWork")
                    }
                    if let notice = background.notice { Text(notice).font(.footnote).foregroundStyle(OliveTheme.attention) }
                }
                Label("Drafts stay on this iPhone.", systemImage: "iphone")
                    .font(.footnote).foregroundStyle(OliveTheme.muted)
            }.padding(OliveTheme.Space.page).frame(maxWidth: 640, alignment: .leading).frame(maxWidth: .infinity)
        }
        .background(OliveTheme.surface).navigationTitle("Home").navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .topBarTrailing) { SettingsButton() } }
    }
}
