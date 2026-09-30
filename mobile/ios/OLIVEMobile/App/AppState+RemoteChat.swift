import Foundation
import UIKit

/// Remote Chat v2 (olive-chat/1): every OLIVE mode on the user's computer, with
/// attachments and media results. The phone never runs a model and never falls
/// back to a hosted service: when the computer is offline, nothing is sent.
extension AppState {
    // MARK: Negotiated modes

    var chatCapabilities: ChatCapabilities? { chatConnection?.chatCapabilities }
    var selectedMode: ChatMode { ChatMode.named(preset) }
    var selectedCapability: RemoteModeCapability? { chatCapabilities?.mode(preset) }

    func availability(_ mode: ChatMode) -> ChatModeAvailability {
        guard let connection = chatConnection, connection.connected else { return .offline }
        if let capabilities = connection.chatCapabilities {
            if capabilities.permission == "deny" { return .permissionOff }
            guard let entry = capabilities.mode(mode.id) else { return .unsupportedComputer }
            return entry.available ? .available : .unavailable
        }
        // A computer without olive-chat/1 keeps its FAST/NORMAL/MAX (olive-inference/1).
        if connection.capability?["permission"].string == "deny" { return .permissionOff }
        guard ChatMode.legacy.contains(mode.id) else { return .unsupportedComputer }
        guard connection.inference != nil else { return .offline }
        return connection.capability?["presets"][mode.id].boolean == true ? .available : .unavailable
    }

    /// Why Send is refused, in the user's words; nil when sending is allowed.
    var sendBlocker: String? {
        let mode = selectedMode, state = availability(mode)
        guard state == .available else { return state == .offline ? "Computer offline" : state.explanation }
        if preparing > 0 { return "Preparing attachment…" }
        return attachmentProblem(for: mode) ?? (mode.id == "video" ? videoProblem : nil)
    }

    // MARK: VIDEO length

    /// VIDEO details the computer advertised (mode_options/1); nil from an older computer.
    var videoCapability: VideoCapability? { chatCapabilities?.mode("video")?.video }

    /// What the next VIDEO request asks for: the chosen length, else one stated in
    /// the prompt (the computer's own parser rules), else nil for its default.
    var videoTarget: (seconds: Double, source: String)? {
        guard let capability = videoCapability, capability.configurable else { return nil }
        if let chosen = videoDuration { return (chosen, "explicit") }
        if let stated = VideoDuration.parse(draft) { return (stated.seconds, "prompt") }
        return nil
    }

    /// Compact state for the composer: "Auto · 20 s", "20 s", "Auto".
    var videoDurationLabel: String {
        guard let target = videoTarget else {
            let fallback = videoCapability.map { " · " + VideoDuration.label(Double($0.defaultMS) / 1000) } ?? ""
            return "Auto" + fallback
        }
        return (target.source == "explicit" ? "" : "Auto · ") + VideoDuration.label(target.seconds)
    }

    /// Refused before sending, in the computer's configured terms.
    var videoProblem: String? {
        guard let target = videoTarget, let capability = videoCapability else { return nil }
        let ms = Int64((target.seconds * 1000).rounded())
        if ms < max(capability.minimumMS, 1) {
            return "Choose a video length of at least \(VideoDuration.label(Double(capability.minimumMS) / 1000))."
        }
        if ms > capability.maximumMS {
            return "VIDEO on this computer is limited to \(VideoDuration.label(Double(capability.maximumMS) / 1000)) per video. Choose a shorter length."
        }
        return nil
    }

    /// Factual expectation for long lengths; never an invented ETA.
    var videoPlanNote: String? {
        guard let target = videoTarget, let capability = videoCapability, videoProblem == nil else { return nil }
        let segments = capability.segments(forMS: Int64((target.seconds * 1000).rounded()))
        guard segments > 1 else { return nil }
        var note = "\(VideoDuration.label(target.seconds)) target · \(segments) generation segments"
        if Int64(target.seconds * 1000) >= capability.longWarningMS { note += " · may take several minutes" }
        return note
    }

