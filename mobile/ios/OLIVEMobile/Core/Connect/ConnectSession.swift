import Foundation
import Observation

@MainActor
protocol ChatRemoteSession: AnyObject {
    var connected: Bool { get }
    var capability: ConnectJSON? { get }
    var selectedID: String? { get }
    var inference: RemoteInferenceClient? { get }
    /// Remote Chat v2 (olive-chat/1), only when the computer advertised it.
    var chat: RemoteChatClient? { get }
    var chatCapabilities: ChatCapabilities? { get }
    /// True once the computer answered the protocol probe (either way).
    var chatProbed: Bool { get }
    func refreshChatCapabilities() async
}

extension ChatRemoteSession {
    var chat: RemoteChatClient? { nil }
    var chatCapabilities: ChatCapabilities? { nil }
    var chatProbed: Bool { true }
    func refreshChatCapabilities() async {}
}

/// Whether to keep sending the optional OLIVE Notes probe. An older desktop
/// closes the channel on it every time; a Wi-Fi hiccup can too, once. Only two
/// consecutive failures mean "this computer's OLIVE doesn't sync Notes" for the
/// rest of this launch, so an older desktop sees at most two reconnects.
struct NotesProbePolicy: Equatable {
    static let attempts = 2
    private(set) var enabled = true
    private var failures = 0
    mutating func succeeded() { failures = 0 }
    mutating func failed() { failures += 1; if failures >= Self.attempts { enabled = false } }
}

/// The first authenticated path wins; Direct is preferred when both arrive close
/// together (a short grace after a World win). Later Direct successes become an
/// upgrade offer; any other late channel is closed. Never two live sessions.
@MainActor
private final class EstablishRace {
    private var continuation: CheckedContinuation<ConnectTransport?, Never>?
    private var pending: Int
    private var held: ConnectTransport?
    private var grace: Task<Void, Never>?
    var onLateDirect: ((ConnectTransport) -> Void)?
    init(expected: Int, _ continuation: CheckedContinuation<ConnectTransport?, Never>) {
        pending = expected; self.continuation = continuation
    }
    private func decide(_ channel: ConnectTransport?) {
        grace?.cancel(); grace = nil
        guard let continuation else { return }
        self.continuation = nil
        continuation.resume(returning: channel)
    }
    func report(_ channel: ConnectTransport?) {
        pending -= 1
        guard let channel else {
            if continuation != nil && pending == 0 { let held = held; self.held = nil; decide(held) }
            return
        }
        guard continuation != nil else {
            if channel.path == .direct, let onLateDirect { onLateDirect(channel) } else { Task { await channel.close() } }
            return
        }
        if channel.path == .direct {
            if let held { Task { await held.close() } }
            held = nil; decide(channel)
        } else if pending == 0 {
            decide(channel)
        } else {
            held = channel
            grace = Task { [weak self] in
                try? await Task.sleep(for: .milliseconds(750))
                guard !Task.isCancelled, let self else { return }
                let held = self.held; self.held = nil; self.decide(held)
            }
        }
    }
}

