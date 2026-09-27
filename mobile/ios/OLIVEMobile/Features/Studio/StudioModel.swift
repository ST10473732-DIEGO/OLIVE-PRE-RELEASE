import Foundation
import Observation

@MainActor @Observable
final class StudioModel {
    private let session: ConnectSession?
    private let background: BackgroundWorkCoordinator?
    private(set) var workspaces: [ConnectJSON] = []
    private(set) var entries: [ConnectJSON] = []
    private(set) var workspace: ConnectJSON?
    private(set) var filePath: String?
    private(set) var revision: String?
    struct Draft: Codable { let peer: String; let workspace: String; let path: String; let revision: String; let original: String; let text: String }
    private let draftStore: ProtectedStore<[String: Draft]>
    private var drafts: [String: Draft] = [:]
    private var draftsAvailable = true
    private var loading = false
    private var editorPeer: String?
    var text = "" { didSet { persistDraft() } }
    private(set) var remoteText: String?
    private func persistDraft() {
        guard !loading, let peer = editorPeer, let workspaceID = workspace?["workspace_id"].string, let filePath, let revision else { return }
        guard draftsAvailable, text.utf8.count <= 64000 else { notice = "Draft storage unavailable or editor limit reached."; return }
        let key = peer + ":" + workspaceID + ":" + filePath
        var next = drafts
        if dirty { next[key] = Draft(peer: peer, workspace: workspaceID, path: filePath, revision: revision, original: original, text: text) }
        else { next.removeValue(forKey: key) }
        do {
            guard next.count <= 64 else { throw ConnectFailure.localStorageUnavailable }
            try draftStore.save(next); drafts = next
        } catch { notice = ConnectFailure.localStorageUnavailable.localizedDescription }
    }
    private(set) var original = ""
    var dirty: Bool { text != original }
    private(set) var notice = ""
    private(set) var output = ""
    private(set) var busy = false
    private(set) var running = false
    private var channel: ConnectTransport?
    private var jobRequest: ConnectJSON?
    private var cancelRequested = false
    init(session: ConnectSession?, background: BackgroundWorkCoordinator?, directory: URL = URL.applicationSupportDirectory.appendingPathComponent("Companion")) {
        self.session = session; self.background = background
        draftStore = ProtectedStore(url: directory.appendingPathComponent("studio-drafts-v1.json"), maximumBytes: 8_000_000)
        do { drafts = try draftStore.load() ?? [:]; guard drafts.count <= 64 else { throw ConnectFailure.localStorageUnavailable } }
        catch { draftsAvailable = false; notice = "Saved drafts unavailable; existing data preserved." }
    }
    var available: Bool { session?.connected == true }
    func allowed(_ capability: String) -> Bool { workspace?["permissions"]["studio." + capability].string != "deny" && available }
    private func request(_ operation: String, arguments: ConnectJSON = .object([:])) async throws -> (ConnectJSON, ConnectTransport) {
        guard let session else { throw ConnectFailure.peerOffline }
        let (channel, identity, peer) = try await session.context()
        return (try StudioWire.request(source: identity.publicIdentity.deviceID, target: peer.id, operation: operation,
            workspace: operation == "workspaces" ? nil : workspace?["workspace_id"].string,
            revision: operation == "workspaces" ? 0 : workspace?["share_revision"].integer ?? 0, arguments: arguments), channel)
    }
    private func exchange(_ operation: String, arguments: ConnectJSON = .object([:])) async throws -> ConnectJSON {
        let (request, channel) = try await request(operation, arguments: arguments)
        return try await StudioWire.exchange(request, channel: channel)
    }
    func refresh() async {
        guard !busy, !running else { return }; busy = true; defer { busy = false }
        do { workspaces = try await exchange("workspaces")["workspaces"].array ?? []; notice = workspaces.isEmpty ? "No workspaces shared with this iPhone." : "" }
        catch { notice = error.localizedDescription }
    }
    func open(_ item: ConnectJSON) async {
        guard !dirty, !busy, !running else { notice = "Save or discard your draft first."; return }
        workspace = item; filePath = nil; revision = nil; entries = []; text = ""; original = ""
        busy = true; defer { busy = false }
        do { let r = try await exchange("tree"); entries = r["entries"].array ?? []; notice = r["truncated"].boolean == true ? "The bounded tree has more files than can be displayed." : "" }
        catch { notice = error.localizedDescription }
    }
    func read(_ path: String) async {
        guard !dirty, !busy, !running else { notice = "Save or discard your draft first."; return }
        busy = true; defer { busy = false }
        do {
            let result = try await exchange("read", arguments: .object(["path": .string(path)]))
            loading = true
            filePath = path; editorPeer = session?.selectedID; revision = result["revision"].string; original = try result["text"].text(); text = original; notice = ""; remoteText = nil
            if let peer = editorPeer, let workspaceID = workspace?["workspace_id"].string,
               let draft = drafts[peer + ":" + workspaceID + ":" + path] {
                remoteText = revision == draft.revision ? nil : original
                revision = draft.revision; original = draft.original; text = draft.text
                notice = remoteText == nil ? "Restored unsaved local draft" : "Revision conflict · draft retained; discard to reload computer version"
            }
            loading = false
        } catch { notice = error.localizedDescription }
    }
    func save() async {
        guard !busy, !running, remoteText == nil, session?.selectedID == editorPeer, let filePath, let revision else { return }
        busy = true; defer { busy = false }
        let savedText = text
        do {
            let r = try await exchange("save", arguments: .object(["path": .string(filePath), "text": .string(savedText), "expected_hash": .string(revision)]))
            guard r["state"] == .string("saved") else { throw ConnectFailure.connectionLost }
            self.revision = try r["revision"].text(); original = savedText; persistDraft(); notice = "Saved and revision verified."
        } catch { notice = error.localizedDescription }
    }
    func discard() {
        text = original
        if let remoteText { self.remoteText = nil; original = remoteText; text = remoteText; revision = nil
            if let filePath { Task { await read(filePath) } }
        }
    }
    func run(_ operation: String) async {
        guard !running, !busy, !dirty, ["build", "test", "run"].contains(operation) else { return }
        running = true; cancelRequested = false; output = ""; defer { running = false; jobRequest = nil; channel = nil; session?.finishBackgroundWork() }
        do {
            let (req, transport) = try await request(operation)
            channel = transport; jobRequest = req
            let id = try req["request_id"].uuid()
            try background?.begin(BackgroundOperationRecord(id: id, capability: "studio." + operation,
                peerID: try req["target_device_id"].uuid(), label: operation == "test" ? "Running tests" : operation == "build" ? "Building project" : "Running project",
                protocolID: id, requestDigest: req.digest, startedAt: Date())) { [weak self] in
                    guard let self else { return }
                    await self.channel?.close() // C8 disconnect cancels the channel-owned job.
                    self.notice = "Interrupted · original session ended"
                    self.session?.finishBackgroundWork()
                }
            var result = try await StudioWire.exchange(req, channel: transport)
            let deadline = ContinuousClock.now.advanced(by: .seconds(600))
            while ["starting", "running", "cancelling"].contains(result["state"].string ?? "") {
                notice = result["state"].string ?? "Running"
                if let value = result["output"].string { output = value }
                guard ContinuousClock.now < deadline else { await transport.close(); throw ConnectFailure.requestTimeout }
                try await Task.sleep(for: .seconds(1))
                let poll = try StudioWire.request(source: req["source_device_id"].uuid(), target: req["target_device_id"].uuid(),
                    operation: cancelRequested ? "run_cancel" : "run_status", workspace: req["workspace_id"].uuid(),
                    revision: req["share_revision"].number(1...Int64.max), arguments: .object(["job_id": .string(id)]))
                result = try await StudioWire.exchange(poll, channel: transport)
            }
            output = result["output"].string ?? output
            notice = result["state"].string ?? "Unknown result"
            background?.finish(result["state"] == .string("completed") ? .completed : result["state"] == .string("cancelled") ? .cancelled : .failed, id: id)
        } catch { notice = error.localizedDescription; if let id = jobRequest?["request_id"].string { background?.finish(.interrupted, id: id) } }
    }
    func cancel() { cancelRequested = true; notice = "Cancelling on computer…" }
}
