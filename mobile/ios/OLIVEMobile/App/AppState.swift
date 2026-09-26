import Foundation
import Observation

@MainActor @Observable
final class AppState {
    var destination: Destination { didSet { store.saveDestination(destination) } }
    var draft: String { didSet { saveDraft() } }
    var isSettingsPresented = false
    private(set) var persistenceNotice: String?
    var connection: MobileConnectionState { session?.connected == true ? .connected : session?.selected != nil ? .offline : .notPaired }
    let session: ConnectSession?
    private let chatConnection: (any ChatRemoteSession)?
    var preset = "normal"
    private(set) var chatStatus = ""
    private(set) var active = false
    private(set) var stopping = false
    private var chatTask: Task<Void, Never>?
    private var chatGeneration = UUID()
    private var currentUserID: UUID?
    private var currentAnswerID: UUID?
    private(set) var lastRequestID: String?
    private(set) var firstResponseSeconds: Double?
    private(set) var totalResponseSeconds: Double?
    private(set) var stopSeconds: Double?
    private var requestStarted = ContinuousClock.now
    private var history: [(String, String)] = []
    private(set) var messages: [ChatMessage] = []
    let connectClient: any ConnectClient
    let pairingService: any PairingService
    @ObservationIgnored private let store: any ShellStore
    @ObservationIgnored private var canWriteDraft = true
    var canSend: Bool { !active && chatConnection?.connected == true && chatConnection?.capability?["permission"].string != "deny" && chatConnection?.capability?["presets"][preset].boolean == true && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && draft.utf8.count <= 16000 }

    init(store: any ShellStore, connectClient: any ConnectClient = DisconnectedConnectClient(),
         pairingService: any PairingService = UnavailablePairingService(), session: ConnectSession? = nil, chatConnection: (any ChatRemoteSession)? = nil) {
        self.session = session
        self.chatConnection = chatConnection ?? session
        self.store = store
        self.connectClient = connectClient
        self.pairingService = pairingService
        destination = store.loadDestination()
        do { draft = try store.loadDraft() }
        catch {
            draft = ""
            canWriteDraft = false // Preserve an unreadable/newer file, never overwrite it.
            persistenceNotice = "Your saved draft could not be opened. New text stays here until you close OLIVE."
        }
    }
    func saveDraft() {
        guard canWriteDraft else { return }
        do { try store.saveDraft(draft); persistenceNotice = nil }
        catch { persistenceNotice = "Your draft could not be saved. Keep OLIVE open to retain this text." }
    }
    func send() {
        guard canSend, let client = chatConnection?.inference else { return }
        let text = draft, token = UUID(), answerID = UUID()
        let peerID = chatConnection?.selectedID ?? "", selectedPreset = preset
        requestStarted = .now; firstResponseSeconds = nil; totalResponseSeconds = nil; stopSeconds = nil
        chatGeneration = token; active = true; stopping = false; chatStatus = "Sending"
        let user = ChatMessage(id: UUID(), role: .user, blocks: [.text(text)])
        messages.append(user)
        currentUserID = user.id; currentAnswerID = answerID
        let context = Array((history + [("user", text)]).suffix(24))
        chatTask = Task {
            do {
                try await client.run(preset: selectedPreset, messages: context) { [self] job, status, answer in
                    await self.receive(token: token, answerID: answerID, draftSent: text, job: job, status: status, answer: answer, peerID: peerID, preset: selectedPreset)
                }
                guard chatGeneration == token else { return }
                if !stopping {
                    chatStatus = "Completed"
                    totalResponseSeconds = requestStarted.duration(to: .now).secondsValue
                    if let i = messages.firstIndex(where: { $0.id == answerID }) { messages[i].status = "Completed" }
                    if let answer = messages.first(where: { $0.id == answerID }) { history = Array((history + [("user", text), ("assistant", answer.plainText)]).suffix(24)) }
                }
            } catch {
                guard chatGeneration == token else { return }
                if !stopping { chatStatus = "Failed · " + (error as? ConnectFailure ?? .connectionLost).localizedDescription }
                if let i = messages.firstIndex(where: { $0.id == user.id }) { messages[i].status = chatStatus }
                if let i = messages.firstIndex(where: { $0.id == answerID }) { messages[i].status = "Incomplete" }
                // Restore the submitted text only if the user has not started a new draft.
                if draft.isEmpty { draft = text }
            }
            if chatGeneration == token && !stopping { active = false; chatTask = nil }
        }
    }
    private func receive(token: UUID, answerID: UUID, draftSent: String, job: String, status: String, answer: String, peerID: String, preset: String) {
        guard chatGeneration == token, !stopping else { return }
        if ["queued", "starting", "streaming"].contains(status), draft == draftSent { draft = "" }
        chatStatus = ["awaiting_approval": "Waiting for approval on computer", "queued": "Queued", "starting": "Starting", "streaming": "Receiving", "completed": "Completed"][status] ?? status
        lastRequestID = job
        if !answer.isEmpty {
            if firstResponseSeconds == nil { firstResponseSeconds = requestStarted.duration(to: .now).secondsValue }
            var message = ChatMessage(id: answerID, role: .assistant, blocks: ChatMessage.parse(answer))
            message.status = status == "completed" ? "Completed" : "Receiving"
            message.attribution = .init(deviceID: peerID, preset: preset, requestID: job)
            if let index = messages.firstIndex(where: { $0.id == answerID }) { messages[index] = message } else { messages.append(message) }
        }
    }
    func stop() {
        guard active, !stopping, let client = chatConnection?.inference else { return }
        stopping = true; chatStatus = "Stopping on computer…"
        let stopToken = chatGeneration
        let stopStarted = ContinuousClock.now
        let pendingTask = chatTask
        pendingTask?.cancel()
        Task {
            do {
                let terminal = try await client.stop()
                await pendingTask?.value
                guard chatGeneration == stopToken else { return }
                stopSeconds = stopStarted.duration(to: .now).secondsValue
                chatStatus = terminal == "cancelled" ? "Cancelled" : terminal == "completed" ? "Completed on computer · response may be incomplete" : terminal == "no_active_request" ? "No active request" : "Stopped · \(terminal)"
            } catch {
                guard chatGeneration == stopToken else { return }
                chatStatus = "Connection lost · Stop acknowledgement unavailable"
            }
            guard chatGeneration == stopToken else { return }
            markCurrentTurn(chatStatus)
            active = false; stopping = false; chatGeneration = UUID(); chatTask = nil
        }
    }
    private func markCurrentTurn(_ status: String) {
        for i in messages.indices where messages[i].id == currentUserID || messages[i].id == currentAnswerID { messages[i].status = status }
    }
    func activate() { session?.activate() }
    func suspend() {
        saveDraft()
        if active { chatStatus = "Interrupted · connection closed"; markCurrentTurn(chatStatus) }
        chatGeneration = UUID(); active = false; stopping = false; chatTask?.cancel(); chatTask = nil
        session?.suspend()
    }
    func openChat() { destination = .chat }
}

extension Duration {
    var secondsValue: Double { Double(components.seconds) + Double(components.attoseconds) / 1e18 }
}