@MainActor @Observable
final class ConnectSession: ChatRemoteSession {
    var onChannelReady: (@MainActor (ConnectTransport, ConnectIdentity, TrustedConnectPeer) async -> Void)?
    var onDisconnect: (@MainActor () -> Void)?
    let discovery = ConnectDiscoveryService()
    let repository: ConnectTrustRepository
    let pairing: ConnectPairingClient
    private let identities: ConnectIdentityStore
    private(set) var peers: [TrustedConnectPeer]
    private(set) var selectedID: String?
    private(set) var status = "Not connected"
    private(set) var diagnostic = "idle"
    private(set) var connected = false
    private(set) var companionCapability: ConnectJSON?
    /// OLIVE Notes probe result: {notes_protocol, permission}. nil = unknown/unsupported.
    private(set) var notesCapability: ConnectJSON?
    var onNotesCapability: (@MainActor (ConnectJSON?) -> Void)?
    private var capabilityProbe = true
    private var notesProbe = NotesProbePolicy()
    private var revokedPeers = Set<String>()
    private var selectedRevoked: Bool { selectedID.map { revokedPeers.contains($0) } ?? false }
    private(set) var capability: ConnectJSON?
    private(set) var fingerprint: String?
    private(set) var resettingIdentity = false
    var canResetIdentity: Bool { repository.isAvailable && peers.isEmpty && !resettingIdentity }
    private(set) var inference: RemoteInferenceClient?
    /// olive-chat/1 client and the computer's mode matrix (nil on older computers).
    private(set) var chat: RemoteChatClient?
    private(set) var chatCapabilities: ChatCapabilities?
    private(set) var chatProbed = false
    var onChatReady: (@MainActor () -> Void)?
    private var transport: ConnectTransport?
    private var reconnect: Task<Void, Never>?
    private var generation = UUID()
    private var identityGeneration = UUID()
    private var foreground = false
    private(set) var lifecycle: MobileLifecycleState = .unpaired
    func finishBackgroundWork() { if !foreground { suspend() } }
    private var discoveryRetry: Task<Void, Never>?
    private var nextDiscoveryRetry = ContinuousClock.now
    var selected: TrustedConnectPeer? { peers.first { $0.id == selectedID } }

    // MARK: OLIVE Connect World
    /// The path of the authenticated channel: Direct (local network) or World (relay).
    private(set) var path: ConnectPath?
    /// Plain World state for the selected computer ("Ready", "Not set up yet", …).
    private(set) var worldStatus = "Not set up yet"
    /// Whether the selected computer speaks olive-world/1 (nil until it answers).
    private(set) var worldSupported: Bool?
    private(set) var worldProvisioned = false
    private var worldFailure: WorldFailure?
    @ObservationIgnored let worldCredentials: WorldCredentialStore
    @ObservationIgnored private let worldPreferences: WorldPreferences
    @ObservationIgnored private let network = WorldNetworkMonitor()
    @ObservationIgnored private var directUpgrade: Task<Void, Never>?
    @ObservationIgnored private var pendingUpgrade: ConnectTransport?
    @ObservationIgnored private var upgradeWaiter: CheckedContinuation<Void, Never>?
    /// Settings toggle. Off keeps Direct (local network) only.
    var worldEnabled: Bool {
        get { worldPreferences.enabled }
        set { worldPreferences.enabled = newValue; Task { await refreshWorldStatus() }; if foreground && !connected { kick() } }
    }

