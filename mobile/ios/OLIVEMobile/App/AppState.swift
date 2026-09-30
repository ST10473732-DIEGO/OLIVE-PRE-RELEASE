import Foundation
import Observation
import UIKit

@MainActor @Observable
final class AppState {
    var destination: Destination { didSet { store.saveDestination(destination) } }
    var draft: String { didSet { draftRevision = UUID(); saveDraft() } }
    var isSettingsPresented = false
    private(set) var persistenceNotice: String?
    var connection: MobileConnectionState { session?.connected == true ? .connected : session?.selected != nil ? .offline : .notPaired }
    @ObservationIgnored lazy var sync = SyncModel(session: session, store: MobileSyncStore(directory: companionDirectory))
    @ObservationIgnored lazy var files = FilesModel(session: session, background: background, directory: companionDirectory.appendingPathComponent("Files"))
    @ObservationIgnored lazy var studio = StudioModel(session: session, background: background, directory: companionDirectory)
    /// OLIVE Notes: local-first; syncs over this session only when allowed on both sides.
    @ObservationIgnored lazy var notes = NotesModel(directory: companionDirectory)
    /// OLIVE Draw: local-first; syncs over this session only when allowed on both sides.
    @ObservationIgnored lazy var draw = DrawModel(directory: companionDirectory, defaults: drawDefaults)
    /// OLIVE DrawNote's current section (Notes | Draw), remembered on this phone only.
    var drawNoteSection: DrawNoteSection { didSet { store.saveDrawNoteSection(drawNoteSection) } }
    @ObservationIgnored private let drawDefaults: UserDefaults
    let companionDirectory: URL
    let background: BackgroundWorkCoordinator?
    let chatStore: MobileChatStore?
    let session: ConnectSession?
    private let chatConnection: (any ChatRemoteSession)?
    var preset = "normal"
    private(set) var chatStatus = ""
    private(set) var active = false
    private(set) var stopping = false
    private var chatTask: Task<Void, Never>?
    private var chatGeneration = UUID()
    private var draftRevision = UUID()
    private var admittedRequest: UUID?
    private var clearedDraftRevision: UUID?
    private var currentUserID: UUID?
    private var currentAnswerID: UUID?
    private(set) var lastRequestID: String?
    private(set) var firstResponseSeconds: Double?
    private(set) var totalResponseSeconds: Double?
    private(set) var stopSeconds: Double?
    private var requestStarted = ContinuousClock.now
    private var verifiedAnswer = ""
    private var history: [(String, String)] = []
    private(set) var messages: [ChatMessage] = []
    let connectClient: any ConnectClient
    let pairingService: any PairingService
    @ObservationIgnored private let store: any ShellStore
    @ObservationIgnored private var canWriteDraft = true
    var canSend: Bool { !active && background?.active == nil && background?.cancelling != true && chatConnection?.connected == true && chatConnection?.capability?["permission"].string != "deny" && chatConnection?.capability?["presets"][preset].boolean == true && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && draft.utf8.count <= 16000 }