    /// Revalidated whenever the mode or the attachments change; nothing is dropped silently.
    func attachmentProblem(for mode: ChatMode) -> String? {
        guard !draftAttachments.isEmpty else { return nil }
        guard let capability = chatCapabilities?.mode(mode.id) else {
            return mode.short + " can't use attachments with this computer's OLIVE yet."
        }
        if draftAttachments.count > ChatWire.maximumAttachments { return "Up to \(ChatWire.maximumAttachments) attachments per message." }
        var counts: [String: Int] = [:]
        for item in draftAttachments {
            let kind = item.descriptor.kind, limit = capability.maximum(kind)
            counts[kind, default: 0] += 1
            if limit == 0 {
                if mode.id == "video" {
                    return kind == "image" || capability.imageMax == 0
                        ? "VIDEO currently supports text prompts only. Remove the attachment or switch mode."
                        : "VIDEO accepts one starting image, not documents or notes. Remove the attachment or switch mode."
                }
                if mode.id == "now" { return "OLIVE NOW answers public questions only. Remove the attachment or switch mode." }
                return mode.short + " doesn't accept this attachment. Remove it or switch mode."
            }
            if kind == "document", !capability.documentMimes.contains(item.descriptor.mime) {
                return mode.short + " doesn't accept this file type on this computer."
            }
            if item.descriptor.size > capability.maximumBytes(kind) { return "This file is too large for OLIVE \(mode.short) on this computer." }
            if counts[kind, default: 0] > limit {
                if mode.id == "video", kind == "image" { return "OLIVE VIDEO currently accepts one starting image. Remove the extra image." }
                return mode.id == "reimagine" ? "REIMAGINE edits one image at a time. Remove the extra image."
                    : "Too many attachments for \(mode.short) (up to \(limit) of this kind)."
            }
        }
        return nil
    }

    func attachmentAccepted(_ item: StoredChatAttachment) -> Bool {
        guard let capability = selectedCapability else { return false }
        let kind = item.descriptor.kind
        return capability.maximum(kind) > 0 && item.descriptor.size <= capability.maximumBytes(kind)
            && (kind != "document" || capability.documentMimes.contains(item.descriptor.mime))
    }

    // MARK: Conversation and mode persistence

    func restoreConversation() {
        guard let chatStore, let peer = chatConnection?.selectedID ?? session?.selectedID else { return }
        let state = chatStore.session()
        restoringMode = true; defer { restoringMode = false }
        if let conversation = state.conversations[peer] {
            conversationID = conversation.id
            preset = ChatMode.all.contains(where: { $0.id == conversation.mode }) ? conversation.mode : "normal"
            voice = conversation.voice
        }
        if draftAttachments.isEmpty {
            draftAttachments = state.draftAttachments.filter { attachmentStore.item($0.id) != nil }
        }
    }

    func rememberMode() {
        guard !restoringMode else { return }
        saveSession()
    }

    func saveSession() {
        guard let chatStore, let peer = chatConnection?.selectedID ?? session?.selectedID else { return }
        var state = chatStore.session()
        state.conversations[peer] = .init(id: conversationID, mode: preset, voice: voice)
        state.draftAttachments = draftAttachments
        try? chatStore.saveSession(state)
    }

    /// A cleared chat is a new conversation in OLIVE NORMAL, like a new desktop chat.
    func startNewConversation() {
        conversationID = UUID().uuidString.lowercased()
        restoringMode = true; preset = "normal"; restoringMode = false
        videoDuration = nil
        saveSession()
        collectLocalFiles()
    }

    /// Unreferenced copies become eligible for cleanup; anything visible stays.
    func collectLocalFiles() {
        let turns = chatStore?.turns ?? []
        var referenced = Set(draftAttachments.map(\.id))
        referenced.formUnion(turns.flatMap { ($0.attachments ?? []).map(\.id) })
        referenced.formUnion((pending?.attachments ?? []).map(\.id))
        attachmentStore.collect(referenced: referenced)
        let artifacts = Set(turns.flatMap { ($0.artifacts ?? []).map(\.artifactID) })
        let store = mediaStore
        Task { await store.clear(keeping: artifacts) }
    }

    // MARK: Attachments

    func addAttachment(_ prepare: @escaping @Sendable (URL) throws -> PreparedAttachment) {
        guard draftAttachments.count < ChatWire.maximumAttachments else {
            attachmentNotice = "Up to \(ChatWire.maximumAttachments) attachments per message."; return
        }
        preparing += 1; attachmentNotice = nil
        let directory = attachmentStore.directory
        Task {
            let result = await Task.detached(priority: .userInitiated) { Result { try prepare(directory) } }.value
            preparing -= 1
            do {
                let stored = try attachmentStore.commit(try result.get())
                if !draftAttachments.contains(where: { $0.id == stored.id }) { draftAttachments.append(stored) }
                saveSession()
            } catch {
                attachmentNotice = (error as? ChatAttachmentFailure)?.message ?? "The attachment couldn't be prepared."
            }
        }
    }

