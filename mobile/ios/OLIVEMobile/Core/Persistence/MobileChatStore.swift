import Foundation

struct MobileChatTurn: Codable, Identifiable {
    let id: String
    let userID: String
    let assistantID: String
    let peerID: String
    let preset: String
    let user: String
    let answer: String
    let createdAt: Date
}

@MainActor
final class MobileChatStore {
    private let store: ProtectedStore<[MobileChatTurn]>
    private(set) var turns: [MobileChatTurn] = []
    private(set) var available = true
    init(directory: URL = URL.applicationSupportDirectory.appendingPathComponent("Companion")) {
        store = ProtectedStore(url: directory.appendingPathComponent("chat-v1.json"), maximumBytes: 4_000_000)
        do { turns = try store.load() ?? []; guard turns.count <= 128 else { throw ConnectFailure.localStorageUnavailable } }
        catch { available = false }
    }
    func append(_ turn: MobileChatTurn) throws {
        guard available else { throw ConnectFailure.localStorageUnavailable }
        if let old = turns.first(where: { $0.id == turn.id }) {
            guard old.userID == turn.userID, old.assistantID == turn.assistantID,
                  old.user == turn.user, old.answer == turn.answer, old.peerID == turn.peerID else { throw ConnectFailure.syncConflict }
            return
        }
        // Completed turns are not silently evicted before selected sync.
        guard turns.count < 128 else { throw ConnectFailure.localStorageUnavailable }
        let next = turns + [turn]; try store.save(next); turns = next
    }
    /// User-requested clear of one computer's iPhone Chat history. Other computers' turns are kept.
    func removeTurns(peerID: String) throws {
        guard available else { throw ConnectFailure.localStorageUnavailable }
        let next = turns.filter { $0.peerID != peerID }
        guard next.count != turns.count else { return }
        try store.save(next); turns = next
    }
}