    init(repository: ConnectTrustRepository = ConnectTrustRepository(), identities: ConnectIdentityStore = ConnectIdentityStore(),
         worldCredentials: WorldCredentialStore = WorldCredentialStore(), worldPreferences: WorldPreferences = WorldPreferences()) {
        self.repository = repository; self.identities = identities
        self.worldCredentials = worldCredentials; self.worldPreferences = worldPreferences
        pairing = ConnectPairingClient(repository: repository, identities: identities)
        peers = repository.peers; selectedID = peers.first?.id
        discovery.onNewEndpoints = { [weak self] in self?.discoveredEndpoints() }
        network.onChange = { [weak self] previous, now in self?.networkChanged(from: previous, to: now) }
    }
    private func discoveredEndpoints() {
        if connected && path == .world { probeDirect(); return }   // Back on the LAN: try Direct alongside World.
        guard foreground, selected != nil, !connected, reconnect == nil, discoveryRetry == nil else { return }
        // Discovery remains untrusted. Coalesce announcements and cap new retry
        // cycles to one per minute; each candidate still needs exact pinned TLS.
        let deadline = max(nextDiscoveryRetry, .now)
        discoveryRetry = Task { [weak self] in
            try? await Task.sleep(until: deadline, clock: .continuous)
            guard let self, !Task.isCancelled else { return }
            self.discoveryRetry = nil
            guard self.foreground, !self.discovery.nearby.isEmpty else { return }
            self.connect()
        }
    }
    /// Wi-Fi <-> cellular, or the network coming back: one immediate bounded attempt (no polling).
    private func networkChanged(from previous: WorldNetworkMonitor.Snapshot, to now: WorldNetworkMonitor.Snapshot) {
        guard foreground, selected != nil, !selectedRevoked else { return }
        if connected {
            if path == .direct && previous.wifi && !now.wifi, let transport {
                Task { await transport.close() }   // The LAN is gone: fail over now, not after a timeout.
            } else if path == .world && now.wifi && !previous.wifi {
                probeDirect()
            }
        } else if now.satisfied && (!previous.satisfied || previous.wifi != now.wifi) {
            kick()
        }
    }
    /// Restart the reconnect cycle immediately (not connected only).
    private func kick() {
        guard !connected, foreground else { return }
        generation = UUID(); reconnect?.cancel(); reconnect = nil
        discoveryRetry?.cancel(); discoveryRetry = nil
        connect()
    }
    func context() async throws -> (ConnectTransport, ConnectIdentity, TrustedConnectPeer) {
        guard connected, let transport, let peer = selected else { throw ConnectFailure.peerOffline }
        let identity = try await identities.load(allowCreation: false)
        guard connected, self.transport === transport, selectedID == peer.id else { throw ConnectFailure.peerOffline }
        return (transport, identity, peer)
    }
    /// This phone's Connect device ID when an identity already exists (no creation).
    func localDeviceID() async -> String? {
        try? await identities.load(allowCreation: false).publicIdentity.deviceID
    }
    func refreshPeers() {
        peers = repository.peers
        if selectedID == nil { selectedID = peers.first?.id }
        if foreground { connect() }
    }
    func select(_ id: String) {
        capabilityProbe = true; notesProbe = NotesProbePolicy(); selectedID = id; disconnect()
        worldSupported = nil; worldFailure = nil
        Task { await refreshWorldStatus() }
        if foreground { connect() }
    }
    func activate() {
        foreground = true; lifecycle = selectedRevoked ? .revoked : connected ? .foregroundConnected : selected == nil ? .unpaired : .foregroundConnecting; discovery.start()
        network.start()
        let identityToken = identityGeneration
        Task {
            let value = try? await identities.load(allowCreation: repository.isPristine).publicIdentity.fingerprint
            if !resettingIdentity, identityGeneration == identityToken { fingerprint = value }
        }
        Task { await refreshWorldStatus() }
        connect()
    }
    func suspend(continuing: Bool = false) {
        foreground = false; pairing.cancel(); discovery.stop(); network.stop()
        directUpgrade?.cancel(); directUpgrade = nil
        if continuing && connected { lifecycle = .backgroundActiveTask; status = "Background · active work" }
        else { disconnect(); lifecycle = selectedRevoked ? .revoked : selected == nil ? .unpaired : .backgroundSuspendedExpected; status = selectedRevoked ? "Revoked" : "Background · suspended" }
    }
    func disconnect() {
        onDisconnect?()
        generation = UUID(); reconnect?.cancel(); reconnect = nil
        discoveryRetry?.cancel(); discoveryRetry = nil
        directUpgrade?.cancel(); directUpgrade = nil
        if let pendingUpgrade { Task { await pendingUpgrade.close() } }
        pendingUpgrade = nil; wakeUpgrade()
        if let transport { Task { await transport.close() } }
        transport = nil; inference = nil; capability = nil; companionCapability = nil; notesCapability = nil; connected = false; path = nil
        chat = nil; chatCapabilities = nil; chatProbed = false
        status = selectedRevoked ? "Revoked" : selected == nil ? "Not connected" : "Offline"
        lifecycle = selectedRevoked ? .revoked : selected == nil ? .unpaired : .pairedOffline
    }
    func recordRevocation(peerID: String) {
        // Only an authenticated explicit protocol error calls this. EOF, Wi-Fi
        // loss and expired work never imply revoked trust.
        revokedPeers.insert(peerID)
        Task { await worldCredentials.forget(peerID: peerID); await refreshWorldStatus() }   // World access ends with trust.
        if selectedID == peerID { disconnect(); diagnostic = "device_revoked" }
    }

