import Foundation
import Observation

/// OLIVE Draw over the existing OLIVE Connect session (frames 15/16, olive-draw/1).
///
/// Negotiation (desktop compatibility design): an older desktop closes a channel
/// on an unknown frame type, so this phone first asks the read-only
/// `connect.ping` / `protocols` probe on the ordinary request frame. Only a
/// desktop that lists `olive-draw/1` ever receives a Draw frame; the phone then
/// speaks first (`hello`), which tells the desktop this phone supports Draw.
/// Older desktops answer the probe with a normal rejection and keep the channel.
///
/// Content flows only when this phone's switch is on AND the computer allows
/// `sync.draw` for this phone (Off by default on the computer; Notes permission
/// never implies it). Completed edits are durable on the phone before anything
/// is sent; the durable feed plus per-peer cursors is the outbox. There is no
/// polling: local edits and desktop requests trigger pumps.
/// The part of an authenticated Connect channel Draw uses (ConnectTransport;
/// a fake desktop in unit tests). No second socket exists.
protocol DrawChannel: AnyObject, Sendable {
    func exchangeFrame(kind: UInt8, id: String, payload: Data) async throws -> Data
    func setDrawInbound(_ handler: (@Sendable (ConnectFrame) async -> ConnectFrame)?) async
}

extension ConnectTransport: DrawChannel {}

