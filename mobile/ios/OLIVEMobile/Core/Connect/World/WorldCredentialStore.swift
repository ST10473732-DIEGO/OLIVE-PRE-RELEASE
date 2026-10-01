import Foundation

/// World route credentials per paired computer, in the Keychain (device-only,
/// never synced, never UserDefaults). One account per computer so several
/// computers each keep their own route. Non-secret preferences live apart.
actor WorldCredentialStore {
    private let secrets: any SecretStore
    init(secrets: any SecretStore = KeychainSecretStore()) { self.secrets = secrets }
    static func account(_ peerID: String) -> String { "world-route-v1." + peerID }

    func load(peerID: String) async -> WorldCredential? {
        guard let data = try? await secrets.read(account: Self.account(peerID)),
              let value = try? ConnectJSON.decode(data, limit: 2048),
              let credential = try? WorldCredential(value), credential.peerID == peerID else { return nil }
        return credential
    }
    func save(_ credential: WorldCredential) async throws {
        try await secrets.write(credential.wire.canonical, account: Self.account(credential.peerID))
    }
    /// A newer relay URL for the same route (the computer's answer was "current").
    func updateRelay(peerID: String, relayURL: String) async throws {
        guard let current = await load(peerID: peerID), current.relayURL != relayURL else { return }
        try await save(WorldCredential(peerID: peerID, relayURL: relayURL, routeID: current.routeID,
                                       routeSecret: current.routeSecret, generation: current.generation))
    }
    /// Unpair, revocation or reset: the route is forgotten on this iPhone.
    func forget(peerID: String) async {
        try? await secrets.remove(account: Self.account(peerID))
    }
}

/// Non-secret World preferences on this iPhone.
struct WorldPreferences {
    private let defaults: UserDefaults
    init(defaults: UserDefaults = .standard) { self.defaults = defaults }
    /// On by default once a computer has provisioned a route; Off keeps Direct only.
    var enabled: Bool {
        get { defaults.object(forKey: "olive.world.enabled") as? Bool ?? true }
        nonmutating set { defaults.set(newValue, forKey: "olive.world.enabled") }
    }
    /// The computer said World is off or has no relay (a reason code, never a secret).
    func unavailable(peerID: String) -> String? { defaults.string(forKey: "olive.world.unavailable." + peerID) }
    func setUnavailable(_ reason: String?, peerID: String) {
        defaults.set(reason, forKey: "olive.world.unavailable." + peerID)
    }
}

/// Explicit, DEBUG-only test switches (Mac test host / acceptance). Release builds ignore them.
enum WorldTestFlags {
    /// Test-only: never attempt Direct, so the relay path is exercised on one LAN.
    static var forceWorld: Bool {
        #if DEBUG
        ProcessInfo.processInfo.arguments.contains("--olive-world-force") || ProcessInfo.processInfo.environment["OLIVE_WORLD_FORCE"] == "1"
        #else
        false
        #endif
    }
    /// Test-only: allow a plaintext ws:// relay on loopback or a private LAN address (Mac test host).
    static var allowTestPlaintext: Bool {
        #if DEBUG
        ProcessInfo.processInfo.arguments.contains("--olive-world-test-lan") || ProcessInfo.processInfo.environment["OLIVE_WORLD_TEST_LAN"] == "1"
        #else
        false
        #endif
    }
}