    /// Direct (each discovered endpoint, pinned TLS) and World (relay, the same
    /// pinned TLS) race; returns the winning authenticated channel or nil.
    private func establish(identity: ConnectIdentity, peer: TrustedConnectPeer, token: UUID) async -> ConnectTransport? {
        let endpoints = Array(discovery.nearby.prefix(8))
        let lanUsable = network.current.wifi
        let directAllowed = !WorldTestFlags.forceWorld && !endpoints.isEmpty && lanUsable
        var credential: WorldCredential?
        if worldEnabled && worldPreferences.unavailable(peerID: peer.id) == nil {
            credential = await worldCredentials.load(peerID: peer.id)
        }
        guard generation == token else { return nil }
        var paths = WorldPathSelector(worldAvailable: credential != nil, directAllowed: directAllowed, worldAllowed: true)
        let actions = paths.start(lanUsable: lanUsable)
        guard !actions.isEmpty else { return nil }
        diagnostic = "connect:" + (credential == nil ? "direct" : directAllowed ? "direct+world" : "world")
        return await withCheckedContinuation { (continuation: CheckedContinuation<ConnectTransport?, Never>) in
            let race = EstablishRace(expected: actions.count, continuation)
            race.onLateDirect = { [weak self] channel in self?.offerUpgrade(channel, token: token) }
            for action in actions {
                guard case .connect(let kind, _, let delay) = action else { continue }
                Task { @MainActor in
                    if delay > 0 { try? await Task.sleep(for: .seconds(delay)) }
                    race.report(await self.attempt(kind, identity: identity, peer: peer, endpoints: endpoints, credential: credential, token: token))
                }
            }
        }
    }

    private func attempt(_ kind: ConnectPath, identity: ConnectIdentity, peer: TrustedConnectPeer, endpoints: [NearbyConnectPeer],
                         credential: WorldCredential?, token: UUID) async -> ConnectTransport? {
        guard generation == token else { return nil }
        if kind == .direct {
            for endpoint in endpoints {
                let channel = ConnectTransport(endpoint: endpoint.endpoint)
                do { try await channel.connect(identity: identity, peer: peer.identity); return channel }
                catch { await channel.close(); if generation != token { return nil } }
            }
            return nil
        }
        guard let credential else { return nil }
        do {
            let stream = try WorldSocket(credential: credential)
            let channel = ConnectTransport(stream: stream, path: .world)
            do {
                try await channel.connect(identity: identity, peer: peer.identity)
                worldFailure = nil
                return channel
            } catch {
                // A relay-level reason when there is one; otherwise the OLIVE peer refused authentication.
                let relayReason = await stream.failure
                worldFailure = relayReason ?? (error as? ConnectFailure == .certificateMismatch ? nil : .computerOffline)
                if error as? ConnectFailure == .certificateMismatch { diagnostic = "world:identity_rejected" }
                await channel.close()
                return nil
            }
        } catch {
            worldFailure = error as? WorldFailure ?? .relayNotConfigured
            return nil
        }
    }

