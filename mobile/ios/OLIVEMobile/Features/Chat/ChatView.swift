import SwiftUI

struct ChatView: View {
    @Environment(AppState.self) private var state
    @FocusState private var composerFocused: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var typeSize
    /// Whether the end of the conversation is on screen; drives the jump button and auto-follow.
    @State private var atBottom = true
    @State private var confirmingClear = false
    var body: some View {
        GeometryReader { geometry in ScrollViewReader { proxy in
            ScrollView {
                if state.messages.isEmpty {
                    emptyState.frame(minHeight: geometry.size.height)
                } else {
                    LazyVStack(spacing: 20) {
                        ForEach(state.messages) { message in
                            MessageBubble(message: message, thinking: state.active && message.id == state.messages.last?.id && message.role == .assistant)
                                .transition(reduceMotion ? .opacity : .asymmetric(
                                    insertion: .move(edge: .bottom).combined(with: .opacity), removal: .opacity))
                        }
                        Color.clear.frame(height: 1).id("latest")
                            .onAppear { if #unavailable(iOS 18) { atBottom = true } }
                            .onDisappear { if #unavailable(iOS 18) { atBottom = false } }
                    }.olivePage(top: OliveTheme.Space.medium)
                        .animation(reduceMotion ? nil : OliveTheme.Motion.settle, value: state.messages.count)
                }
            }
            .scrollDismissesKeyboard(.interactively)
            .defaultScrollAnchor(.bottom)
            .modifier(BottomTracking(atBottom: $atBottom))
            .onChange(of: state.messages) { old, new in
                // Follow a streaming reply only while already at the bottom; always follow a newly sent message.
                guard atBottom || new.count > old.count else { return }
                withAnimation(reduceMotion ? nil : .easeOut(duration: 0.18)) { proxy.scrollTo("latest", anchor: .bottom) }
            }
            .overlay(alignment: .bottom) {
                if !atBottom && !state.messages.isEmpty {
                    Button { scrollToLatest(proxy) } label: {
                        Image(systemName: "arrow.down").font(.system(size: 15, weight: .bold)).foregroundStyle(OliveTheme.text)
                            .frame(width: 38, height: 38)
                            .background(OliveTheme.raised, in: Circle())
                            .overlay(Circle().stroke(OliveTheme.border))
                            .shadow(color: .black.opacity(0.4), radius: 10, y: 3)
                            .frame(width: 44, height: 44).contentShape(Circle())
                    }.buttonStyle(OlivePressableStyle())
                        .padding(.bottom, 10)
                        .transition(reduceMotion ? .opacity : .scale(scale: 0.6).combined(with: .opacity))
                        .accessibilityLabel("Scroll to latest message").accessibilityIdentifier("chat.scrollToBottom")
                }
            }
            .animation(reduceMotion ? nil : OliveTheme.Motion.press, value: atBottom)
        } }
        .safeAreaInset(edge: .bottom, spacing: 0) { composer }
        .background(OliveTheme.surface).navigationTitle("Chat").navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if state.canClearChat {
                ToolbarItem(placement: .topBarLeading) {
                    Button { confirmingClear = true } label: { Image(systemName: "trash").frame(minWidth: 44, minHeight: 44) }
                        .accessibilityLabel("Clear chat").accessibilityIdentifier("chat.clear")
                }
            }
            if composerFocused {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { composerFocused = false }.accessibilityIdentifier("chat.dismissKeyboard")
                }
            }
        }
        .confirmationDialog("Clear this chat?", isPresented: $confirmingClear, titleVisibility: .visible) {
            Button("Clear chat", role: .destructive) {
                withAnimation(reduceMotion ? nil : OliveTheme.Motion.settle) { state.clearChat() }
            }.accessibilityIdentifier("chat.clearConfirm")
        } message: {
            Text("This removes the conversation and its saved history from this iPhone. OLIVE starts fresh with your next message. Anything already shared with your computer stays there.")
        }
    }

