import SwiftUI

struct SelectedChatView: View {
    @Environment(AppState.self) private var state
    @State private var deleting: SignedSyncRecord?
    var body: some View {
        let conversations = state.sync.records.filter { $0.kind == "conversation" && !$0.deleted }
        let blocked = !state.sync.online || state.sync.busy || state.active
        List {
            Section {
                HStack(alignment: .top, spacing: 12) {
                    OliveIcon(symbol: "lock.shield", size: 32)
                    Text("Only conversations explicitly selected on the sending device are shared. Pairing does not share private desktop Chat.")
                        .font(.subheadline).foregroundStyle(OliveTheme.secondary)
                }.padding(.vertical, 4)
                Button { Task { await state.sync.sync("chat") } } label: {
                    HStack { Spacer(); if state.sync.busy { ProgressView().tint(OliveTheme.accentInk) }; Text("Sync Chat").font(.headline); Spacer() }
                        .foregroundStyle(OliveTheme.accentInk)
                }.disabled(blocked).listRowBackground(OliveTheme.accent.opacity(blocked ? 0.4 : 1))
                    .accessibilityLabel("Sync Chat")
                Button { Task { await state.sync.selectMobileChat(state.chatStore?.turns ?? []) } } label: {
                    Label("Select completed iPhone Chat", systemImage: "iphone.and.arrow.forward").frame(maxWidth: .infinity)
                }.disabled(blocked).accessibilityLabel("Select completed iPhone Chat")
            } footer: {
                if !state.sync.notice.isEmpty { Text(state.sync.notice).font(.footnote) }
            }.listRowBackground(OliveTheme.raised)
            if conversations.isEmpty {
                Section {
                    OliveEmptyState(symbol: "bubble.left.and.bubble.right", title: "No shared conversations",
                                    detail: "Sync Chat to bring in conversations selected on your computer.")
                }.listRowBackground(Color.clear)
            }
            ForEach(conversations) { conversation in
                Section {
                    NavigationLink { SyncedConversationView(conversation: conversation) } label: {
                        Label("Read conversation", systemImage: "text.bubble").foregroundStyle(OliveTheme.text)
                    }.accessibilityIdentifier("sync.read." + conversation.id)
                    Toggle(isOn: Binding(get: { state.sync.selected(conversation.id) }, set: { state.sync.select(conversation.id, $0) })) {
                        Label("Selected for this computer", systemImage: "checkmark.circle")
                    }.tint(OliveTheme.accent)
                    Button(role: .destructive) { deleting = conversation } label: {
                        Label("Delete shared conversation", systemImage: "trash")
                    }.disabled(blocked)
                } header: {
                    Text(conversation.payload["title"].string ?? "Conversation").font(.subheadline.weight(.semibold))
                        .foregroundStyle(OliveTheme.text).textCase(nil)
                }.listRowBackground(OliveTheme.raised)
            }
        }.oliveListStyle()
            .animation(OliveTheme.Motion.settle, value: conversations.map(\.id))
            .navigationTitle("Selected Chat").navigationBarTitleDisplayMode(.inline)
            .confirmationDialog("Delete this shared conversation?", isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }), titleVisibility: .visible) {
                Button("Delete conversation", role: .destructive) {
                    if let reviewed = deleting { Task { await state.sync.deleteConversation(reviewed) } }
                    deleting = nil
                }
            } message: {
                Text("This creates tombstones for the conversation and its messages. Tap Sync Chat to share the deletion. Completed Remote AI history on this iPhone is stored separately.")
            }
    }
}
private struct SyncedConversationView: View {
    @Environment(AppState.self) private var state
    let conversation: SignedSyncRecord
    private var messages: [SignedSyncRecord] {
        let snapshot = state.sync.store.snapshot
        let list = state.sync.records.filter { $0.kind == "message" && snapshot.messageParents[$0.id] == conversation.id }
        let byID = Dictionary(uniqueKeysWithValues: list.map { ($0.id, $0) })
        let children = Dictionary(grouping: list) { record in
            snapshot.messagePredecessors?[record.id] ?? record.payload["after"].string ?? ""
        }.mapValues { $0.map(\.id).sorted().reversed().map { $0 } }
        var result: [SignedSyncRecord] = [], visited = Set<String>(), pending = children[""] ?? []
        while let id = pending.popLast() {
            guard visited.insert(id).inserted, let record = byID[id] else { continue }
            if !record.deleted { result.append(record) }
            pending.append(contentsOf: children[id] ?? [])
        }
        return result
    }
    var body: some View {
        ScrollView {
            LazyVStack(spacing: 20) {
                ForEach(messages) { record in
                    MessageBubble(message: ChatMessage(id: UUID(uuidString: record.id) ?? UUID(),
                        role: record.payload["role"] == .string("user") ? .user : .assistant,
                        blocks: ChatMessage.parse(record.payload["content"].string ?? "")))
                }
                if messages.isEmpty {
                    OliveEmptyState(symbol: "text.bubble", title: "No messages", detail: "This shared conversation has no messages yet.")
                }
            }.olivePage().oliveAppear()
        }.background(OliveTheme.surface).defaultScrollAnchor(.top)
            .navigationTitle(conversation.payload["title"].string ?? "Chat").navigationBarTitleDisplayMode(.inline)
    }
}