    /// On World with the LAN back: try Direct alongside; a success replaces World.
    private func probeDirect() {
        guard connected, path == .world, foreground, directUpgrade == nil, !WorldTestFlags.forceWorld,
              network.current.wifi, let peer = selected else { return }
        let token = generation
        let endpoints = Array(discovery.nearby.prefix(8))
        guard !endpoints.isEmpty else { return }
        directUpgrade = Task { [weak self] in
            guard let self else { return }
            defer { if self.generation == token { self.directUpgrade = nil } }
            guard let identity = try? await self.identities.load(allowCreation: false) else { return }
            if let channel = await self.attempt(.direct, identity: identity, peer: peer, endpoints: endpoints, credential: nil, token: token) {
                self.offerUpgrade(channel, token: token)
            }
        }
    }
    private func offerUpgrade(_ channel: ConnectTransport, token: UUID) {
        guard generation == token, connected, path == .world, pendingUpgrade == nil else { Task { await channel.close() }; return }
        pendingUpgrade = channel
        wakeUpgrade()
    }
    private func wakeUpgrade() { let waiter = upgradeWaiter; upgradeWaiter = nil; waiter?.resume() }
    /// The heartbeat's wait: returns after `seconds`, or at once when a Direct upgrade is ready.
    private func heartbeatPause(seconds: Double) async throws {
        guard pendingUpgrade == nil else { return }
        let timer = Task { [weak self] in
            try? await Task.sleep(for: .seconds(seconds))
            guard !Task.isCancelled else { return }   // A finished pause's timer must not wake the next one.
            self?.wakeUpgrade()
        }
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            upgradeWaiter?.resume()
            upgradeWaiter = continuation
        }
        timer.cancel()
        try Task.checkCancellation()
    }

    func connect() {
        guard !selectedRevoked, foreground, reconnect == nil, !connected, let peer = selected else { return }
        nextDiscoveryRetry = .now.advanced(by: .seconds(60))
        let token = UUID(); generation = token
        reconnect = Task {
            // Bounded: LAN-only keeps the original short cycle; with World, exponential
            // backoff up to 30 s for about ten minutes. Network changes restart it at once.
            var worldPossible = false
            if worldEnabled { worldPossible = await worldCredentials.load(peerID: peer.id) != nil }
            var backoff = WorldBackoff()
            let attempts = worldPossible ? 26 : 6
            let legacy: [Double] = [0, 1, 2, 4, 8, 15]
            var attempt = 0
            var attemptedRevision = discovery.revision
            var upgraded: ConnectTransport?
            while attempt < attempts {
                let delay = upgraded != nil ? 0 : worldPossible ? (attempt == 0 ? 0 : backoff.next()) : legacy[attempt]
                attempt += 1
                if delay > 0 { try? await Task.sleep(for: .seconds(delay)) }
                guard generation == token, !Task.isCancelled, foreground else { return }
                status = "Connecting"; diagnostic = "discovery"
                attemptedRevision = discovery.revision
                let identity: ConnectIdentity
                do { diagnostic = "identity"; identity = try await identities.load(allowCreation: repository.isPristine) }
                catch { diagnostic = "identity:" + (error as? ConnectFailure ?? .identityRecoveryRequired).rawValue; continue }
                let candidate: ConnectTransport?
                if let next = upgraded { candidate = next; upgraded = nil }
                else { diagnostic = "tcp_tls_hello"; candidate = await establish(identity: identity, peer: peer, token: token) }
                guard generation == token else { if let candidate { await candidate.close() }; return }
                guard let channel = candidate else {
                    status = worldFailure == .computerOffline ? "Offline · Your computer is offline" : "Offline"
                    await refreshWorldStatus()
                    continue
                }
                transport = channel
                let started = ContinuousClock.now
                do {
                    let client = RemoteInferenceClient(transport: channel, source: identity.publicIdentity.deviceID, target: peer.id)
                    diagnostic = "inference_status"
                    let capabilities = try await client.status()
                    if capabilityProbe {
                        do { companionCapability = try await client.companionStatus() }
                        catch {
                            // Older desktop rejects the optional operation. Retain
                            // exact pinned reconnect, then use its existing C7 status.
                            if error as? ConnectFailure == .deviceRevoked { throw error }
                            capabilityProbe = false
                            throw error
                        }
                    }
                    if notesProbe.enabled {
                        do { notesCapability = try await client.notesStatus(); notesProbe.succeeded() }
                        catch {
                            // An older desktop cannot parse Notes frames and drops the
                            // channel. Reconnect; after repeated failures stop probing
                            // (see NotesProbePolicy) and Notes stays local on this phone.
                            if error as? ConnectFailure == .deviceRevoked { throw error }
                            notesProbe.failed()
                            throw error
                        }
                    }
                    guard generation == token else { await channel.close(); return }
                    lifecycle = .foregroundConnected
                    path = channel.path
                    inference = client; capability = capabilities; connected = true; status = "Connected"; diagnostic = "authenticated:" + channel.path.rawValue.lowercased()
                    await refreshWorldStatus()
                    await onChannelReady?(channel, identity, peer)
                    Task { await self.probeChat(channel: channel, source: identity.publicIdentity.deviceID, target: peer.id, token: token) }
                    Task { await self.provisionWorld(channel: channel, source: identity.publicIdentity.deviceID, target: peer.id, token: token) }
                    attempt = 0 // A later disconnection gets a fresh bounded recovery cycle.
                    if channel.path == .world { probeDirect() }
                    // C7 status is the existing public role/policy negotiation and heartbeat.
                    var beats = 0
                    while generation == token && !Task.isCancelled {
                        try await heartbeatPause(seconds: 15)
                        if let next = pendingUpgrade {
                            // Direct is back: hand over to it and retire World. Accepted desktop
                            // work continues; Chat recovers by job id, transfers by offset.
                            pendingUpgrade = nil
                            upgraded = next
                            throw ConnectFailure.connectionLost
                        }
                        let fresh = try await client.status()
                        guard generation == token else { return }
                        capability = fresh
                        beats += 1
                        if beats % 4 == 0, chat != nil { await refreshChatCapabilities() }
                        if beats % 2 == 0, path == .world { probeDirect() }
                        if capabilityProbe { companionCapability = try await client.companionStatus() }
                        if notesProbe.enabled {
                            let notes = try await client.notesStatus()
                            if notes != notesCapability { notesCapability = notes; onNotesCapability?(notes) }
                        }
                    }
                } catch {
                    await channel.close()
                    guard generation == token else { if let upgraded { await upgraded.close() }; return }
                    if error as? ConnectFailure == .deviceRevoked { recordRevocation(peerID: peer.id); return }
                    backoff.settled(lived: Double(started.duration(to: .now).components.seconds))
                    onDisconnect?()
                    connected = false; path = nil; inference = nil; capability = nil; companionCapability = nil; notesCapability = nil; lifecycle = foreground ? .reconnecting : .backgroundSuspendedExpected
                    chat = nil; chatCapabilities = nil; chatProbed = false
                    directUpgrade?.cancel(); directUpgrade = nil
                    diagnostic += ":" + (error as? ConnectFailure ?? .connectionLost).rawValue
                    status = upgraded != nil ? "Connecting" : (error as? ConnectFailure) == .certificateMismatch ? "Identity rejected" : "Offline"
                }
            }
            if generation == token {
                reconnect = nil; status = "Offline · Waiting for your computer"
                await refreshWorldStatus()
                if discovery.revision != attemptedRevision { discoveredEndpoints() }
            }
        }
    }
    func retry() { capabilityProbe = true; notesProbe = NotesProbePolicy(); disconnect(); connect() }

    /// Remote Chat v2 negotiation. The read-only `protocols` probe decides whether
    /// frame 17 may ever be sent; an older computer simply keeps FAST/NORMAL/MAX.
    /// A failed probe never drops the connection or causes a reconnect loop.
    private func probeChat(channel: ConnectTransport, source: String, target: String, token: UUID) async {
        do {
            let speaks = try await RemoteChatClient.probe(transport: channel, source: source, target: target)
            guard generation == token, connected else { return }
            guard speaks else { chatProbed = true; return }
            let client = RemoteChatClient(transport: channel, source: source, target: target)
            let capabilities = try await client.capabilities()
            guard generation == token, connected else { return }
            chat = client; chatCapabilities = capabilities; chatProbed = true
            onChatReady?()
        } catch {
            guard generation == token else { return }
            if error as? ConnectFailure == .deviceRevoked { recordRevocation(peerID: target); return }
            chatProbed = true  // Treated as unsupported for this connection; the next one asks again.
        }
    }

    /// OLIVE Connect World enrolment for an existing pair, over this authenticated
    /// channel: no re-pairing. Asked only of computers that list olive-world/1.
    /// Idempotent: the computer returns the same route until it rotates it.
    private func provisionWorld(channel: ConnectTransport, source: String, target: String, token: UUID) async {
        do {
            let protocols = try await WorldProvisioner.protocols(transport: channel, source: source, target: target)
            guard generation == token else { return }
            guard protocols.contains(WorldWire.name) else { worldSupported = false; await refreshWorldStatus(); return }
            worldSupported = true
            let have = await worldCredentials.load(peerID: target)?.routeID
            switch try await WorldProvisioner.provision(transport: channel, source: source, target: target, have: have) {
            case .provisioned(let credential):
                try await worldCredentials.save(credential)
                worldPreferences.setUnavailable(nil, peerID: target)
            case .current(_, let relayURL):
                try await worldCredentials.updateRelay(peerID: target, relayURL: relayURL)
                worldPreferences.setUnavailable(nil, peerID: target)
            case .unavailable(let reason):
                worldPreferences.setUnavailable(reason, peerID: target)
            }
        } catch {
            if error as? ConnectFailure == .deviceRevoked { recordRevocation(peerID: target); return }
            // World stays as it was; Direct is unaffected.
        }
        await refreshWorldStatus()
    }

    /// Plain words for Devices and Settings. Never a route, key or secret.
    func refreshWorldStatus() async {
        guard let peer = selected else { worldStatus = "Not set up"; worldProvisioned = false; return }
        let credential = await worldCredentials.load(peerID: peer.id)
        worldProvisioned = credential != nil
        if revokedPeers.contains(peer.id) { worldStatus = "Revoked"; return }
        if !worldEnabled { worldStatus = "Off"; return }
        if connected && path == .world { worldStatus = "Connected · World"; return }
        switch worldPreferences.unavailable(peerID: peer.id) {
        case .some("disabled"): worldStatus = "Off on your computer"; return
        case .some("relay_not_configured"): worldStatus = "Relay not configured"; return
        case .some: worldStatus = "Unavailable on your computer"; return
        case .none: break
        }
        if credential == nil {
            worldStatus = worldSupported == false ? "Not supported by this computer" : "Not set up yet"
            return
        }
        if let worldFailure, !connected {
            worldStatus = worldFailure == .computerOffline ? "Ready · Computer offline"
                : worldFailure == .relayUnreachable ? "Relay unavailable" : worldFailure.message
            return
        }
        worldStatus = "Ready"
    }

    func refreshChatCapabilities() async {
        guard let chat, connected else { return }
        let token = generation
        if let fresh = try? await chat.capabilities(), generation == token, connected { chatCapabilities = fresh }
    }
    func unpair(_ id: String) throws {
        if selectedID == id { disconnect() }
        try repository.unpair(id); revokedPeers.remove(id); peers = repository.peers
        Task { await worldCredentials.forget(peerID: id); worldPreferences.setUnavailable(nil, peerID: id) }
        if selectedID == id { selectedID = peers.first?.id }
        if foreground { connect() }
    }
    func resetIdentity() async throws {
        guard canResetIdentity else { throw ConnectFailure.identityRecoveryRequired }
        resettingIdentity = true
        identityGeneration = UUID()
        defer { resettingIdentity = false }
        pairing.cancel(); disconnect(); fingerprint = nil
        try repository.prepareIdentityReset()
        do {
            let identity = try await identities.reset()
            fingerprint = identity.publicIdentity.fingerprint
            diagnostic = "identity_reset"; status = "Not connected"
        } catch {
            diagnostic = "identity_reset_failed"
            throw ConnectFailure.identityRecoveryRequired
        }
    }
}

