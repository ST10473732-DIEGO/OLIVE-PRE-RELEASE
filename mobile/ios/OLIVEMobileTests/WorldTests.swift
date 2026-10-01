import XCTest
@testable import OLIVEMobile

/// In-memory SecretStore double; production uses the device-only Keychain.
private actor MemorySecretStore: SecretStore {
    var values: [String: Data] = [:]
    func read(account: String) throws -> Data? { values[account] }
    func write(_ data: Data, account: String) throws { values[account] = data }
    func remove(account: String) throws { values[account] = nil }
}

/// OLIVE Connect World on the iPhone. Vectors: tests/fixtures/world_vectors_v1.json
/// (the Python suite checks these exact strings appear here).
final class WorldWireTests: XCTestCase {
    let routeSecret = "769500f30dc44572ffe5d2de92dfcf5e90e4321a024988af7d8cd5f7545cd4b2"
    let routeID = "19115ed1205d644e5ed4108e9b49f629"
    let relayCredential = "1c235c6834e18abfc5ff6f60c8cbd6fb5c0ce03f170e136347088b12cba5bc4b"
    let peer = "22222222-2222-4222-8222-222222222222"

    func testKeyScheduleMatchesPythonVectors() throws {
        let credential = try WorldWire.relayCredential(routeSecret: XCTUnwrap(WorldWire.bytes(hex: routeSecret)))
        XCTAssertEqual(credential.hex, relayCredential)
        let hello = try WorldCredential(peerID: peer, relayURL: "wss://relay.example.com", routeID: routeID,
                                        routeSecret: routeSecret, generation: 1).hello()
        XCTAssertEqual(hello, "{\"credential\":\"\(relayCredential)\",\"role\":\"phone\",\"route\":\"\(routeID)\",\"v\":1}")
        XCTAssertFalse(hello.contains(routeSecret), "the relay never receives the route secret itself")
        XCTAssertThrowsError(try WorldWire.relayCredential(routeSecret: Data(count: 31)))
    }

    func testRelayURLPolicyNeverDowngradesSilently() throws {
        XCTAssertEqual(try WorldWire.relayURL("wss://relay.example.com").absoluteString, "wss://relay.example.com/olive-world/1")
        XCTAssertEqual(try WorldWire.relayURL("wss://relay.example.com:8443/world").path, "/world")
        for bad in ["ws://relay.example.com", "https://relay.example.com", "wss://user:pw@relay.example.com",
                    "wss://relay.example.com/?t=1", "wss://relay.example.com/#x", " wss://relay.example.com", "wss://"] {
            XCTAssertThrowsError(try WorldWire.relayURL(bad), bad)
        }
        XCTAssertThrowsError(try WorldWire.relayURL("ws://192.168.1.20:8765"), "plaintext needs the explicit DEBUG test flag")
        XCTAssertNoThrow(try WorldWire.relayURL("ws://192.168.1.20:8765", allowTestPlaintext: true))
        XCTAssertThrowsError(try WorldWire.relayURL("ws://8.8.8.8", allowTestPlaintext: true), "never a public plaintext relay")
    }

    func testRelayEvents() throws {
        XCTAssertEqual(try WorldWire.event("{\"event\":\"paired\",\"v\":1}"), .paired)
        XCTAssertEqual(try WorldWire.event("{\"event\":\"waiting\",\"v\":1}"), .waiting)
        for bad in ["{}", "{\"event\":\"paired\",\"v\":2}", "{\"event\":\"other\",\"v\":1}", "{\"event\":\"paired\",\"v\":1,\"x\":1}", "nope"] {
            XCTAssertThrowsError(try WorldWire.event(bad), bad)
        }
        XCTAssertEqual(WorldFailure.from(closeCode: 4007), .computerOffline)
        XCTAssertEqual(WorldFailure.from(closeCode: 4003), .replaced)
        XCTAssertEqual(WorldFailure.from(closeCode: 1001), .relayUnreachable)
    }

    private func completed(_ result: ConnectJSON) -> ConnectJSON {
        .object(["protocol_version": .string("olive-connect/1"), "request_id": .string(UUID().uuidString.lowercased()),
                 "state": .string("completed"), "result": result])
    }