    /// Removes the draft reference only. The photo, file, note or drawing is untouched.
    func removeAttachment(_ id: String) {
        draftAttachments.removeAll { $0.id == id }
        attachmentNotice = nil
        saveSession()
    }

    func attachNote(_ row: NoteRow) {
        guard let text = notes.text(of: row.id) else { attachmentNotice = "This note isn't available right now."; return }
        let id = row.id, title = row.displayTitle, edited = row.editedAt
        addAttachment { try AttachmentPreparation.note(id: id, title: title, text: text, editedAt: edited, directory: $0) }
    }

    func attachDrawing(_ summary: DrawSummary) {
        guard let engine = draw.engine else { attachmentNotice = "OLIVE Draw isn't available right now."; return }
        guard draftAttachments.count < ChatWire.maximumAttachments else {
            attachmentNotice = "Up to \(ChatWire.maximumAttachments) attachments per message."; return
        }
        preparing += 1; attachmentNotice = nil
        let directory = attachmentStore.directory
        Task {
            do {
                let ops = try await engine.visibleOperations(summary.id)
                var images: [String: CGImage] = [:]
                for asset in Set(ops.compactMap(\.assetID)) {
                    if let data = try await engine.assetData(asset) {
                        images[asset] = await Task.detached { DrawAssets.decode(data) }.value
                    }
                }
                let prepared = try await Task.detached(priority: .userInitiated) {
                    try AttachmentPreparation.drawing(id: summary.id, title: summary.title, revision: summary.revision, ops: ops,
                        width: summary.width, height: summary.height, background: summary.background, images: images, directory: directory)
                }.value
                let stored = try attachmentStore.commit(prepared)
                if !draftAttachments.contains(where: { $0.id == stored.id }) { draftAttachments.append(stored) }
                saveSession()
            } catch {
                attachmentNotice = (error as? ChatAttachmentFailure)?.message ?? "The drawing couldn't be prepared."
            }
            preparing -= 1
        }
    }

    /// The computer's advertised limit for this kind and type, or nil when no mode takes it.
    nonisolated static func limit(_ capabilities: ChatCapabilities?, kind: String, mime: String) -> Int64? {
        let modes = capabilities?.modes.filter { $0.maximum(kind) > 0 && (kind != "document" || $0.documentMimes.contains(mime)) } ?? []
        return modes.map { $0.maximumBytes(kind) }.max()
    }

    // MARK: Send

    func sendRemote() {
        let text = draft, mode = selectedMode, attached = draftAttachments
        let spokenVoice = mode.id == "audio" ? voice : nil
        let sentDraftRevision = draftRevision, token = UUID(), answerID = UUID()
        let peerID = chatConnection?.selectedID ?? "", jobID = UUID().uuidString.lowercased()
        let context = InferenceWire.context(history: history, user: text)
        let arguments: ConnectJSON
        // VIDEO length travels only to a computer that accepts options (mode_options/1).
        var options: ConnectJSON?, segments: Int?
        if mode.id == "video", chatCapabilities?.modeOptions == true {
            if let target = videoTarget, let capability = videoCapability {
                let ms = Int64((target.seconds * 1000).rounded())
                options = .object(["target_duration_ms": .int(ms), "duration_source": .string(target.source)])
                segments = capability.segments(forMS: ms)
            } else {
                options = .object([:])  // Auto: the computer applies its default.
            }
        }
        do {
            arguments = try ChatWire.startArguments(job: jobID, conversation: conversationID, mode: mode.id, voice: spokenVoice,
                                                    messages: context, attachments: attached.map(\.descriptor), options: options)
        } catch { chatStatus = ConnectFailure.inputTooLarge.localizedDescription; return }
        var user = ChatMessage(id: UUID(), role: .user, blocks: [.text(text)])
        user.attachments = attached
        var answer = ChatMessage(id: answerID, role: .assistant, blocks: [], status: attached.isEmpty ? "Sending…" : "Preparing…")
        answer.modeLabel = mode.short + " · This computer"
        messages.append(user); messages.append(answer)
        let record = PendingChatRequest(jobID: jobID, conversationID: conversationID, peerID: peerID, mode: mode.id, user: text,
            userID: user.id.uuidString.lowercased(), assistantID: answerID.uuidString.lowercased(), attachments: attached,
            accepted: false, stopRequested: false, received: "", createdAt: Date(), videoSegments: segments)
        pending = record; persistPending()
        currentUserID = user.id; currentAnswerID = answerID
        chatGeneration = token; admittedRequest = nil; clearedDraftRevision = nil
        requestStarted = .now; firstResponseSeconds = nil; totalResponseSeconds = nil
        active = true; stopping = false; remoteJob = jobID; lastRequestID = jobID
        chatStatus = "Sending"
        chatTask = Task { await self.runRemote(token: token, record: record, arguments: arguments, sentDraftRevision: sentDraftRevision) }
    }

