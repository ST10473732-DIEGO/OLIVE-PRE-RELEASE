import XCTest
import CryptoKit
@testable import OLIVEMobile

final class ConnectProtocolTests: XCTestCase {
    private func vectors() throws -> ConnectJSON {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "vectors", withExtension: "json"))
        return try ConnectJSON.decode(Data(contentsOf: url), limit: 200_000)
    }
    func testCanonicalPythonVectors() throws {
        let v = try vectors()
        let offer = try PairingOffer(v["offer"].canonical, now: v["offer"]["created_at"].integer!)
        let reply = try PairingOffer(v["reply"].canonical, now: v["offer"]["created_at"].integer!)
        XCTAssertEqual(offer.identity.fingerprint, v["fingerprint"].string)
        XCTAssertEqual(ConnectJSON.array([offer.wire,reply.wire]).digest, v["binding"].string)
        XCTAssertEqual(String(decoding: PairingOffer.receiptMessage(offer: offer, reply: reply, deviceID: reply.identity.deviceID), as: UTF8.self), v["receipt_message"].string)
        for name in ["start","poll","cancel","status","response","capabilities"] {
            let frame = try ConnectFrame(kind: name == "response" || name == "capabilities" ? 10 : 9, payload: v[name].canonical).encode()
            XCTAssertEqual(frame.hex, v[name + "_frame"].string)
            XCTAssertEqual(try ConnectFrame.header(Data(frame.prefix(6))).0, v[name].canonical.count)
        }
        _ = try InferenceWire.response(v["capabilities"].canonical)
    }
    func testStrictJSONRejectsDuplicatesTruncationAndNonIntegers() {
        for text in ["{\"a\":1,\"a\":2}", "{\"a\":true", "[1,]", "01", "1.0", "NaN", "{\"a\":1,\"\\u0061\":2}"] {
            XCTAssertThrowsError(try ConnectJSON.decode(Data(text.utf8)), text)
        }
    }
    func testFrameLimitsAndVersions() throws {
        XCTAssertThrowsError(try ConnectFrame(kind: 9, payload: Data(repeating: 0, count: 72001)).encode())
        XCTAssertThrowsError(try ConnectFrame.header(Data([0,0,0,0,2,4])))
        XCTAssertThrowsError(try ConnectFrame.header(Data([0,0,0,1,1,4])))
        XCTAssertThrowsError(try ConnectFrame.header(Data([0,0,0,0,1,99])))
        for size in 0..<6 { XCTAssertThrowsError(try ConnectFrame.header(Data(repeating: 0, count: size))) }
    }
    func testPeerIdentityMismatchAndCertificateTampering() throws {
        var identity = try vectors()["offer"]["identity"].object!
        identity["device_id"] = .string(UUID().uuidString.lowercased())
        XCTAssertThrowsError(try ConnectPublicIdentity(.object(identity)))
        identity = try vectors()["offer"]["identity"].object!
        var der = Data(base64Encoded: identity["certificate"]!.string!)!; der[der.count - 1] ^= 1
        identity["certificate"] = .string(der.base64EncodedString())
        XCTAssertThrowsError(try ConnectPublicIdentity(.object(identity)))
    }
    func testInferenceSequenceLimitsAndTerminalSuppression() throws {
        let v = try vectors()
        var accumulator = InferenceAccumulator()
        let r = try InferenceWire.response(v["response"].canonical)["result"]
        try accumulator.consume(r)
        XCTAssertEqual(accumulator.text, "391 🫒")
        XCTAssertThrowsError(try accumulator.consume(r))
        try accumulator.consume(.object(["state": .string("cancelled"), "events": .array([]), "error": .string("cancelled")]))
        try accumulator.consume(r)
        XCTAssertEqual(accumulator.text, "391 🫒")
    }
    func testInputBoundsAndPublicRoles() throws {
        XCTAssertThrowsError(try InferenceWire.startArguments(preset: "deep", messages: [("user","hi")]))
        XCTAssertThrowsError(try InferenceWire.startArguments(preset: "normal", messages: [("user",String(repeating: "🫒", count: 4001))]))
        XCTAssertThrowsError(try InferenceWire.startArguments(preset: "normal", messages: [("system","hi")]))
        let v = try vectors()["start"]
        let args = try InferenceWire.startArguments(preset: "normal", messages: [("user", v["arguments"]["messages"].array![0]["content"].text())])
        XCTAssertEqual(args, v["arguments"])
    }
    func testEndpointValidation() {
        for value in ["192.168.1.2", "10.0.0.1", "172.16.0.1", "fd00::1"] { XCTAssertTrue(PairingOffer.localAddress(value)) }
        for value in ["8.8.8.8", "192.168.01.2", "example.local", "fe80::1", "::ffff:192.168.1.2", "0.0.0.0"] { XCTAssertFalse(PairingOffer.localAddress(value)) }
    }
    func testKeychainIdentitySurvivesStoreRecreation() async throws {
        let secrets = KeychainSecretStore(service: "olive.identity.tests.\(UUID().uuidString)")
        do {
            let first = try await ConnectIdentityStore(secrets: secrets).load()
            let second = try await ConnectIdentityStore(secrets: secrets).load()
            XCTAssertEqual(first.publicIdentity, second.publicIdentity)
            let verifier = try Curve25519.Signing.PublicKey(rawRepresentation: first.publicIdentity.publicKey)
            XCTAssertTrue(try verifier.isValidSignature(first.sign(Data("test".utf8)), for: Data("test".utf8)))
            XCTAssertTrue(try verifier.isValidSignature(second.sign(Data("test".utf8)), for: Data("test".utf8)))
            try await secrets.remove(account: "mobile-identity-v1")
            do { _ = try await ConnectIdentityStore(secrets: secrets).load(); XCTFail("Missing private identity must not be replaced") } catch {}
            let absent = try await secrets.read(account: "mobile-identity-v1")
            XCTAssertNil(absent)
            try await secrets.write(Data("corrupt".utf8), account: "mobile-identity-v1")
            do { _ = try await ConnectIdentityStore(secrets: secrets).load(); XCTFail("Must not replace identity") } catch {}
            let preserved = try await secrets.read(account: "mobile-identity-v1")
            XCTAssertEqual(preserved, Data("corrupt".utf8))
            try await secrets.remove(account: "mobile-identity-v1")
            try await secrets.remove(account: "mobile-identity-reservation-v1")
        } catch { try? await secrets.remove(account: "mobile-identity-v1"); try? await secrets.remove(account: "mobile-identity-reservation-v1"); throw error }
    }
    @MainActor func testUnpairAndPendingDoNotCreateTrust() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: dir) }
        let repository = ConnectTrustRepository(directory: dir)
        let v = try vectors()
        let offer = try PairingOffer(v["offer"].canonical, now: v["offer"]["created_at"].integer!)
        try repository.reserve(offer)
        XCTAssertTrue(ConnectTrustRepository(directory: dir).peers.isEmpty)
        XCTAssertThrowsError(try repository.reserve(offer))
        try repository.cancel(offer.sessionID)
        XCTAssertThrowsError(try repository.commit(offer: offer, peerReceipt: Data()))
    }
    @MainActor func testReceiptRecoveryRequiresOriginalLocalConfirmationAndUnpairRemovesPin() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: dir) }
        let local = try ConnectIdentity.generate(), remote = try ConnectIdentity.generate()
        let now = Int64(Date().timeIntervalSince1970)
        let offer = try PairingOffer(ConnectJSON.object(["protocol": .string("olive-pairing-tls13/2"), "session_id": .string(UUID().uuidString.lowercased()),
            "created_at": .int(now), "expires_at": .int(now+120), "identity": remote.publicIdentity.wire,
            "endpoint": .object(["address": .string("192.168.1.2"), "port": .int(54321)]), "display_name": .string("Fixture")]).canonical)
        let reply = try offer.reply(identity: local.publicIdentity, name: "Phone")
        let localReceipt = try local.sign(PairingOffer.receiptMessage(offer: offer, reply: reply, deviceID: local.publicIdentity.deviceID))
        let peerReceipt = try remote.sign(PairingOffer.receiptMessage(offer: offer, reply: reply, deviceID: remote.publicIdentity.deviceID))
        let completion = ConnectJSON.object(["protocol": .string("olive-pairing-completion/1"), "offer": offer.wire, "reply": reply.wire,
            "receipts": .object([local.publicIdentity.deviceID: .string(localReceipt.base64EncodedString()), remote.publicIdentity.deviceID: .string(peerReceipt.base64EncodedString())])])
        let repository = ConnectTrustRepository(directory: dir)
        try repository.reserve(offer)
        XCTAssertThrowsError(try repository.importCompletion(completion.canonical))
        try repository.recordConfirmation(offer: offer, reply: reply, receipt: localReceipt)
        XCTAssertThrowsError(try repository.commit(offer: offer, peerReceipt: Data(repeating: 0, count: 64)))
        let restarted = ConnectTrustRepository(directory: dir)
        XCTAssertTrue(restarted.peers.isEmpty)
        try restarted.importCompletion(completion.canonical)
        XCTAssertEqual(restarted.peers.first?.identity, remote.publicIdentity)
        try restarted.unpair(remote.publicIdentity.deviceID)
        XCTAssertTrue(ConnectTrustRepository(directory: dir).peers.isEmpty)
        let raw = try String(contentsOf: dir.appendingPathComponent("trust-v1.json"), encoding: .utf8)
        XCTAssertFalse(raw.contains(remote.publicIdentity.certificate.base64EncodedString()))
        XCTAssertThrowsError(try restarted.importCompletion(completion.canonical))
    }
    @MainActor func testNearbyBoundedDeduplicationAndRemovalSnapshot() {
        let entries = (0..<80).map { NearbyConnectPeer(id: String($0), endpoint: .service(name: String($0), type: "_olive-connect._tcp", domain: "local.", interface: nil)) }
        XCTAssertEqual(ConnectDiscoveryService.bounded(entries).count, 64)
        XCTAssertEqual(ConnectDiscoveryService.bounded([entries[0],entries[0]]).count, 1)
        XCTAssertTrue(ConnectDiscoveryService.bounded([]).isEmpty)
    }
    func testCodeRenderingPreservesFencedContent() {
        XCTAssertEqual(ChatMessage.parse("Example\n```swift\nfunc even(_ n: Int) -> Bool { n % 2 == 0 }\n```"),
            [.text("Example"), .code(language: "swift", content: "func even(_ n: Int) -> Bool { n % 2 == 0 }")])
    }
}

