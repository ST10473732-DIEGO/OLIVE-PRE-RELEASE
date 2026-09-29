import Foundation
import Observation

@MainActor
protocol ChatRemoteSession: AnyObject {
    var connected: Bool { get }
    var capability: ConnectJSON? { get }
    var selectedID: String? { get }
    var inference: RemoteInferenceClient? { get }
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
    init(repository: ConnectTrustRepository = ConnectTrustRepository(), identities: ConnectIdentityStore = ConnectIdentityStore()) {
        self.repository = repository; self.identities = identities
        pairing = ConnectPairingClient(repository: repository, identities: identities)
        peers = repository.peers; selectedID = peers.first?.id
        discovery.onNewEndpoints = { [weak self] in self?.discoveredEndpoints() }
    }
    private func discoveredEndpoints() {
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
    func select(_ id: String) { capabilityProbe = true; notesProbe = NotesProbePolicy(); selectedID = id; disconnect(); if foreground { connect() } }
    func activate() {
        foreground = true; lifecycle = selectedRevoked ? .revoked : connected ? .foregroundConnected : selected == nil ? .unpaired : .foregroundConnecting; discovery.start()
        let identityToken = identityGeneration
        Task {
            let value = try? await identities.load(allowCreation: repository.isPristine).publicIdentity.fingerprint
            if !resettingIdentity, identityGeneration == identityToken { fingerprint = value }
        }
        connect()
    }
    func suspend(continuing: Bool = false) {
        foreground = false; pairing.cancel(); discovery.stop()
        if continuing && connected { lifecycle = .backgroundActiveTask; status = "Background · active work" }
        else { disconnect(); lifecycle = selectedRevoked ? .revoked : selected == nil ? .unpaired : .backgroundSuspendedExpected; status = selectedRevoked ? "Revoked" : "Background · suspended" }
    }
    func disconnect() {
        onDisconnect?()
        generation = UUID(); reconnect?.cancel(); reconnect = nil
        discoveryRetry?.cancel(); discoveryRetry = nil
        if let transport { Task { await transport.close() } }
        transport = nil; inference = nil; capability = nil; companionCapability = nil; notesCapability = nil; connected = false
        status = selectedRevoked ? "Revoked" : selected == nil ? "Not connected" : "Offline"
        lifecycle = selectedRevoked ? .revoked : selected == nil ? .unpaired : .pairedOffline
    }
    func recordRevocation(peerID: String) {
        // Only an authenticated explicit protocol error calls this. EOF, Wi-Fi
        // loss and expired work never imply revoked trust.
        revokedPeers.insert(peerID)
        if selectedID == peerID { disconnect(); diagnostic = "device_revoked" }
    }
    func connect() {
        guard !selectedRevoked, foreground, reconnect == nil, !connected, let peer = selected else { return }
        nextDiscoveryRetry = .now.advanced(by: .seconds(60))
        let token = UUID(); generation = token
        reconnect = Task {
            let delays = [0, 1, 2, 4, 8, 15]
            var attempt = 0
            var attemptedRevision = discovery.revision
            while attempt < delays.count {
                let delay = delays[attempt]; attempt += 1
                if delay > 0 { try? await Task.sleep(for: .seconds(delay)) }
                guard generation == token, !Task.isCancelled, foreground else { return }
                status = "Connecting"; diagnostic = "discovery"
                let endpoints = Array(discovery.nearby.prefix(8))
                attemptedRevision = discovery.revision
                for endpoint in endpoints {
                    let channel = ConnectTransport(endpoint: endpoint.endpoint)
                    transport = channel
                    do {
                        diagnostic = "identity"
                        let identity = try await identities.load(allowCreation: repository.isPristine)
                        diagnostic = "tcp_tls_hello"
                        try await channel.connect(identity: identity, peer: peer.identity)
                        guard generation == token else { await channel.close(); return }
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
                        inference = client; capability = capabilities; connected = true; status = "Connected"; diagnostic = "authenticated"
                        await onChannelReady?(channel, identity, peer)
                        attempt = 0 // A later disconnection gets a fresh bounded recovery cycle.
                        // C7 status is the existing public role/policy negotiation and heartbeat.
                        while generation == token && !Task.isCancelled {
                            try await Task.sleep(for: .seconds(15))
                            let fresh = try await client.status()
                            guard generation == token else { return }
                            capability = fresh
                            if capabilityProbe { companionCapability = try await client.companionStatus() }
                            if notesProbe.enabled {
                                let notes = try await client.notesStatus()
                                if notes != notesCapability { notesCapability = notes; onNotesCapability?(notes) }
                            }
                        }
                    } catch {
                        await channel.close()
                        guard generation == token else { return }
                        if error as? ConnectFailure == .deviceRevoked { recordRevocation(peerID: peer.id); return }
                        onDisconnect?()
                        connected = false; inference = nil; capability = nil; companionCapability = nil; notesCapability = nil; lifecycle = foreground ? .reconnecting : .backgroundSuspendedExpected
                        diagnostic += ":" + (error as? ConnectFailure ?? .connectionLost).rawValue
                        status = (error as? ConnectFailure) == .certificateMismatch ? "Identity rejected" : "Offline"
                    }
                }
            }
            if generation == token {
                reconnect = nil; status = "Offline · Waiting for your computer"
                if discovery.revision != attemptedRevision { discoveredEndpoints() }
            }
        }
    }
    func retry() { capabilityProbe = true; notesProbe = NotesProbePolicy(); disconnect(); connect() }
    func unpair(_ id: String) throws {
        if selectedID == id { disconnect() }
        try repository.unpair(id); revokedPeers.remove(id); peers = repository.peers
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