@MainActor @Observable
final class DrawSync {
    enum State: Equatable { case off, checking, unsupported, notAllowed, offline, syncing, synced, error(String) }
    private(set) var state: State = .offline
    private(set) var pending = 0
    private(set) var pendingAssets = 0
    private(set) var lastSync: String?
    private(set) var refused = 0
    var enabled: Bool {
        didSet {
            defaults.set(enabled, forKey: Self.key)
            if enabled { start(token: bound) } else { if let peer, let engine { Task { await engine.forget(peer) } }; refreshState() }
        }
    }
    static let key = "olive.draw.sync"
    @ObservationIgnored private let defaults: UserDefaults
    @ObservationIgnored private var engine: DrawEngine?
    @ObservationIgnored private var transport: (any DrawChannel)?
    @ObservationIgnored private var local: String?
    @ObservationIgnored private var peer: String?
    @ObservationIgnored private var bound = UUID()
    /// nil: not known yet; true: the computer speaks olive-draw/1.
    @ObservationIgnored private var supported: Bool?
    /// nil: not known yet; false: the computer answered permission_off.
    @ObservationIgnored private var permitted: Bool?
    @ObservationIgnored private var helloDone = false
    @ObservationIgnored private var dirty = false
    @ObservationIgnored private var pumping = false
    @ObservationIgnored private var failures = 0
    @ObservationIgnored private var lastError: String?
    /// Latency of the last completed pump (diagnostics only).
    private(set) var lastPumpMilliseconds: Int?

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        enabled = defaults.object(forKey: Self.key) as? Bool ?? true
        state = enabled ? .offline : .off
    }

    func attach(engine: DrawEngine) { self.engine = engine; refreshState() }

    /// The paired computer, known before any connection, so edits made offline
    /// (or before a relaunch) are counted as waiting.
    func remember(peer: String?) {
        guard transport == nil, let peer else { return }
        self.peer = peer
        refreshState()
    }

    /// The Connect channel is ready: install the frame-15 handler, then probe.
    func bind(channel: any DrawChannel, local: String, peer: String) async {
        let token = UUID(); bound = token
        transport = channel; self.local = local; self.peer = peer
        supported = nil; permitted = nil; helloDone = false; failures = 0; lastError = nil
        await engine?.setDevice(local)
        await channel.setDrawInbound { [weak self] frame in
            guard let self else {
                return ConnectFrame(kind: DrawProtocol.responseFrame, payload: DrawProtocol.encodeResponse(
                    requestID: DrawProtocol.requestID(of: frame.payload), error: "draw_unavailable"))
            }
            return await self.inbound(frame, token: token)
        }
        refreshState()
        start(token: token)
    }

    func invalidate() {
        bound = UUID()
        if let peer, let engine { Task { await engine.forget(peer) } }
        transport = nil; supported = nil; permitted = nil; helloDone = false
        refreshState()
    }

    private func start(token: UUID) {
        guard enabled, token == bound, transport != nil else { refreshState(); return }
        Task { [weak self] in
            guard let self else { return }
            if self.supported == nil { await self.probe(token: token) }
            self.kick()
        }
    }

    /// Read-only probe on the ordinary request frame; grants nothing.
    private func probe(token: UUID) async {
        guard let transport, let local, let peer, token == bound else { return }
        state = .checking
        let now = DrawWire.now()
        let id = UUID().uuidString.lowercased()
        let request = ConnectJSON.object(["request_id": .string(id), "protocol_version": .string("olive-connect/1"),
            "source_device_id": .string(local), "target_device_id": .string(peer), "capability": .string("connect.ping"),
            "operation": .string("protocols"), "arguments": .object([:]), "timestamp": .int(now), "expires_at": .int(now + 60)])
        do {
            let raw = try await transport.exchangeFrame(kind: 1, id: id, payload: request.canonical)
            guard token == bound else { return }
            let value = try ConnectJSON.decode(raw, limit: 16_384)
            let protocols = value["state"] == .string("completed") ? value["result"]["protocols"].array ?? [] : []
            supported = protocols.contains(.string(DrawProtocol.name))
        } catch {
            guard token == bound else { return }
            // Timeouts or a lost channel are not an answer; the next connection asks again.
            lastError = (error as? ConnectFailure)?.rawValue ?? "connection_lost"
        }
        refreshState()
    }

    /// Local edits and computer contact call this; bursts are coalesced (~30 ms).
    func kick() {
        dirty = true
        guard enabled, transport != nil, supported == true, permitted != false else { refreshState(); return }
        state = .syncing   // "Synced" is only shown again once the computer has acknowledged everything.
        guard !pumping else { return }
        pumping = true
        Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(30))
            await self?.run()
        }
    }

    private func run() async {
        defer { pumping = false; refreshState() }
        while dirty {
            dirty = false
            guard let engine, let transport, let local, let peer, enabled, supported == true, permitted != false else { return }
            let token = bound
            state = .syncing
            let started = ContinuousClock.now
            let send = DrawWire.sender(local: local, peer: peer, clock: { DrawWire.now() }) { id, raw in
                try await transport.exchangeFrame(kind: DrawProtocol.requestFrame, id: id, payload: raw)
            }
            do {
                let outcome = try await engine.pump(peer: peer, hello: !helloDone, send: send, keepGoing: { @MainActor [weak self] in
                    self?.bound == token && self?.enabled == true
                })
                guard token == bound else { return }
                helloDone = true; permitted = true; failures = 0; lastError = nil
                let elapsed = started.duration(to: .now)
                lastPumpMilliseconds = Int(elapsed.components.seconds * 1000 + elapsed.components.attoseconds / 1_000_000_000_000_000)
                if outcome == "partial" { dirty = true }
            } catch let failure as DrawProtocol.Failure {
                guard token == bound else { return }
                lastError = failure.code
                switch failure.code {
                case "permission_off", "device_not_paired", "identity_mismatch": permitted = false; return
                case "unsupported_protocol": supported = false; return
                default:
                    failures += 1
                    if failures <= 3 { try? await Task.sleep(for: .seconds(Double(1 << failures))); dirty = token == bound }
                }
            } catch {
                guard token == bound else { return }
                lastError = (error as? ConnectFailure)?.rawValue ?? "connection_lost"
                failures += 1
                // Retry the transport, never the edit: it is already durable here.
                if failures <= 3 { try? await Task.sleep(for: .seconds(Double(1 << failures))); dirty = token == bound }
            }
        }
    }

    /// A desktop-initiated olive-draw/1 request (frame 15). Always answered.
    private func inbound(_ frame: ConnectFrame, token: UUID) async -> ConnectFrame {
        let requestID = DrawProtocol.requestID(of: frame.payload)
        guard token == bound, let engine, let local, let peer else {
            return ConnectFrame(kind: DrawProtocol.responseFrame, payload: DrawProtocol.encodeResponse(requestID: requestID, error: "draw_unavailable"))
        }
        // This phone's own switch Off: answer, but share nothing.
        let response = await DrawWire.receive(engine: engine, raw: frame.payload, peer: peer, local: local, permitted: enabled, now: DrawWire.now())
        if enabled && token == bound {
            // The computer only sends Draw frames when it speaks olive-draw/1 and
            // allows sync.draw for this phone: send anything this phone has too.
            supported = true
            if permitted == false { permitted = nil; helloDone = false }
            kick()
        }
        return ConnectFrame(kind: DrawProtocol.responseFrame, payload: response)
    }

    func refreshState() {
        guard enabled else { state = .off; return }
        Task { await refreshCounts() }
        guard transport != nil else { state = .offline; return }
        if supported == nil { state = .checking; return }
        if supported == false { state = .unsupported; return }
        if permitted == false { state = .notAllowed; return }
        if pumping { state = .syncing; return }
        if let lastError, failures > 0 { state = .error(lastError); return }
        state = pending > 0 || pendingAssets > 0 ? .syncing : .synced
    }

    private func refreshCounts() async {
        guard let engine else { return }
        if let peer {
            pending = (try? await engine.pending(peer)) ?? pending
            lastSync = (try? await engine.peer(peer))?.lastSync
            refused = await engine.refusedCount(peer)
        }
        pendingAssets = (try? await engine.pendingAssets()) ?? pendingAssets
        if case .synced = state, pending > 0 || pendingAssets > 0 { state = .syncing }
        if case .syncing = state, !pumping, pending == 0, pendingAssets == 0, transport != nil { state = .synced }
    }

    /// One quiet status line: local saving is separate from syncing.
    var label: String {
        switch state {
        case .off: "Saved on this phone · Draw sync is off"
        case .checking: "Saved on this phone · checking your computer…"
        case .unsupported: "Saved on this phone · this computer’s OLIVE doesn’t support Draw yet"
        case .notAllowed: "Saved on this phone · your computer does not allow Draw sync for this phone"
        case .offline: pending > 0 ? "Offline — \(pending) edit\(pending == 1 ? "" : "s") waiting · will sync later" : "Saved on this phone"
        case .syncing:
            pendingAssets > 0 ? "Syncing… · \(pendingAssets) image\(pendingAssets == 1 ? "" : "s") arriving"
                : pending > 0 ? "Syncing… · \(pending) edit\(pending == 1 ? "" : "s") waiting" : "Syncing…"
        case .synced: pendingAssets > 0 ? "Synced · \(pendingAssets) image\(pendingAssets == 1 ? "" : "s") arriving" : "Synced with your computer"
        case .error(let code): "Sync issue (\(code)) · drawings are saved on this phone"
        }
    }
}