private actor InferenceTestTransport: InferenceTransport {
    var generating = false
    var released = false
    var calls: [String] = []
    var polls = 0
    var hold = false
    init(hold: Bool = false) { self.hold = hold }
    func exchange(_ req: ConnectJSON) async throws -> ConnectJSON {
        let operation = req["operation"].string!
        calls.append(operation)
        var result: ConnectJSON
        switch operation {
        case "start":
            generating = true; released = false; polls = 0
            result = .object(["state": .string("queued"), "events": .array([]), "error": .null])
        case "cancel":
            // Represents the release acknowledgement, not a renderer-only stop.
            try await Task.sleep(for: .milliseconds(100))
            generating = false; released = true; hold = false
            result = .object(["state": .string("cancelled"), "events": .array([]), "error": .string("cancelled")])
        default:
            if hold { try await Task.sleep(for: .milliseconds(150)) }
            polls += 1
            if !generating { result = .object(["state": .string("cancelled"), "events": .array([]), "error": .string("cancelled")]) }
            else {
                let complete = !hold && polls >= 2
                if complete { generating = false; released = true }
                result = .object(["state": .string(complete ? "completed" : "streaming"),
                    "events": .array([.object(["sequence": .int(Int64(polls)), "text": .string(polls == 1 ? "3" : "91")])]), "error": .null])
            }
        }
        return .object(["protocol_version": .string("olive-inference/1"), "request_id": req["request_id"], "job_id": req["job_id"], "result": result, "error": .null])
    }
    func close() { generating = false }
}
private actor InferenceUpdates {
    var values: [(String,String)] = []
    func append(_ state: String, _ text: String) { values.append((state,text)) }
    var lastText: String? { values.last?.1 }
}
final class RemoteLifecycleTests: XCTestCase {
    func testIncrementalRequestAndCompletion() async throws {
        let transport = InferenceTestTransport(), updates = InferenceUpdates()
        let client = RemoteInferenceClient(transport: transport, source: UUID().uuidString.lowercased(), target: UUID().uuidString.lowercased())
        try await client.run(preset: "normal", messages: [("user","17 * 23")]) { _, state, text in await updates.append(state,text) }
        let last = await updates.lastText, calls = await transport.calls
        XCTAssertEqual(last, "391"); XCTAssertEqual(calls, ["start","poll","poll"])
    }
    func testStopWaitsForReleaseSuppressesLatePollAndAllowsNextRequest() async throws {
        let transport = InferenceTestTransport(hold: true), updates = InferenceUpdates()
        let client = RemoteInferenceClient(transport: transport, source: UUID().uuidString.lowercased(), target: UUID().uuidString.lowercased())
        let running = Task { try await client.run(preset: "fast", messages: [("user","example")]) { _, state, text in await updates.append(state,text) } }
        for _ in 0..<100 { if await transport.generating { break }; try await Task.sleep(for: .milliseconds(5)) }
        let state = try await client.stop(), released = await transport.released
        XCTAssertEqual(state, "cancelled"); XCTAssertTrue(released)
        do { try await running.value; XCTFail("Cancelled request cannot complete") } catch {}
        let stoppedText = await updates.lastText
        XCTAssertEqual(stoppedText, "")
        _ = try await client.stop() // Repeated stop is inert.
        try await client.run(preset: "normal", messages: [("user","new request")]) { _, state, text in await updates.append(state,text) }
        let nextText = await updates.lastText
        XCTAssertEqual(nextText, "391")
    }
}

