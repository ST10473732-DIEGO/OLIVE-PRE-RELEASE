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
        let list = state.sync.records.filter { $0.kind == "message" && !$0.deleted && $0.payload["conversation_id"] == .string(conversation.id) }
        var result: [SignedSyncRecord] = [], visited = Set<String>()
        func append(after: String?) {
            for item in list.filter({ $0.payload["after"].string == after }).sorted(by: { $0.id < $1.id }) where visited.insert(item.id).inserted {
                result.append(item); append(after: item.id)
            }
        }
        append(after: nil)
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