    func testProvisioningIsParsedStrictly() throws {
        let provisioned = ConnectJSON.object(["world_protocol": .string("olive-world/1"), "state": .string("provisioned"),
            "route_id": .string(routeID), "route_secret": .string(routeSecret), "relay_url": .string("wss://relay.example.com"),
            "generation": .int(1)])
        guard case .provisioned(let credential) = try WorldWire.provisioning(completed(provisioned), peerID: peer) else { return XCTFail() }
        XCTAssertEqual(credential.routeID, routeID)
        XCTAssertEqual(try WorldWire.provisioning(completed(.object(["world_protocol": .string("olive-world/1"), "state": .string("current"),
            "route_id": .string(routeID), "relay_url": .string("wss://relay.example.com")])), peerID: peer),
            .current(routeID: routeID, relayURL: "wss://relay.example.com"))
        XCTAssertEqual(try WorldWire.provisioning(completed(.object(["world_protocol": .string("olive-world/1"),
            "state": .string("unavailable"), "reason": .string("disabled")])), peerID: peer), .unavailable(reason: "disabled"))
        var extra = provisioned.object!; extra["token"] = .string("x")
        var short = provisioned.object!; short["route_secret"] = .string("00")
        var upper = provisioned.object!; upper["route_id"] = .string(routeID.uppercased())
        var other = provisioned.object!; other["world_protocol"] = .string("olive-world/2")
        for bad in [extra, short, upper, other] {
            XCTAssertThrowsError(try WorldWire.provisioning(completed(.object(bad)), peerID: peer))
        }
        let revoked = ConnectJSON.object(["protocol_version": .string("olive-connect/1"), "request_id": .null,
                                          "state": .string("rejected"), "error": .string("device_not_paired")])
        XCTAssertThrowsError(try WorldWire.provisioning(revoked, peerID: peer)) { XCTAssertEqual($0 as? ConnectFailure, .deviceRevoked) }
        let request = WorldWire.provisioningRequest(source: peer, target: peer, have: routeID, now: 100)
        XCTAssertEqual(request["operation"], .string("world"))
        XCTAssertEqual(request["arguments"], .object(["have": .string(routeID)]))
        XCTAssertEqual(WorldWire.provisioningRequest(source: peer, target: peer, have: nil)["arguments"], .object([:]))
    }

    func testCredentialsLiveInTheSecretStorePerComputer() async throws {
        let secrets = MemorySecretStore()
        let store = WorldCredentialStore(secrets: secrets)
        let other = "33333333-3333-4333-8333-333333333333"
        let credential = WorldCredential(peerID: peer, relayURL: "wss://relay.example.com", routeID: routeID, routeSecret: routeSecret, generation: 1)
        try await store.save(credential)
        try await store.save(WorldCredential(peerID: other, relayURL: "wss://relay.example.com", routeID: String(repeating: "a", count: 32),
                                             routeSecret: String(repeating: "b", count: 64), generation: 3))
        let loaded = await store.load(peerID: peer)
        XCTAssertEqual(loaded, credential)
        try await store.updateRelay(peerID: peer, relayURL: "wss://other.example.com")
        let moved = await store.load(peerID: peer)
        XCTAssertEqual(moved?.relayURL, "wss://other.example.com")
        XCTAssertEqual(moved?.routeSecret, routeSecret)
        await store.forget(peerID: peer)
        let forgotten = await store.load(peerID: peer)
        XCTAssertNil(forgotten, "revocation/unpair forgets the route")
        let untouched = await store.load(peerID: other)
        XCTAssertEqual(untouched?.generation, 3, "another computer's route is untouched")
        let defaults = UserDefaults.standard.dictionaryRepresentation().description
        XCTAssertFalse(defaults.contains(routeSecret), "no secret in UserDefaults")
    }

    @MainActor func testPreferencesHoldNoSecrets() {
        let suite = "olive.world.tests." + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let preferences = WorldPreferences(defaults: defaults)
        XCTAssertTrue(preferences.enabled, "automatic once provisioned")
        preferences.enabled = false
        XCTAssertFalse(preferences.enabled)
        preferences.setUnavailable("disabled", peerID: peer)
        XCTAssertEqual(preferences.unavailable(peerID: peer), "disabled")
        preferences.setUnavailable(nil, peerID: peer)
        XCTAssertNil(preferences.unavailable(peerID: peer))
    }
}