@MainActor private final class ChatTestStore: ShellStore {
    var text = ""
    func loadDestination() -> Destination { .chat }
    func saveDestination(_ value: Destination) {}
    func loadDraft() throws -> String { text }
    func saveDraft(_ value: String) throws { text = value }
}
@MainActor private final class ChatTestConnection: ChatRemoteSession {
    var connected = true
    let selectedID: String? = UUID().uuidString.lowercased()
    var capability: ConnectJSON? = .object(["permission": .string("allow"), "presets": .object(["normal": .bool(true)])])
    let inference: RemoteInferenceClient?
    init(_ transport: any InferenceTransport) {
        inference = RemoteInferenceClient(transport: transport, source: UUID().uuidString.lowercased(), target: selectedID!)
    }
}
@MainActor final class MobileChatStateTests: XCTestCase {
    func testOffAndOfflinePreserveDraftWithoutSending() async throws {
        let transport = InferenceTestTransport(), connection = ChatTestConnection(transport)
        let state = AppState(store: ChatTestStore(), chatConnection: connection)
        state.draft = "Keep this question"
        connection.connected = false
        state.send()
        XCTAssertEqual(state.draft, "Keep this question"); XCTAssertTrue(state.messages.isEmpty)
        connection.connected = true
        connection.capability = .object(["permission": .string("deny"), "presets": .object(["normal": .bool(true)])])
        state.send()
        let calls = await transport.calls
        XCTAssertTrue(calls.isEmpty); XCTAssertFalse(state.canSend)
    }
    func testDuplicateSubmitAndDraftAdmissionThenCompletion() async throws {
        let transport = InferenceTestTransport(), connection = ChatTestConnection(transport)
        let state = AppState(store: ChatTestStore(), chatConnection: connection)
        state.draft = "Question"
        state.send(); state.send()
        for _ in 0..<100 { if !state.active { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertEqual(state.chatStatus, "Completed"); XCTAssertEqual(state.draft, "")
        XCTAssertEqual(state.messages.filter { $0.role == .user }.count, 1)
        let calls = await transport.calls
        XCTAssertEqual(calls.filter { $0 == "start" }.count, 1)
        XCTAssertNotNil(state.messages.last?.attribution?.requestID)
    }
    func testStopBackgroundRaceCannotOverwriteNewState() async throws {
        let transport = InferenceTestTransport(hold: true), connection = ChatTestConnection(transport)
        let state = AppState(store: ChatTestStore(), chatConnection: connection)
        state.draft = "Long request"; state.send()
        for _ in 0..<100 { if await transport.generating { break }; try await Task.sleep(for: .milliseconds(5)) }
        state.stop(); state.suspend()
        let interrupted = state.chatStatus
        try await Task.sleep(for: .milliseconds(300))
        XCTAssertEqual(state.chatStatus, interrupted)
        XCTAssertFalse(state.active)
        XCTAssertTrue(state.messages.allSatisfy { $0.status == "Interrupted · connection closed" })
    }
}
