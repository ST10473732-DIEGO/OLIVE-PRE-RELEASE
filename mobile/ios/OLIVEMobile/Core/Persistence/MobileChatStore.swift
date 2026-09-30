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
    // Remote Chat v2. Optional, so turns saved by earlier builds keep decoding
    // unchanged (they are FAST/NORMAL/MAX text with no attachments).
    var conversationID: String? = nil
    var attachments: [StoredChatAttachment]? = nil
    var sources: [ChatSource]? = nil
    var artifacts: [ChatArtifact]? = nil
    var attribution: ChatAttribution? = nil
}

/// A request that was sent and has not reached a conclusive outcome. Persisted so a
/// relaunch asks the computer for its status instead of silently losing or
/// regenerating it. Only one exists at a time (the computer allows one per phone).
struct PendingChatRequest: Codable, Equatable {
    let jobID: String
    let conversationID: String
    let peerID: String
    let mode: String
    let user: String
    let userID: String
    let assistantID: String
    let attachments: [StoredChatAttachment]
    var accepted: Bool
    var stopRequested: Bool
    var received: String
    let createdAt: Date
}

/// Per-computer Chat session: its conversation id (the computer's document context
/// for DEEP follow-ups) and the mode chosen for that conversation. Clearing the chat
/// starts a new conversation in OLIVE NORMAL, like a new desktop chat.
struct ChatSessionState: Codable, Equatable {
    struct Conversation: Codable, Equatable {
        var id: String
        var mode: String
        var voice: String?
    }
    var conversations: [String: Conversation] = [:]
    var draftAttachments: [StoredChatAttachment] = []
}

@MainActor
final class MobileChatStore {
    private let store: ProtectedStore<[MobileChatTurn]>
    private let pendingStore: ProtectedStore<PendingChatRequest?>
    private let sessionStore: ProtectedStore<ChatSessionState>
    private(set) var turns: [MobileChatTurn] = []
    private(set) var available = true
    init(directory: URL = URL.applicationSupportDirectory.appendingPathComponent("Companion")) {
        store = ProtectedStore(url: directory.appendingPathComponent("chat-v1.json"), maximumBytes: 4_000_000)
        pendingStore = ProtectedStore(url: directory.appendingPathComponent("chat-pending-v1.json"), maximumBytes: 400_000)
        sessionStore = ProtectedStore(url: directory.appendingPathComponent("chat-session-v1.json"), maximumBytes: 400_000)
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
    func pending() -> PendingChatRequest? { try? pendingStore.load() ?? nil }
    func savePending(_ value: PendingChatRequest?) throws { try pendingStore.save(value) }
    func session() -> ChatSessionState { (try? sessionStore.load()) ?? nil ?? ChatSessionState() }
    func saveSession(_ value: ChatSessionState) throws { try sessionStore.save(value) }

    /// User-requested clear of one computer's iPhone Chat history. Other computers' turns are kept.
    func removeTurns(peerID: String) throws {
        guard available else { throw ConnectFailure.localStorageUnavailable }
        let next = turns.filter { $0.peerID != peerID }
        guard next.count != turns.count else { return }
        try store.save(next); turns = next
    }
}
