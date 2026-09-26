import SwiftUI

struct ChatView: View {
    @Environment(AppState.self) private var state
    @FocusState private var composerFocused: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var typeSize
    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 24) {
                    if state.messages.isEmpty {
                        VStack(alignment: .leading, spacing: 24) {
                            OliveMark(size: 72)
                            OliveEmptyState(symbol: "bubble.left.and.bubble.right", title: "What’s on your mind?",
                                            detail: "Your computer brings OLIVE’s answers here.")
                            Text(state.connection.explanation).font(.callout).foregroundStyle(OliveTheme.secondary)
                                .accessibilityIdentifier("chat.connectionRequired")
                            Text("No messages sent").font(.footnote).foregroundStyle(OliveTheme.muted)
                        }.padding(.vertical, 24).accessibilityIdentifier("chat.empty")
                    }
                    ForEach(state.messages) { MessageBubble(message: $0) }
                    Color.clear.frame(height: 1).id("latest")
                }.padding(OliveTheme.Space.page).frame(maxWidth: 640).frame(maxWidth: .infinity)
            }
            .scrollDismissesKeyboard(.interactively)
            .onChange(of: state.messages) { _, _ in
                withAnimation(reduceMotion ? nil : .easeOut(duration: 0.18)) { proxy.scrollTo("latest", anchor: .bottom) }
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) { composer }
        .background(OliveTheme.surface).navigationTitle("Chat").navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if composerFocused {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { composerFocused = false }.accessibilityIdentifier("chat.dismissKeyboard")
                }
            }
        }
    }
    private var composer: some View {
        @Bindable var state = state
        return VStack(alignment: .leading, spacing: 12) {
            if let session = state.session, let peer = session.selected {
                HStack {
                    Text(peer.displayName).font(.caption)
                    Spacer()
                    Picker("Model role", selection: $state.preset) {
                        ForEach(["fast", "normal", "max"].filter { session.capability?["presets"][$0].boolean == true }, id: \.self) { Text($0.capitalized).tag($0) }
                    }.disabled(state.active)
                }
            }
            HStack(alignment: .bottom, spacing: 8) {
                TextField("Message OLIVE", text: $state.draft, axis: .vertical)
                    .lineLimit(1...(typeSize.isAccessibilitySize ? 3 : 6)).font(.body).focused($composerFocused)
                    .padding(.vertical, 10).accessibilityIdentifier("chat.composer")
                Button {
                    if state.active { state.stop() } else { state.send() }
                } label: {
                    Image(systemName: state.active ? "stop.fill" : "arrow.up")
                        .font(.system(size: state.active ? 14 : 17, weight: .semibold))
                        .foregroundStyle(state.active || state.canSend ? OliveTheme.accentInk : OliveTheme.muted)
                        .frame(width: 44, height: 44)
                        .background(state.active || state.canSend ? OliveTheme.accent : OliveTheme.surface, in: Circle())
                        .contentShape(Circle())
                }.buttonStyle(.plain)
                    .disabled(state.active ? state.stopping : !state.canSend)
                    .opacity(state.stopping ? 0.6 : 1)
                    .accessibilityLabel(state.active ? (state.stopping ? "Stopping response" : "Stop response") : "Send message")
                    .accessibilityHint(state.active ? "Cancels the request on your computer" : "Requires a connected computer with Remote AI available")
                    .accessibilityIdentifier(state.active ? "chat.stop" : "chat.send")
            }.padding(10).background(OliveTheme.raised, in: RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(composerFocused ? OliveTheme.accent : OliveTheme.border))
            Text(state.persistenceNotice ?? (state.chatStatus.isEmpty ? state.session?.status ?? "Not connected · local draft" : state.chatStatus))
                .font(.caption).foregroundStyle(state.persistenceNotice == nil ? OliveTheme.muted : OliveTheme.attention)
                .accessibilityIdentifier("chat.draftStatus")
        }.padding(.horizontal, OliveTheme.Space.medium).padding(.vertical, 12)
            .frame(maxWidth: 640).frame(maxWidth: .infinity).background(OliveTheme.ground)
    }
}