    private func runRemote(token: UUID, record: PendingChatRequest, arguments: ConnectJSON, sentDraftRevision: UUID) async {
        let mode = ChatMode.named(record.mode)
        var startSent = false
        do {
            try await upload(record.attachments, token: token)
            startSent = true
            let view = try await start(arguments, attachments: record.attachments, token: token)
            guard chatGeneration == token else { return }
            admit(token: token, sentDraftRevision: sentDraftRevision, attachments: record.attachments)
            if view.state == "not_received" { throw ChatRemoteError(code: "request_indeterminate") }
            let (final, text) = try await follow(record, token: token)
            conclude(final, text: text, record: record, token: token)
        } catch {
            guard chatGeneration == token, !stopping else { return }
            if let remote = error as? ChatRemoteError, pending?.accepted != true {
                // Refused before any work began: nothing ran on the computer.
                failBeforeWork(ChatText.error(remote.code, mode: mode), record: record, token: token, sentDraftRevision: sentDraftRevision)
            } else if error as? ConnectFailure == .deviceRevoked {
                session?.recordRevocation(peerID: record.peerID)
                failBeforeWork(ConnectFailure.deviceRevoked.localizedDescription, record: record, token: token, sentDraftRevision: sentDraftRevision)
            } else if pending?.accepted == true || startSent {
                // The computer may hold this request (an acknowledgement can be lost). Keep it
                // pending and ask for its status on reconnect; never send it a second time.
                updateAnswer(record, status: "Connection lost. OLIVE will check this request when your computer reconnects.")
                chatStatus = "Waiting for your computer"
                active = false; chatTask = nil; remoteJob = nil
            } else {
                failBeforeWork("Your computer went offline before this was sent. Nothing was run; your draft is kept.",
                               record: record, token: token, sentDraftRevision: sentDraftRevision)
            }
        }
    }

    /// Retry an operation across a brief reconnect; typed refusals are returned at once.
    private func connected<T: Sendable>(_ token: UUID, within seconds: Int, _ body: @Sendable (RemoteChatClient) async throws -> T) async throws -> T {
        let deadline = ContinuousClock.now.advanced(by: .seconds(seconds))
        while true {
            try Task.checkCancellation()
            guard chatGeneration == token, !stopping else { throw CancellationError() }
            if let client = chatConnection?.chat, chatConnection?.connected == true {
                do { return try await body(client) }
                catch let failure as ConnectFailure where [.connectionLost, .peerOffline, .requestTimeout, .resourceBusy].contains(failure) {}
            }
            guard ContinuousClock.now < deadline else { throw ConnectFailure.connectionLost }
            chatStatus = "Reconnecting to your computer…"
            try await Task.sleep(for: .seconds(1))
        }
    }

    private func upload(_ attachments: [StoredChatAttachment], token: UUID) async throws {
        for (index, item) in attachments.enumerated() {
            let label = attachments.count > 1 ? "Sending attachment \(index + 1) of \(attachments.count)" : "Sending attachment"
            let file = attachmentStore.url(item.descriptor), size = item.descriptor.size
            chatStatus = label + "…"
            try await connected(token, within: 90) { client in
                try await client.upload(item.descriptor, file: file) { received in
                    await MainActor.run {
                        // Real byte progress: the size is known exactly.
                        let percent = size > 0 ? Int(Double(received) / Double(size) * 100) : 0
                        self.chatStatus = label + " · \(percent)%"
                    }
                }
            }
        }
    }