/// The two read-only/idempotent requests World enrolment needs, on the ordinary request frame.
enum WorldProvisioner {
    static func protocols(transport: any ChatFrameTransport, source: String, target: String) async throws -> [String] {
        let now = Int64(Date().timeIntervalSince1970), id = UUID().uuidString.lowercased()
        let request = ConnectJSON.object(["request_id": .string(id), "protocol_version": .string("olive-connect/1"),
            "source_device_id": .string(source), "target_device_id": .string(target), "capability": .string("connect.ping"),
            "operation": .string("protocols"), "arguments": .object([:]), "timestamp": .int(now), "expires_at": .int(now + 60)])
        let value = try ConnectJSON.decode(try await transport.exchangeFrame(kind: 1, id: id, payload: request.canonical), limit: 16_384)
        guard value["state"] == .string("completed") else { return [] }
        return (value["result"]["protocols"].array ?? []).compactMap(\.string)
    }
    static func provision(transport: any ChatFrameTransport, source: String, target: String, have: String?) async throws -> WorldWire.Provisioning {
        let request = WorldWire.provisioningRequest(source: source, target: target, have: have)
        let raw = try await transport.exchangeFrame(kind: 1, id: try request["request_id"].uuid(), payload: request.canonical)
        return try WorldWire.provisioning(ConnectJSON.decode(raw, limit: 16_384), peerID: target)
    }
}