/// Mirrors tests/test_world_wire.py PathSelectorTests and BackoffTests.
final class WorldPathTests: XCTestCase {
    func testDirectFirstWorldAfterBoundedDelay() {
        var paths = WorldPathSelector(worldAvailable: true)
        XCTAssertEqual(paths.start(lanUsable: true), [.connect(.direct, generation: 1, delay: 0),
                                                      .connect(.world, generation: 2, delay: WorldPathSelector.worldFallbackDelay)])
        XCTAssertLessThan(WorldPathSelector.worldFallbackDelay, 3)
        var offLAN = WorldPathSelector(worldAvailable: true)
        XCTAssertEqual(offLAN.start(lanUsable: false).last, .connect(.world, generation: 2, delay: 0))
    }

    func testDirectPreferredEitherOrder() {
        var paths = WorldPathSelector(worldAvailable: true)
        _ = paths.start(lanUsable: true)
        XCTAssertEqual(paths.authenticated(.world, generation: 2), [])
        XCTAssertEqual(paths.authenticated(.direct, generation: 1), [.close(.world, generation: 2)])
        XCTAssertEqual(paths.active, .direct)
        var reverse = WorldPathSelector(worldAvailable: true)
        _ = reverse.start(lanUsable: true)
        _ = reverse.authenticated(.direct, generation: 1)
        XCTAssertEqual(reverse.authenticated(.world, generation: 2), [.close(.world, generation: 2)])
        XCTAssertEqual(reverse.state, .direct)
    }

    func testHandoverAndStaleCallbacks() {
        var paths = WorldPathSelector(worldAvailable: true)
        _ = paths.start(lanUsable: true)
        _ = paths.authenticated(.world, generation: 2)
        _ = paths.authenticated(.direct, generation: 1)
        XCTAssertEqual(paths.failed(.world, generation: 2), [], "retired World generation ignored")
        let fallback = paths.failed(.direct, generation: 1)
        XCTAssertEqual(fallback, [.connect(.world, generation: 3, delay: 0)], "Direct died: World now")
        XCTAssertEqual(paths.failed(.direct, generation: 1), [], "duplicate death ignored")
        XCTAssertEqual(paths.authenticated(.direct, generation: 1), [.close(.direct, generation: 1)], "late success of a dead attempt closed")
        _ = paths.authenticated(.world, generation: 3)
        XCTAssertEqual(paths.state, .world)
        XCTAssertEqual(paths.directCandidate(), [.connect(.direct, generation: 4, delay: 0)])
        XCTAssertEqual(paths.directCandidate(), [], "one Direct probe at a time")
        XCTAssertEqual(paths.authenticated(.direct, generation: 4), [.close(.world, generation: 3)])
        XCTAssertEqual(paths.active, .direct)
    }

    func testForcedWorldDirectOnlyAndRevoked() {
        var forced = WorldPathSelector(worldAvailable: true, directAllowed: false)
        XCTAssertEqual(forced.start(lanUsable: true), [.connect(.world, generation: 1, delay: 0)])
        var direct = WorldPathSelector(worldAvailable: true, worldAllowed: false)
        XCTAssertEqual(direct.start(lanUsable: false), [.connect(.direct, generation: 1, delay: 0)])
        var paths = WorldPathSelector(worldAvailable: true)
        _ = paths.start(lanUsable: true)
        _ = paths.authenticated(.direct, generation: 1)
        XCTAssertFalse(paths.revoke().isEmpty)
        XCTAssertEqual(paths.start(lanUsable: true), [])
        XCTAssertEqual(paths.state, .revoked)
    }

    func testBackoffIsBoundedJitteredAndResets() {
        var backoff = WorldBackoff()
        let delays = (0..<10).map { _ in backoff.next(random: 1) }
        XCTAssertEqual(delays.first ?? 0, 0.6, accuracy: 0.001)
        XCTAssertLessThanOrEqual(delays.max() ?? 0, 36)
        backoff.settled(lived: 5)
        XCTAssertGreaterThan(backoff.next(random: 0), 20)
        backoff.settled(lived: 31)
        XCTAssertLessThan(backoff.next(random: 0), 1)
    }
}