    private func start(_ arguments: ConnectJSON, attachments: [StoredChatAttachment], token: UUID) async throws -> ChatJobView {
        var uploadedAgain = false
        let approvalDeadline = ContinuousClock.now.advanced(by: .seconds(130))
        while true {
            do {
                // The same job id and content: a resend after a lost acknowledgement never runs twice.
                let view = try await connected(token, within: 90) { try await $0.start(arguments) }
                guard view.state == "awaiting_approval" else { return view }
                chatStatus = "Waiting for approval on your computer…"
                guard ContinuousClock.now < approvalDeadline else { throw ChatRemoteError(code: "confirmation_required") }
                try await Task.sleep(for: .seconds(1))
            } catch let error as ChatRemoteError where error.code == "attachment_missing" && !uploadedAgain {
                uploadedAgain = true  // The computer's staging expired; send the same bytes again.
                try await upload(attachments, token: token)
            }
        }
    }

    private func admit(token: UUID, sentDraftRevision: UUID, attachments: [StoredChatAttachment]) {
        guard chatGeneration == token else { return }
        admittedRequest = token
        pending?.accepted = true; persistPending()
        if draftRevision == sentDraftRevision { draft = ""; clearedDraftRevision = draftRevision }
        if draftAttachments == attachments { draftAttachments = []; saveSession() }
        chatStatus = "Sent"
    }

    /// Poll by UTF-8 byte offset: text already shown is never repeated, across
    /// reconnects and relaunches alike.
    private func follow(_ record: PendingChatRequest, token: UUID) async throws -> (ChatJobView, String) {
        let mode = ChatMode.named(record.mode)
        var text = pending?.received ?? ""
        var after = text.utf8.count
        let deadline = ContinuousClock.now.advanced(by: mode.patience(videoSegments: record.videoSegments))
        var saved = ContinuousClock.now
        while true {
            let offset = after
            let view = try await connected(token, within: 600) { try await $0.poll(job: record.jobID, after: offset) }
            guard chatGeneration == token, !stopping else { throw CancellationError() }
            text += view.text; after += view.text.utf8.count
            streamed = (record.jobID, text)
            if !view.text.isEmpty, firstResponseSeconds == nil { firstResponseSeconds = requestStarted.duration(to: .now).secondsValue }
            // Structured long-video progress ("segment 3 of 10") when the computer reports it.
            let phase = view.progress?.text ?? ChatText.phase(view.phase)
            updateAnswer(record, text: text, status: view.terminal ? nil : phase ?? (text.isEmpty ? "Working on your computer…" : "Receiving"))
            chatStatus = phase ?? (text.isEmpty ? "Working" : "Receiving")
            if ContinuousClock.now - saved > .seconds(2) { pending?.received = text; persistPending(); saved = .now }
            if view.state == "not_received" || (view.terminal && after >= view.total) { return (view, text) }
            guard ContinuousClock.now < deadline else { throw ConnectFailure.requestTimeout }
            try await Task.sleep(for: mode.isMedia && text.isEmpty ? .seconds(1) : .milliseconds(250))
        }
    }

    private func conclude(_ view: ChatJobView, text: String, record: PendingChatRequest, token: UUID) {
        guard chatGeneration == token else { return }
        let mode = ChatMode.named(record.mode)
        pending = nil; persistPending()
        totalResponseSeconds = requestStarted.duration(to: .now).secondsValue
        switch view.state {
        case "completed":
            let label = (view.attribution?.label ?? mode.short) + " · This computer"
            updateAnswer(record, text: text, status: "Completed", sources: view.sources, artifacts: view.artifacts, label: label)
            let turn = MobileChatTurn(id: record.jobID, userID: record.userID, assistantID: record.assistantID, peerID: record.peerID,
                preset: record.mode, user: record.user, answer: text, createdAt: Date(), conversationID: record.conversationID,
                attachments: record.attachments.isEmpty ? nil : record.attachments, sources: view.sources.isEmpty ? nil : view.sources,
                artifacts: view.artifacts.isEmpty ? nil : view.artifacts, attribution: view.attribution)
            do { try chatStore?.append(turn) } catch { persistenceNotice = "This answer could not be saved on this iPhone." }
            if !text.isEmpty { history = Array((history + [("user", record.user), ("assistant", text)]).suffix(24)) }
            chatStatus = "Completed"
            ensureMedia(view.artifacts)
        case "cancelled":
            updateAnswer(record, text: text, status: "Generation stopped.")
            chatStatus = "Stopped"
        case "not_received":
            updateAnswer(record, status: "Your computer never received this request. Nothing was run; your draft is restored.")
            restoreDraft(record)
            chatStatus = "Not sent"
        default:
            let message = ChatText.error(view.error ?? (view.state == "outcome_unknown" ? "request_indeterminate" : ""), mode: mode)
            updateAnswer(record, text: text, status: message)
            chatStatus = "Failed"
        }
        active = false; stopping = false; chatTask = nil; remoteJob = nil
    }