    private func scrollToLatest(_ proxy: ScrollViewProxy) {
        withAnimation(reduceMotion ? nil : OliveTheme.Motion.settle) { proxy.scrollTo("latest", anchor: .bottom) }
        // Lazy rows above may be re-measured on the way down; settle exactly on the end.
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(450))
            if !atBottom { withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) { proxy.scrollTo("latest", anchor: .bottom) } }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 20) {
            BreathingMark()
            VStack(spacing: 8) {
                Text("What’s on your mind?").font(OliveTheme.TypeStyle.heading).accessibilityAddTraits(.isHeader)
                Text("Your computer brings OLIVE’s answers here.").foregroundStyle(OliveTheme.secondary)
            }
            if state.connection != .connected {
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Image(systemName: "info.circle").foregroundStyle(OliveTheme.information)
                    Text(state.connection.explanation).font(.callout).foregroundStyle(OliveTheme.secondary)
                        .multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("chat.connectionRequired")
                }
                .padding(14).frame(maxWidth: 420, alignment: .leading)
                .background(OliveTheme.raised, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous))
            }
        }
        .multilineTextAlignment(.center).padding(OliveTheme.Space.page).frame(maxWidth: OliveTheme.pageWidth).frame(maxWidth: .infinity)
        .oliveAppear().accessibilityIdentifier("chat.empty")
    }

    private var composer: some View {
        @Bindable var state = state
        let presets = state.session.map { session in ["fast", "normal", "max"].filter { session.capability?["presets"][$0].boolean == true } } ?? []
        return VStack(spacing: 8) {
            HStack(spacing: 8) {
                HStack(spacing: 6) {
                    StatusDot(color: state.connection.tint, pulsing: state.active)
                    if let peer = state.session?.selected {
                        Text(peer.displayName).font(.caption.weight(.semibold)).foregroundStyle(OliveTheme.secondary)
                        Text("·").font(.caption).foregroundStyle(OliveTheme.muted)
                    }
                    Text(state.persistenceNotice ?? (state.chatStatus.isEmpty ? state.session?.status ?? "Not connected · local draft" : state.chatStatus))
                        .font(.caption).foregroundStyle(state.persistenceNotice == nil ? OliveTheme.muted : OliveTheme.attention)
                        .accessibilityIdentifier("chat.draftStatus")
                }.lineLimit(1).truncationMode(.middle)
                Spacer(minLength: 8)
                if state.session?.selected != nil, !presets.isEmpty {
                    Menu {
                        Picker("Model role", selection: $state.preset) {
                            ForEach(presets, id: \.self) { Text($0.capitalized).tag($0) }
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Text(state.preset.capitalized)
                            Image(systemName: "chevron.up.chevron.down").font(.caption2)
                        }
                        .font(.caption.weight(.semibold)).foregroundStyle(OliveTheme.accent)
                        .padding(.horizontal, 10).padding(.vertical, 5)
                        .background(OliveTheme.accent.opacity(0.12), in: Capsule())
                    }.disabled(state.active).accessibilityLabel("Model role")
                }
            }.padding(.horizontal, 6)
            HStack(alignment: .bottom, spacing: 8) {
                TextField("Message OLIVE", text: $state.draft, axis: .vertical)
                    .lineLimit(1...(typeSize.isAccessibilitySize ? 3 : 6)).font(.body).focused($composerFocused)
                    .padding(.vertical, 10).padding(.leading, 8).accessibilityIdentifier("chat.composer")
                Button {
                    if state.active { state.stop() } else { state.send() }
                } label: {
                    Image(systemName: state.active ? "stop.fill" : "arrow.up")
                        .font(.system(size: state.active ? 14 : 17, weight: .bold))
                        .foregroundStyle(state.active || state.canSend ? OliveTheme.accentInk : OliveTheme.muted)
                        .frame(width: 40, height: 40)
                        .background(state.active || state.canSend ? OliveTheme.accent : OliveTheme.surface, in: Circle())
                        .contentShape(Circle())
                        .contentTransition(.symbolEffect(.replace))
                        .frame(width: 44, height: 44)
                }.buttonStyle(OlivePressableStyle())
                    .disabled(state.active ? state.stopping : !state.canSend)
                    .opacity(state.stopping ? 0.6 : 1)
                    .animation(OliveTheme.Motion.press, value: state.canSend)
                    .animation(OliveTheme.Motion.press, value: state.active)
                    .accessibilityLabel(state.active ? (state.stopping ? "Stopping response" : "Stop response") : "Send message")
                    .accessibilityHint(state.active ? "Cancels the request on your computer" : "Requires a connected computer with Remote AI available")
                    .accessibilityIdentifier(state.active ? "chat.stop" : "chat.send")
            }.padding(4).padding(.leading, 4)
                .background(OliveTheme.raised, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.composer, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: OliveTheme.Radius.composer, style: .continuous)
                    .stroke(composerFocused ? OliveTheme.accent.opacity(0.7) : OliveTheme.border))
                .shadow(color: .black.opacity(0.35), radius: 12, y: 4)
                .animation(.easeOut(duration: 0.2), value: composerFocused)
        }.padding(.horizontal, OliveTheme.Space.medium).padding(.top, 6).padding(.bottom, 10)
            .frame(maxWidth: OliveTheme.pageWidth).frame(maxWidth: .infinity)
            // Same colour as the page, so it reads as part of it; messages fade out just above.
            .background(OliveTheme.surface.ignoresSafeArea(edges: .bottom))
            .overlay(alignment: .top) {
                LinearGradient(colors: [OliveTheme.surface.opacity(0), OliveTheme.surface], startPoint: .top, endPoint: .bottom)
                    .frame(height: 28).offset(y: -28).allowsHitTesting(false)
            }
    }
}

/// Tracks whether the end of the conversation is visible, from the scroll view's real geometry.
private struct BottomTracking: ViewModifier {
    @Binding var atBottom: Bool
    func body(content: Content) -> some View {
        if #available(iOS 18, *) {
            content.onScrollGeometryChange(for: Bool.self) { geometry in
                // visibleRect spans the insets too; the readable bottom edge sits above the composer and tab bar.
                geometry.visibleRect.maxY - geometry.contentInsets.bottom >= geometry.contentSize.height - 40
            } action: { _, isAtBottom in
                if atBottom != isAtBottom { atBottom = isAtBottom }
            }
        } else { content }
    }
}

/// The OLIVE mark with a slow, calm glow while Chat is empty.
private struct BreathingMark: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var breathing = false
    var body: some View {
        OliveMark(size: 64)
            .padding(18)
            .background(Circle().fill(OliveTheme.accent.opacity(breathing ? 0.16 : 0.07)))
            .scaleEffect(breathing ? 1.04 : 1)
            .onAppear {
                guard !reduceMotion else { return }
                withAnimation(.easeInOut(duration: 2.4).repeatForever(autoreverses: true)) { breathing = true }
            }
    }
}
