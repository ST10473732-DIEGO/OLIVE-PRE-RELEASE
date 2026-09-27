import Foundation
import Observation

@MainActor
protocol ChatRemoteSession: AnyObject {
    var connected: Bool { get }
    var capability: ConnectJSON? { get }
    var selectedID: String? { get }
    var inference: RemoteInferenceClient? { get }
}

@MainActor @Observable
final class ConnectSession: ChatRemoteSession {
    let discovery = ConnectDiscoveryService()
    let repository: ConnectTrustRepository
    let pairing: ConnectPairingClient
    private let identities: ConnectIdentityStore
    private(set) var peers: [TrustedConnectPeer]
    private(set) var selectedID: String?
    private(set) var status = "Not connected"
    private(set) var diagnostic = "idle"
    private(set) var connected = false
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
    func refreshPeers() {
        peers = repository.peers
        if selectedID == nil { selectedID = peers.first?.id }
        if foreground { connect() }
    }
    func select(_ id: String) { selectedID = id; disconnect(); if foreground { connect() } }
    func activate() {
        foreground = true; discovery.start()
        let identityToken = identityGeneration
        Task {
            let value = try? await identities.load(allowCreation: repository.isPristine).publicIdentity.fingerprint
            if !resettingIdentity, identityGeneration == identityToken { fingerprint = value }
        }
        connect()
    }
    func suspend() {
        foreground = false; pairing.cancel(); discovery.stop(); disconnect()
    }
    func disconnect() {
        generation = UUID(); reconnect?.cancel(); reconnect = nil
        discoveryRetry?.cancel(); discoveryRetry = nil
        if let transport { Task { await transport.close() } }
        transport = nil; inference = nil; capability = nil; connected = false
        status = selected == nil ? "Not connected" : "Offline"
    }
    func connect() {
        guard foreground, reconnect == nil, !connected, let peer = selected else { return }
        nextDiscoveryRetry = .now.advanced(by: .seconds(60))
        let token = UUID(); generation = token
        reconnect = Task {
            let delays = [0, 1, 2, 4, 8, 15]
            var attempt = 0
            var attemptedRevision = discovery.revision
            while attempt < delays.count {
                let delay = delays[attempt]; attempt += 1
                if delay > 0 { try? await Task.sleep(for: .seconds(delay)) }
                guard generation == token, !Task.isCancelled else { return }
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
                        guard generation == token else { await channel.close(); return }
                        inference = client; capability = capabilities; connected = true; status = "Connected"; diagnostic = "authenticated"
                        attempt = 0 // A later disconnection gets a fresh bounded recovery cycle.
                        // C7 status is the existing public role/policy negotiation and heartbeat.
                        while generation == token && !Task.isCancelled {
                            try await Task.sleep(for: .seconds(15))
                            let fresh = try await client.status()
                            guard generation == token else { return }
                            capability = fresh
                        }
                    } catch {
                        await channel.close()
                        guard generation == token else { return }
                        connected = false; inference = nil; capability = nil
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
    func retry() { disconnect(); connect() }
    func unpair(_ id: String) throws {
        if selectedID == id { disconnect() }
        try repository.unpair(id); peers = repository.peers
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