    private func failBeforeWork(_ message: String, record: PendingChatRequest, token: UUID, sentDraftRevision: UUID) {
        guard chatGeneration == token else { return }
        pending = nil; persistPending()
        updateAnswer(record, status: message.isEmpty ? "Your computer is offline. Nothing was run; your draft is kept." : message)
        if let index = messages.firstIndex(where: { $0.id.uuidString.lowercased() == record.userID }) { messages[index].status = "Not sent" }
        restoreDraft(record)
        chatStatus = "Not sent"
        active = false; stopping = false; chatTask = nil; remoteJob = nil
    }

    /// A refused or never-received request returns to the composer, never overwriting newer text.
    private func restoreDraft(_ record: PendingChatRequest) {
        if draft.isEmpty { draft = record.user }
        if draftAttachments.isEmpty { draftAttachments = record.attachments.filter { attachmentStore.item($0.id) != nil }; saveSession() }
    }

    func updateAnswer(_ record: PendingChatRequest, text: String? = nil, status: String?, sources: [ChatSource]? = nil,
                      artifacts: [ChatArtifact]? = nil, label: String? = nil) {
        guard let index = messages.firstIndex(where: { $0.id.uuidString.lowercased() == record.assistantID }) else { return }
        var message = messages[index]
        if let text { message = ChatMessage(id: message.id, role: .assistant, blocks: ChatMessage.parse(text), status: message.status,
            attribution: .init(deviceID: record.peerID, preset: record.mode, requestID: record.jobID),
            attachments: [], sources: message.sources, artifacts: message.artifacts, modeLabel: message.modeLabel) }
        message.status = status
        if let sources { message.sources = sources }
        if let artifacts { message.artifacts = artifacts }
        if let label { message.modeLabel = label }
        if messages[index] != message { messages[index] = message }
    }

    func persistPending() {
        do { try chatStore?.savePending(pending) } catch { persistenceNotice = "This request's status could not be saved on this iPhone." }
    }

    // MARK: Stop

    /// Stop reaches the computer's task; if the phone is offline, it is sent on reconnect.
    /// The original request is never resubmitted, and no late result is attached.
    func stopRemote() {
        guard active, !stopping, let job = remoteJob else { return }
        stopping = true; chatStatus = "Stopping on your computer…"
        pending?.stopRequested = true; persistPending()
        let token = chatGeneration, running = chatTask
        running?.cancel()
        Task {
            var confirmed = false
            if let client = chatConnection?.chat, chatConnection?.connected == true {
                confirmed = (try? await client.cancel(job: job)) != nil
            }
            await running?.value
            guard chatGeneration == token else { return }
            if let record = pending {
                updateAnswer(record, status: confirmed ? "Generation stopped." : "Stop requested. OLIVE stops it when your computer reconnects.")
            }
            if confirmed { pending = nil; persistPending() }
            chatStatus = confirmed ? "Stopped" : "Stop pending"
            active = false; stopping = false; chatGeneration = UUID(); chatTask = nil; remoteJob = nil
        }
    }

    // MARK: Background, relaunch and reconnect

    func pauseRemote() {
        chatTask?.cancel(); chatTask = nil
        chatGeneration = UUID()
        // The exact UTF-8 text received so far: the resume offset must match the computer's bytes.
        if let record = pending, streamed.job == record.jobID { pending?.received = streamed.text }
        persistPending()
        chatStatus = "Continues on your computer"
        active = false; stopping = false; remoteJob = nil
    }