    init(store: any ShellStore, connectClient: any ConnectClient = DisconnectedConnectClient(),
         pairingService: any PairingService = UnavailablePairingService(), session: ConnectSession? = nil, chatConnection: (any ChatRemoteSession)? = nil,
         drawDefaults: UserDefaults = .standard) {
        self.session = session
        self.drawDefaults = drawDefaults
        companionDirectory = store.companionDirectory ?? FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        background = session == nil ? nil : BackgroundWorkCoordinator(directory: companionDirectory)
        chatStore = session == nil ? nil : MobileChatStore(directory: companionDirectory)
        self.chatConnection = chatConnection ?? session
        self.store = store
        self.connectClient = connectClient
        self.pairingService = pairingService
        destination = store.loadDestination()
        drawNoteSection = store.loadDrawNoteSection()
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
        let sentDraftRevision = draftRevision
        let peerID = chatConnection?.selectedID ?? "", selectedPreset = preset
        verifiedAnswer = ""
        requestStarted = .now; firstResponseSeconds = nil; totalResponseSeconds = nil; stopSeconds = nil
        chatGeneration = token; admittedRequest = nil; clearedDraftRevision = nil
        active = true; stopping = false; chatStatus = "Sending"
        let user = ChatMessage(id: UUID(), role: .user, blocks: [.text(text)])
        messages.append(user)
        currentUserID = user.id; currentAnswerID = answerID
        let context = InferenceWire.context(history: history, user: text)
        let jobID = UUID().uuidString.lowercased()
        do {
            try background?.begin(BackgroundOperationRecord(id: jobID, capability: "models.remote", peerID: peerID,
                label: "Receiving response", protocolID: jobID,
                requestDigest: ConnectJSON.object(["preset": .string(selectedPreset), "messages": .array(context.map { .array([.string($0.0), .string($0.1)]) })]).digest, startedAt: Date())) { [weak self] in
                    await self?.interruptForBackground()
                }
        } catch { active = false; messages.removeAll { $0.id == user.id }; chatStatus = error.localizedDescription; return }
        chatTask = Task {
            do {
                try await client.run(preset: selectedPreset, jobID: jobID, messages: context) { [self] job, status, answer in
                    await self.receive(token: token, answerID: answerID, sentDraftRevision: sentDraftRevision, job: job, status: status, answer: answer, peerID: peerID, preset: selectedPreset)
                }
                guard chatGeneration == token else { return }
                if !stopping {
                    if messages.contains(where: { $0.id == answerID }) {
                        try chatStore?.append(MobileChatTurn(id: jobID, userID: user.id.uuidString.lowercased(),
                            assistantID: answerID.uuidString.lowercased(), peerID: peerID, preset: selectedPreset,
                            user: text, answer: verifiedAnswer, createdAt: Date()))
                    }
                    background?.finish(.completed, id: jobID)
                    session?.finishBackgroundWork()
                    chatStatus = "Completed"
                    totalResponseSeconds = requestStarted.duration(to: .now).secondsValue
                    if let i = messages.firstIndex(where: { $0.id == answerID }) { messages[i].status = "Completed" }
                    if messages.contains(where: { $0.id == answerID }) { history = Array((history + [("user", text), ("assistant", verifiedAnswer)]).suffix(24)) }
                }
            } catch {
                guard chatGeneration == token else { return }
                if !stopping {
                    let failure = error as? ConnectFailure ?? .connectionLost
                    if failure == .deviceRevoked { session?.recordRevocation(peerID: peerID) }
                    background?.finish(.interrupted, id: jobID, failure: failure)
                    session?.finishBackgroundWork(); chatStatus = "Failed · " + failure.localizedDescription
                }
                if let i = messages.firstIndex(where: { $0.id == user.id }) { messages[i].status = chatStatus }
                if let i = messages.firstIndex(where: { $0.id == answerID }) { messages[i].status = "Incomplete" }
                // Retain a failed request for explicit retry, but Stop must not
                // resurrect sent text or overwrite a newer draft.
                if !stopping, draft.isEmpty, draftRevision == clearedDraftRevision {
                    draft = text
                    chatStatus += " Draft restored; nothing was resent."
                }
            }
            if chatGeneration == token && !stopping { active = false; chatTask = nil }
        }
    }
    private func receive(token: UUID, answerID: UUID, sentDraftRevision: UUID, job: String, status: String, answer: String, peerID: String, preset: String) {
        guard chatGeneration == token, !stopping else { return }
        if admittedRequest != token, ["queued", "starting", "streaming", "completed"].contains(status) {
            admittedRequest = token
            if draftRevision == sentDraftRevision { draft = ""; clearedDraftRevision = draftRevision }
        }
        chatStatus = ["awaiting_approval": "Waiting for approval on computer", "queued": "Queued", "starting": "Starting", "streaming": "Receiving", "completed": "Completed"][status] ?? status
        verifiedAnswer = answer
        lastRequestID = job
        do { try background?.progress(Int64(answer.utf8.count), id: job) } catch { persistenceNotice = error.localizedDescription }
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
            background?.finish(.cancelled); session?.finishBackgroundWork()
            markCurrentTurn(chatStatus)
            active = false; stopping = false; chatGeneration = UUID(); chatTask = nil
        }
    }
    private func markCurrentTurn(_ status: String) {
        for i in messages.indices where messages[i].id == currentUserID || messages[i].id == currentAnswerID { messages[i].status = status }
    }
    func restoreCompletedChat() {
        guard !active, let chatStore else { return }
        let turns = chatStore.turns.filter { $0.peerID == session?.selectedID }.suffix(24)
        history = turns.flatMap { [("user", $0.user), ("assistant", $0.answer)] }
        messages = turns.flatMap { turn -> [ChatMessage] in
            guard let user = UUID(uuidString: turn.userID), let assistant = UUID(uuidString: turn.assistantID) else { return [] }
            return [ChatMessage(id: user, role: .user, blocks: [.text(turn.user)], status: "Completed"),
                ChatMessage(id: assistant, role: .assistant, blocks: ChatMessage.parse(turn.answer), status: "Completed",
                    attribution: .init(deviceID: turn.peerID, preset: turn.preset, requestID: turn.id))]
        }
    }
    func activate() {
        if messages.isEmpty { restoreCompletedChat() }
        background?.onIdle = { [weak self] in self?.session?.finishBackgroundWork() }
        session?.onChannelReady = { [weak self] channel, identity, peer in
            await self?.files.bind(channel: channel, local: identity.publicIdentity.deviceID, peer: peer.id)
            guard let self else { return }
            // Notes must speak as this phone's authenticated Connect identity.
            self.notes.start(deviceID: identity.publicIdentity.deviceID)
            await self.notes.sync.bind(channel: channel, peer: peer.id, capability: self.session?.notesCapability)
            // Draw records are made by the same authenticated identity; the probe,
            // hello and pumps run on their own tasks (never blocking Connect).
            self.draw.start(deviceID: identity.publicIdentity.deviceID)
            await self.draw.sync.bind(channel: channel, local: identity.publicIdentity.deviceID, peer: peer.id)
        }
        session?.onDisconnect = { [weak self] in self?.files.invalidate(); self?.notes.sync.invalidate(); self?.draw.sync.invalidate() }
        session?.onNotesCapability = { [weak self] value in self?.notes.sync.capabilityChanged(value) }
        startNotes()
        session?.activate()
    }
    private func startNotes() {
        guard notes.engine == nil || draw.engine == nil else { return }
        Task { [weak self] in
            guard let self else { return }
            let id = await self.session?.localDeviceID() ?? Self.notesLocalID()
            if self.notes.engine == nil { self.notes.start(deviceID: id) }
            self.notes.sync.remember(peer: self.session?.selectedID)
            if self.draw.engine == nil { self.draw.start(deviceID: id) }
            self.draw.sync.remember(peer: self.session?.selectedID)
        }
    }
    /// Before this phone has a Connect identity, Notes still works locally.
    private static func notesLocalID() -> String {
        let key = "olive.notes.localDevice"
        if let id = UserDefaults.standard.string(forKey: key), UUID(uuidString: id) != nil { return id }
        let id = UUID().uuidString.lowercased()
        UserDefaults.standard.set(id, forKey: key)
        return id
    }
    func suspend() {
        saveDraft()
        notes.flush() // Local persistence first; sync resumes on the next connection.
        // Draw: completed edits are already committed; finish any in-flight commit
        // under a short background assertion. Never waits for the computer.
        let drawAssertion = UIApplication.shared.beginBackgroundTask(withName: "OLIVE Draw save") {}
        Task { await draw.flush(); if drawAssertion != .invalid { UIApplication.shared.endBackgroundTask(drawAssertion) } }
        if background?.active != nil, background?.continuationGranted == true { session?.suspend(continuing: true); return }
        guard active || background?.active != nil else { session?.suspend(); return }
        session?.suspend(continuing: true) // Short cleanup retains only the existing active session.
        if active {
            chatGeneration = UUID() // Fence any outstanding Stop completion immediately.
            chatStatus = "Interrupted · connection closed"; markCurrentTurn(chatStatus)
        }
        // iOS17–25 (or denied continued processing): short cancellation/cleanup
        // only. This assertion never promises to finish long work.
        let assertion = UIApplication.shared.beginBackgroundTask(withName: "OLIVE cleanup") { [weak self] in
            Task { @MainActor in self?.session?.finishBackgroundWork() }
        }
        Task {
            await background?.cancel(expired: true, source: .noGrantAtBackground)
            await interruptForBackground()
            background?.finish(.interrupted)
            if assertion != .invalid { UIApplication.shared.endBackgroundTask(assertion) }
        }
    }
    private func interruptForBackground() async {
        if active {
            stopping = true; chatTask?.cancel()
            if let client = chatConnection?.inference { _ = try? await client.stop() }
            await chatTask?.value
            chatStatus = "Interrupted · connection closed"; markCurrentTurn(chatStatus)
        }
        chatGeneration = UUID(); active = false; stopping = false; chatTask = nil
        session?.finishBackgroundWork()
    }
    func openChat() { destination = .chat }
    /// Open-note navigation lands in DrawNote › Notes; Draw links land in Draw.
    func openNotes() { drawNoteSection = .notes; destination = .notes }
    func openDraw() { drawNoteSection = .draw; destination = .notes }
    var canClearChat: Bool { !active && !messages.isEmpty }
    /// Clears the visible conversation, its model context and this computer's saved iPhone history.
    func clearChat() {
        guard canClearChat else { return }
        if let chatStore, let peer = session?.selectedID {
            do { try chatStore.removeTurns(peerID: peer) }
            catch { chatStatus = "Chat history could not be cleared. Nothing was removed."; return }
        }
        messages = []; history = []; chatStatus = ""
    }
    #if DEBUG
    /// Isolated UI-test fixture only: a long synthetic conversation held in memory, never persisted.
    func prepareLongChatUIFixture() {
        messages = (1...24).flatMap { turn -> [ChatMessage] in
            let lines = (1...(turn % 5 == 0 ? 40 : 1 + turn % 4)).map { "Synthetic answer \(turn), line \($0)." }
            return [ChatMessage(id: UUID(), role: .user, blocks: [.text("Synthetic question \(turn)")]),
                    ChatMessage(id: UUID(), role: .assistant, blocks: ChatMessage.parse(lines.joined(separator: "\n")), status: "Completed")]
        }
    }
    #endif
}

extension Duration {
    var secondsValue: Double { Double(components.seconds) + Double(components.attoseconds) / 1e18 }
}
