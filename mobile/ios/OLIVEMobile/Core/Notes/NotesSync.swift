import Foundation
import Observation

/// OLIVE Notes over the existing OLIVE Connect session (frames 13/14).
///
/// Only the paired, authenticated computer this phone selected takes part, and
/// only when (a) Notes sync is on here and (b) the computer reports Notes sync
/// Allow for this phone. Pushes are near-instant while the app is foreground
/// and connected; iOS suspends the socket in the background, so pending edits
/// stay in the durable change feed and sync on the next connection.
@MainActor @Observable
final class NotesSync {
    enum State: Equatable { case off, unsupported, notAllowed, offline, syncing, synced, error(String) }
    private(set) var state: State = .offline
    private(set) var pending = 0
    private(set) var lastSync: String?
    var enabled: Bool {
        didSet { UserDefaults.standard.set(enabled, forKey: Self.key); if enabled { kick() } else { state = .off } }
    }
    static let key = "olive.notes.sync"
    @ObservationIgnored private weak var engine: NotesEngineHost?
    @ObservationIgnored private var transport: ConnectTransport?
    @ObservationIgnored private var peer: String?
    @ObservationIgnored private var capability: ConnectJSON?
    @ObservationIgnored private var bound = UUID()
    @ObservationIgnored private var dirty = false
    @ObservationIgnored private var pumping = false
    @ObservationIgnored private var failures = 0

    init() {
        enabled = UserDefaults.standard.object(forKey: Self.key) as? Bool ?? true
        state = enabled ? .offline : .off
    }

    func attach(engine: NotesEngineHost) { self.engine = engine }

    /// The paired computer this phone syncs with, known before any connection,
    /// so edits made offline (or before a relaunch) are counted as pending.
    func remember(peer: String?) {
        guard transport == nil, let peer else { return }
        self.peer = peer
        refreshState()
    }

    var permitted: Bool { capability?["permission"] == .string("allow") }

    /// Called when the Connect channel is ready (and after each capability refresh).
    func bind(channel: ConnectTransport, peer: String, capability: ConnectJSON?) async {
        let token = UUID(); bound = token
        transport = channel; self.peer = peer; self.capability = capability; failures = 0
        await channel.setNotesInbound { [weak self] frame in
            guard let self else { throw ConnectFailure.peerOffline }
            return try await self.inbound(frame, token: token)
        }
        refreshState()
        kick()
    }

    func capabilityChanged(_ value: ConnectJSON?) {
        capability = value
        refreshState()
        kick()
    }

    func invalidate() {
        bound = UUID()
        if let peer { _ = try? engine?.call("disconnected", peer) }
        transport = nil; capability = nil
        refreshState()
    }

    private func refreshState() {
        if !enabled { state = .off; return }
        guard transport != nil else { state = .offline; updatePending(); return }
        if capability == nil { state = .unsupported; return }
        if !permitted { state = .notAllowed; return }
        updatePending()
        if case .error = state { return }
        state = pending > 0 ? .syncing : .synced
    }

    private func updatePending() {
        guard let peer, let status = try? engine?.call("status", peer) else { return }
        pending = Int(status["pending"].integer ?? 0)
        lastSync = status["last_sync"].string
    }

    /// Local edits and peer contact call this; bursts are coalesced (~40 ms).
    func kick() {
        dirty = true
        guard !pumping, enabled, transport != nil, permitted else { refreshState(); return }
        pumping = true
        Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(40))
            await self?.run()
        }
    }

    private func run() async {
        defer { pumping = false; refreshState() }
        while dirty {
            dirty = false
            guard let engine, let transport, let peer, enabled, permitted else { return }
            let token = bound
            state = .syncing
            for _ in 0..<96 {
                guard token == bound else { return }
                let step: ConnectJSON
                do { step = try ConnectJSON.decode(Data(try engine.raw("next", peer).utf8), limit: 600_000) }
                catch { state = .error("notes_unavailable"); return }
                if step["done"] != .null || step["wait"] != .null { break }
                guard let ticket = step["ticket"].string else { state = .error("notes_unavailable"); return }
                let request = step["request"].canonical
                do {
                    let response = try await transport.exchangeFrame(kind: 13, id: ticket, payload: request)
                    _ = try ConnectJSON.decode(response, limit: 512_000) // strict: duplicate keys, number forms
                    let answer = try ConnectJSON.decode(Data(try engine.raw("answer", peer, ticket, String(decoding: response, as: UTF8.self)).utf8))
                    if let code = answer["error"].string {
                        state = code == "permission_off" ? .notAllowed : .error(code)
                        return
                    }
                    failures = 0
                } catch {
                    _ = try? engine.call("fail", peer, (error as? ConnectFailure)?.rawValue ?? "connection_lost")
                    failures += 1
                    state = .offline
                    if failures <= 3, token == bound {
                        // Retry the transport, never the edit: it is already durable.
                        try? await Task.sleep(for: .seconds(Double(1 << failures)))
                        dirty = true
                    }
                    break
                }
            }
        }
    }

    private func inbound(_ frame: ConnectFrame, token: UUID) async throws -> ConnectFrame {
        guard token == bound, let engine, let peer else { throw ConnectFailure.peerOffline }
        let request = try ConnectJSON.decode(frame.payload, limit: 512_000)
        let id = request["request_id"].string.flatMap { UUID(uuidString: $0) != nil ? $0 : nil }
        guard enabled else {
            // This phone's own switch is Off: answer, but share nothing.
            return ConnectFrame(kind: 14, payload: ConnectJSON.object(["protocol_version": .string("olive-notes/1"),
                "request_id": id.map { .string($0) } ?? .null, "state": .string("rejected"), "error": .string("permission_off")]).canonical)
        }
        let response = try engine.raw("handle", peer, String(decoding: frame.payload, as: UTF8.self))
        kick()   // The computer is here and talking: send anything this phone has too.
        return ConnectFrame(kind: 14, payload: Data(response.utf8))
    }
}