    /// After a relaunch: show the in-flight request and ask the computer about it.
    func restorePending() {
        guard let record = chatStore?.pending(), record.peerID == (chatConnection?.selectedID ?? session?.selectedID) else { return }
        pending = record
        if !messages.contains(where: { $0.id.uuidString.lowercased() == record.userID }),
           let user = UUID(uuidString: record.userID), let assistant = UUID(uuidString: record.assistantID) {
            var asked = ChatMessage(id: user, role: .user, blocks: [.text(record.user)]); asked.attachments = record.attachments
            var answer = ChatMessage(id: assistant, role: .assistant, blocks: ChatMessage.parse(record.received), status: "Checking with your computer…")
            answer.modeLabel = ChatMode.named(record.mode).short + " · This computer"
            messages += [asked, answer]
        }
        remoteChatReady()
    }

    func remoteChatReady() {
        ensureMedia(messages.flatMap(\.artifacts))
        guard !active, let record = pending, chatConnection?.chat != nil, chatConnection?.connected == true,
              record.peerID == chatConnection?.selectedID else { return }
        let token = UUID()
        chatGeneration = token; active = true; stopping = false; remoteJob = record.jobID
        currentAnswerID = UUID(uuidString: record.assistantID); currentUserID = UUID(uuidString: record.userID)
        requestStarted = .now
        chatTask = Task {
            do {
                if record.stopRequested, let client = chatConnection?.chat {
                    // Stop was pressed while offline: deliver it now; never resubmit.
                    // Stop wins: even a result that finished meanwhile is not attached.
                    _ = try await client.cancel(job: record.jobID)
                    conclude(ChatJobView(jobID: record.jobID, state: "cancelled", phase: "", text: "", offset: 0, total: 0,
                        sources: [], artifacts: [], attribution: nil, error: "cancelled"), text: record.received, record: record, token: token)
                    return
                }
                let (final, text) = try await follow(record, token: token)
                if final.state == "not_received" && record.accepted {
                    // Accepted before, unknown now: tell the user rather than regenerating.
                    conclude(ChatJobView(jobID: record.jobID, state: "outcome_unknown", phase: "", text: "", offset: 0, total: 0,
                        sources: [], artifacts: [], attribution: nil, error: "request_indeterminate"), text: text, record: record, token: token)
                } else {
                    conclude(final, text: text, record: record, token: token)
                }
            } catch {
                guard chatGeneration == token, !stopping else { return }
                updateAnswer(record, status: "Connection lost. OLIVE will check this request when your computer reconnects.")
                chatStatus = "Waiting for your computer"
                active = false; chatTask = nil; remoteJob = nil
            }
        }
    }

    // MARK: Media results

    /// Download results that are not on this iPhone yet. Resumes partial transfers;
    /// never asks the computer to generate again.
    func ensureMedia(_ artifacts: [ChatArtifact]) {
        for artifact in artifacts where artifact.known && mediaFiles[artifact.id] == nil {
            if let url = mediaStore.available(artifact) { mediaFiles[artifact.id] = url; continue }
            guard downloads[artifact.id] == nil, let client = chatConnection?.chat, chatConnection?.connected == true else { continue }
            mediaFailures[artifact.id] = nil
            mediaProgress[artifact.id] = mediaStore.received(artifact)
            let store = mediaStore
            downloads[artifact.id] = Task {
                do {
                    let url = try await store.download(artifact, fetch: { offset in
                        try await client.artifactChunk(artifact, offset: offset, length: ChatWire.chunkBytes)
                    }, progress: { received in await MainActor.run { self.mediaProgress[artifact.id] = received } })
                    mediaFiles[artifact.id] = url
                } catch let failure as ChatMediaFailure {
                    mediaFailures[artifact.id] = failure.message
                } catch let remote as ChatRemoteError {
                    mediaFailures[artifact.id] = ChatText.error(remote.code, mode: ChatMode.named(artifact.mode))
                } catch {
                    mediaFailures[artifact.id] = "Transfer interrupted. It resumes when your computer is connected."
                }
                mediaProgress[artifact.id] = nil
                downloads[artifact.id] = nil
            }
        }
    }

    func retryMedia(_ artifact: ChatArtifact) {
        mediaFailures[artifact.id] = nil
        ensureMedia([artifact])
    }

    /// User-initiated: remove downloaded Chat media from this iPhone. Chat text,
    /// Notes and Draw are untouched; the computer keeps the originals.
    func clearDownloadedMedia() async {
        for task in downloads.values { task.cancel() }
        downloads = [:]
        await mediaStore.clear(keeping: [])
        mediaFiles = [:]; mediaProgress = [:]; mediaFailures = [:]
    }
}
