import SwiftUI

struct SelectedChatView: View {
    @Environment(AppState.self) private var state
    var body: some View {
        List {
            Section {
                Text("Only conversations explicitly selected on the sending device are shared. Pairing does not share private desktop Chat.")
                Button("Select completed iPhone Chat") { Task { await state.sync.selectMobileChat(state.chatStore?.turns ?? []) } }
                    .disabled(!state.sync.online || state.sync.busy || state.active)
                Button("Sync Chat") { Task { await state.sync.sync("chat") } }.disabled(!state.sync.online || state.sync.busy || state.active)
                Text(state.sync.notice)
            }
            ForEach(state.sync.records.filter { $0.kind == "conversation" && !$0.deleted }) { conversation in
                Section(conversation.payload["title"].string ?? "Conversation") {
                    Toggle("Selected for this computer", isOn: Binding(get: { state.sync.selected(conversation.id) }, set: { state.sync.select(conversation.id, $0) }))
                    NavigationLink("Read conversation") { SyncedConversationView(conversation: conversation) }
                }
            }
        }.navigationTitle("Selected Chat")
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
            LazyVStack(alignment: .leading, spacing: 20) {
                ForEach(messages) { record in
                    VStack(alignment: .leading) {
                        Text(record.payload["role"] == .string("user") ? "You" : "OLIVE").font(.headline)
                        Text(record.payload["content"].string ?? "").textSelection(.enabled)
                    }
                }
            }.padding()
        }.navigationTitle(conversation.payload["title"].string ?? "Chat")
    }
}
