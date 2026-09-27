import XCTest
import CryptoKit
import Network
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
        for code in ["busy", "rate_limited", "model_unavailable", "unknown_request"] {
            let value = try InferenceWire.response(v["admission_errors"][code].canonical)
            XCTAssertEqual(value["error"], .string(code)); XCTAssertEqual(value["result"], .null)
            XCTAssertEqual(try ConnectFrame(kind: 10, payload: value.canonical).encode().hex, v["admission_error_frames"][code].string)
        }
        XCTAssertEqual(InferenceWire.failure("rate_limited"), .rateLimited)
        XCTAssertEqual(InferenceWire.failure("busy"), .resourceBusy)
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
    func testLongConversationKeepsRecentWholeTurnsWithinDesktopBounds() throws {
        let history = (0..<30).flatMap { [("user", "question \($0)"), ("assistant", String(repeating: "🫒", count: 2000))] }
        let context = InferenceWire.context(history: history, user: "next question")
        XCTAssertLessThanOrEqual(context.count, 24)
        XCTAssertLessThanOrEqual(context.reduce(0) { $0 + $1.1.utf8.count }, 48000)
        XCTAssertEqual(context.first?.0, "user")
        XCTAssertEqual(context.last?.1, "next question")
        XCTAssertEqual(context[context.count - 3].1, "question 29")
        _ = try InferenceWire.startArguments(preset: "fast", messages: context)
        let largeAnswer = [("user", "long question"), ("assistant", String(repeating: "x", count: 16001))]
        XCTAssertEqual(InferenceWire.context(history: largeAnswer, user: "next").count, 1)
    }
    func testModelAndSizeFailuresAreNotReportedAsMalformedMessages() {
        XCTAssertEqual(InferenceWire.failure("inference_failed"), .inferenceFailed)
        XCTAssertEqual(InferenceWire.failure("input_too_large"), .inputTooLarge)
        XCTAssertEqual(InferenceWire.failure("output_limit"), .outputLimit)
        XCTAssertEqual(InferenceWire.failure("stream_invalid"), .streamInvalid)
        XCTAssertEqual(InferenceWire.failure("ledger_full"), .requestLedgerFull)
        XCTAssertEqual(InferenceWire.failure("invalid_request"), .responseMalformed)
    }
    @MainActor func testDiscoveryRestartAnnouncesNewCandidateButDoesNotAuthenticate() {
        let discovery = ConnectDiscoveryService()
        var notifications = 0
        discovery.onNewEndpoints = { notifications += 1 }
        let first = NearbyConnectPeer(id: "first", endpoint: .service(name: "first", type: "_olive-connect._tcp", domain: "local.", interface: nil))
        let restart = NearbyConnectPeer(id: "restart", endpoint: .service(name: "restart", type: "_olive-connect._tcp", domain: "local.", interface: nil))
        discovery.updateNearby([first]); discovery.updateNearby([first])
        XCTAssertEqual(notifications, 1)
        discovery.updateNearby([])
        XCTAssertEqual(notifications, 1)
        discovery.updateNearby([restart])
        XCTAssertEqual(notifications, 2)
        XCTAssertEqual(discovery.revision, 2)
        XCTAssertEqual(discovery.nearby.map(\.id), ["restart"])
        discovery.stop()
        XCTAssertTrue(discovery.nearby.isEmpty)
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
    func testExplicitIdentityResetPersistsNewKey() async throws {
        let secrets = KeychainSecretStore(service: "olive.identity.reset.tests.\(UUID().uuidString)")
        do {
            let store = ConnectIdentityStore(secrets: secrets)
            let old = try await store.load()
            let replacement = try await store.reset()
            XCTAssertNotEqual(old.publicIdentity.deviceID, replacement.publicIdentity.deviceID)
            XCTAssertNotEqual(old.publicIdentity.publicKey, replacement.publicIdentity.publicKey)
            let restored = try await ConnectIdentityStore(secrets: secrets).load(allowCreation: false)
            XCTAssertEqual(restored.publicIdentity, replacement.publicIdentity)
            let verifier = try Curve25519.Signing.PublicKey(rawRepresentation: restored.publicIdentity.publicKey)
            let message = Data("reset acceptance".utf8)
            XCTAssertTrue(try verifier.isValidSignature(restored.sign(message), for: message))
            XCTAssertFalse(try verifier.isValidSignature(old.sign(message), for: message))
            try await secrets.remove(account: "mobile-identity-v1")
            try await secrets.remove(account: "mobile-identity-reservation-v1")
        } catch {
            try? await secrets.remove(account: "mobile-identity-v1")
            try? await secrets.remove(account: "mobile-identity-reservation-v1")
            throw error
        }
    }
    func testInterruptedIdentityResetRequiresExplicitRecovery() async throws {
        let secrets = ResetFaultSecretStore()
        let store = ConnectIdentityStore(secrets: secrets)
        let original = try await store.load()
        let originalEnvelope = try await secrets.read(account: "mobile-identity-v1")
        await secrets.failNextEnvelopeWrite()
        do { _ = try await store.reset(); XCTFail("Expected injected Keychain failure") } catch {}
        let retainedEnvelope = try await secrets.read(account: "mobile-identity-v1")
        XCTAssertEqual(retainedEnvelope, originalEnvelope)
        for loader in [store, ConnectIdentityStore(secrets: secrets)] {
            do { _ = try await loader.load(); XCTFail("Interrupted reset must fail closed") } catch {}
        }
        let replacement = try await store.reset()
        let restored = try await ConnectIdentityStore(secrets: secrets).load(allowCreation: false)
        XCTAssertEqual(restored.publicIdentity, replacement.publicIdentity)
        XCTAssertNotEqual(restored.publicIdentity.publicKey, original.publicIdentity.publicKey)
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
        XCTAssertThrowsError(try restarted.prepareIdentityReset())
        XCTAssertFalse(ConnectSession(repository: restarted).canResetIdentity)
        try restarted.unpair(remote.publicIdentity.deviceID)
        XCTAssertTrue(ConnectTrustRepository(directory: dir).peers.isEmpty)
        let raw = try String(contentsOf: dir.appendingPathComponent("trust-v1.json"), encoding: .utf8)
        XCTAssertFalse(raw.contains(remote.publicIdentity.certificate.base64EncodedString()))
        XCTAssertThrowsError(try restarted.importCompletion(completion.canonical))
        let interrupted = ConnectTrustRepository(directory: dir.appendingPathComponent("interrupted"))
        try interrupted.reserve(offer)
        try interrupted.recordConfirmation(offer: offer, reply: reply, receipt: localReceipt)
        XCTAssertEqual(interrupted.interruptedSessions, [offer.sessionID])
        try interrupted.prepareIdentityReset()
        let afterReset = ConnectTrustRepository(directory: dir.appendingPathComponent("interrupted"))
        XCTAssertTrue(afterReset.interruptedSessions.isEmpty)
        XCTAssertThrowsError(try afterReset.importCompletion(completion.canonical))
        XCTAssertThrowsError(try afterReset.reserve(offer))
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

private actor ResetFaultSecretStore: SecretStore {
    private var values: [String: Data] = [:]
    private var failEnvelope = false
    func failNextEnvelopeWrite() { failEnvelope = true }
    func read(account: String) throws -> Data? { values[account] }
    func write(_ data: Data, account: String) throws {
        if account == "mobile-identity-v1", failEnvelope {
            failEnvelope = false
            throw ConnectFailure.identityRecoveryRequired
        }
        values[account] = data
    }
    func remove(account: String) throws { values.removeValue(forKey: account) }
}

private actor InferenceTestTransport: InferenceTransport {
    var generating = false
    var released = false
    var calls: [String] = []
    var polls = 0
    var hold = false
    let rejectStart: Bool
    let failPoll: Bool
    let terminalError: String?
    init(hold: Bool = false, rejectStart: Bool = false, failPoll: Bool = false, terminalError: String? = nil) {
        self.hold = hold; self.rejectStart = rejectStart; self.failPoll = failPoll
        self.terminalError = terminalError
    }
    func exchange(_ req: ConnectJSON) async throws -> ConnectJSON {
        let operation = req["operation"].string!
        calls.append(operation)
        var result: ConnectJSON
        switch operation {
        case "start":
            if rejectStart { throw ConnectFailure.permissionDenied }
            generating = true; released = false; polls = 0
            result = .object(["state": .string("queued"), "events": .array([]), "error": .null])
        case "cancel":
            // Represents the release acknowledgement, not a renderer-only stop.
            try await Task.sleep(for: .milliseconds(100))
            generating = false; released = true; hold = false
            result = .object(["state": .string("cancelled"), "events": .array([]), "error": .string("cancelled")])
        default:
            if failPoll { throw ConnectFailure.connectionLost }
            if hold { try await Task.sleep(for: .milliseconds(150)) }
            polls += 1
            if !generating { result = .object(["state": .string("cancelled"), "events": .array([]), "error": .string("cancelled")]) }
            else {
                let complete = !hold && polls >= 2
                if complete { generating = false; released = true }
                result = .object(["state": .string(complete ? terminalError == nil ? "completed" : "failed" : "streaming"),
                    "events": .array([.object(["sequence": .int(Int64(polls)), "text": .string(polls == 1 ? "3" : "91")])]),
                    "error": complete ? terminalError.map(ConnectJSON.string) ?? .null : .null])
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
/// Desktop C7 rejects a start with result=null/error=code, without a job.
/// Cancelling that rejected ID returns unknown_request on the same healthy channel.
private actor AdmissionTestTransport: InferenceTransport {
    var rejection: String?
    let failUncertainStart: Bool
    let rejectPoll: Bool
    var calls: [String] = []
    var closes = 0
    private var job: String?
    init(rejection: String? = nil, failUncertainStart: Bool = false, rejectPoll: Bool = false) {
        self.rejection = rejection; self.failUncertainStart = failUncertainStart; self.rejectPoll = rejectPoll
    }
    func allow() { rejection = nil }
    func exchange(_ req: ConnectJSON) async throws -> ConnectJSON {
        guard closes == 0 else { throw ConnectFailure.peerOffline }
        let operation = try req["operation"].text()
        calls.append(operation)
        var error: ConnectJSON = .null, result: ConnectJSON = .null
        switch operation {
        case "start":
            if let rejection { error = .string(rejection) }
            else {
                job = req["job_id"].string
                if failUncertainStart { throw ConnectFailure.connectionLost }
                result = .object(["state": .string("queued"), "events": .array([]), "error": .null])
            }
        case "poll":
            if rejectPoll { error = .string("rate_limited") }
            else { result = .object(["state": .string("completed"), "events": .array([
                .object(["sequence": .int(1), "text": .string("391")])]), "error": .null]); job = nil }
        case "cancel":
            if failUncertainStart { throw ConnectFailure.connectionLost }
            if job == nil { error = .string("unknown_request") }
            else { job = nil; result = .object(["state": .string("cancelled"), "events": .array([]), "error": .string("cancelled")]) }
        case "status":
            result = .object(["presets": .object(["fast": .bool(true), "normal": .bool(true), "max": .bool(false)]),
                "permission": .string("allow"), "busy": .bool(false)])
        default: throw ConnectFailure.responseMalformed
        }
        return try InferenceWire.response(ConnectJSON.object(["protocol_version": .string("olive-inference/1"),
            "request_id": req["request_id"], "job_id": req["job_id"], "result": result, "error": error]).canonical)
    }
    func close() { closes += 1; job = nil }
}
final class RemoteLifecycleTests: XCTestCase {
    func testAdmissionRejectionsPreserveChannelAndAllowExplicitRetry() async throws {
        for (code, expected) in [("rate_limited", ConnectFailure.rateLimited), ("busy", .resourceBusy), ("model_unavailable", .capabilityUnavailable)] {
            let transport = AdmissionTestTransport(rejection: code)
            let client = RemoteInferenceClient(transport: transport, source: UUID().uuidString.lowercased(), target: UUID().uuidString.lowercased())
            do {
                try await client.run(preset: "normal", messages: [("user", "Question")]) { _, _, _ in XCTFail("Rejected start cannot produce a response") }
                XCTFail("Expected rejection")
            } catch { XCTAssertEqual(error as? ConnectFailure, expected) }
            let rejectedCalls = await transport.calls, closes = await transport.closes
            XCTAssertEqual(rejectedCalls, ["start"]); XCTAssertEqual(closes, 0)
            let status = try await client.status()
            XCTAssertEqual(status["permission"], .string("allow"))
            await transport.allow() // Capacity/cooldown recovers; no reconnect.
            let updates = InferenceUpdates()
            try await client.run(preset: "normal", messages: [("user", "Retry")]) { _, state, text in await updates.append(state, text) }
            let answer = await updates.lastText, finalCloses = await transport.closes
            XCTAssertEqual(answer, "391"); XCTAssertEqual(finalCloses, 0)
        }
    }
    func testUncertainStartStillCancelsAndClosesWhenCleanupFails() async throws {
        let transport = AdmissionTestTransport(failUncertainStart: true)
        let client = RemoteInferenceClient(transport: transport, source: UUID().uuidString.lowercased(), target: UUID().uuidString.lowercased())
        do { try await client.run(preset: "normal", messages: [("user", "Question")]) { _, _, _ in }; XCTFail("Expected connection loss") }
        catch { XCTAssertEqual(error as? ConnectFailure, .connectionLost) }
        let calls = await transport.calls, closes = await transport.closes
        XCTAssertEqual(calls, ["start", "cancel"]); XCTAssertEqual(closes, 1)
    }
    func testRejectionAfterAdmissionStillCancelsActualJob() async throws {
        let transport = AdmissionTestTransport(rejectPoll: true)
        let client = RemoteInferenceClient(transport: transport, source: UUID().uuidString.lowercased(), target: UUID().uuidString.lowercased())
        do { try await client.run(preset: "normal", messages: [("user", "Question")]) { _, _, _ in }; XCTFail("Expected poll rejection") }
        catch { XCTAssertEqual(error as? ConnectFailure, .rateLimited) }
        let calls = await transport.calls
        XCTAssertEqual(calls, ["start", "poll", "cancel"])
    }
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
    func testRateLimitPreservesDraftAndConnectionWithoutAutomaticRetry() async throws {
        let transport = AdmissionTestTransport(rejection: "rate_limited")
        let state = AppState(store: ChatTestStore(), chatConnection: ChatTestConnection(transport))
        state.draft = "Keep this question"; state.send()
        for _ in 0..<100 { if !state.active { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertFalse(state.active); XCTAssertTrue(state.canSend)
        XCTAssertEqual(state.draft, "Keep this question")
        XCTAssertTrue(state.chatStatus.contains("request limit")); XCTAssertFalse(state.chatStatus.contains("busy"))
        let calls = await transport.calls, closes = await transport.closes
        XCTAssertEqual(calls, ["start"]); XCTAssertEqual(closes, 0)
        await transport.allow()
        XCTAssertEqual(state.messages.filter { $0.role == .user }.count, 1)
        state.send()
        for _ in 0..<100 { if !state.active { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertEqual(state.chatStatus, "Completed"); XCTAssertTrue(state.draft.isEmpty)
    }
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
    func testAdmittedStopKeepsComposerAndSavedDraftEmpty() async throws {
        let transport = InferenceTestTransport(hold: true), store = ChatTestStore()
        let state = AppState(store: store, chatConnection: ChatTestConnection(transport))
        state.draft = "Long request"; state.send()
        for _ in 0..<100 { if state.draft.isEmpty { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertTrue(state.draft.isEmpty); XCTAssertTrue(store.text.isEmpty)
        XCTAssertEqual(state.messages.first?.plainText, "Long request")
        state.stop()
        for _ in 0..<100 { if !state.active { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertEqual(state.chatStatus, "Cancelled")
        XCTAssertTrue(state.draft.isEmpty)
        XCTAssertTrue(AppState(store: store).draft.isEmpty)
    }
    func testNewIdenticalDraftSurvivesResponseUpdatesAndStop() async throws {
        let transport = InferenceTestTransport(hold: true)
        let state = AppState(store: ChatTestStore(), chatConnection: ChatTestConnection(transport))
        state.draft = "Question"; state.send()
        for _ in 0..<100 { if state.draft.isEmpty { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertTrue(state.draft.isEmpty)
        state.draft = "Question" // A new draft may intentionally repeat the sent text.
        for _ in 0..<100 { if await transport.polls >= 2 { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertEqual(state.draft, "Question")
        state.stop()
        for _ in 0..<100 { if !state.active { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertEqual(state.draft, "Question")
    }
    func testRejectedStartKeepsDraftAndVisibleFailedTurn() async throws {
        let store = ChatTestStore()
        let state = AppState(store: store, chatConnection: ChatTestConnection(InferenceTestTransport(rejectStart: true)))
        state.draft = "Keep this question"; state.send()
        for _ in 0..<100 { if !state.active { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertFalse(state.active); XCTAssertEqual(state.draft, "Keep this question")
        XCTAssertEqual(store.text, "Keep this question")
        XCTAssertEqual(state.messages.first?.plainText, "Keep this question")
        XCTAssertTrue(state.messages.first?.status?.hasPrefix("Failed") == true)
    }
    func testConnectionFailureRestoresUntouchedAdmittedDraftForExplicitRetry() async throws {
        let store = ChatTestStore()
        let state = AppState(store: store, chatConnection: ChatTestConnection(InferenceTestTransport(failPoll: true)))
        state.draft = "Retry this question"; state.send()
        for _ in 0..<100 { if !state.active { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertFalse(state.active); XCTAssertTrue(state.chatStatus.hasPrefix("Failed"))
        XCTAssertEqual(state.draft, "Retry this question"); XCTAssertEqual(store.text, state.draft)
    }
    func testOutputLimitKeepsPartialAnswerAndRestoresDraftWithoutResending() async throws {
        let transport = InferenceTestTransport(terminalError: "output_limit")
        let state = AppState(store: ChatTestStore(), chatConnection: ChatTestConnection(transport))
        state.draft = "A bounded synthetic request"; state.send()
        for _ in 0..<150 { if !state.active { break }; try await Task.sleep(for: .milliseconds(10)) }
        XCTAssertFalse(state.active)
        XCTAssertTrue(state.chatStatus.contains(ConnectFailure.outputLimit.localizedDescription))
        XCTAssertTrue(state.chatStatus.contains("Draft restored; nothing was resent."))
        XCTAssertEqual(state.draft, "A bounded synthetic request")
        XCTAssertEqual(state.messages.last?.plainText, "391")
        XCTAssertEqual(state.messages.last?.status, "Incomplete")
        let calls = await transport.calls
        XCTAssertEqual(calls.filter { $0 == "start" }.count, 1)
        XCTAssertEqual(calls.last, "cancel")
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

/// Explicit real-device negative test. It never edits production trust or keys,
/// and probes a wrong pin only after authenticating the real paired endpoint.
final class RealConnectSecurityTests: XCTestCase {
    @MainActor func testRealLANWrongPeerPinRejected() async throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_C92_SECURITY_ACCEPTANCE"] == "1",
                          "Requires explicit physical-iPhone / paired desktop acceptance")
        #if targetEnvironment(simulator)
        throw XCTSkip("Physical iPhone required")
        #endif
        let repository = ConnectTrustRepository()
        let before = repository.peers
        let peer = try XCTUnwrap(before.first)
        let identity = try await ConnectIdentityStore().load(allowCreation: false)
        let discovery = ConnectDiscoveryService()
        discovery.start()
        defer { discovery.stop() }
        for _ in 0..<80 {
            if !discovery.nearby.isEmpty { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        var authenticated: NWEndpoint?
        for candidate in discovery.nearby.prefix(8) {
            let transport = ConnectTransport(endpoint: candidate.endpoint)
            do {
                try await transport.connect(identity: identity, peer: peer.identity)
                authenticated = candidate.endpoint
            } catch { /* Discovery is untrusted; only a pinned success selects the target. */ }
            await transport.close()
            if authenticated != nil { break }
        }
        let endpoint = try XCTUnwrap(authenticated, "Real paired desktop must pass pinned TLS first")
        let wrongPeer = try ConnectIdentity.generate().publicIdentity
        let rejected = ConnectTransport(endpoint: endpoint)
        do {
            try await rejected.connect(identity: identity, peer: wrongPeer)
            XCTFail("Wrong peer certificate was accepted")
        } catch {
            XCTAssertEqual(error as? ConnectFailure, .certificateMismatch,
                           "A TCP timeout is not evidence of wrong-pin rejection")
        }
        await rejected.close()
        XCTAssertEqual(ConnectTrustRepository().peers, before)
        let after = try await ConnectIdentityStore().load(allowCreation: false)
        XCTAssertEqual(after.publicIdentity, identity.publicIdentity)
        print("C9.2 real LAN: correct pin authenticated; wrong pin rejected; saved identity and trust unchanged")
    }
}

final class RealConnectCancellationTests: XCTestCase {
    @MainActor func testRealLANCancellationBoundaries() async throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["OLIVE_C92_CANCEL_ACCEPTANCE"] == "1", "Explicit physical-device real-model acceptance only")
        #if targetEnvironment(simulator)
        throw XCTSkip("Physical iPhone required")
        #endif
        let peer = try XCTUnwrap(ConnectTrustRepository().peers.first)
        let identity = try await ConnectIdentityStore().load(allowCreation: false)
        let source = identity.publicIdentity.deviceID
        let discovery = ConnectDiscoveryService(); discovery.start()
        defer { discovery.stop() }
        for _ in 0..<80 {
            if !discovery.nearby.isEmpty { break }
            try await Task.sleep(for: .milliseconds(100))
        }
        var selected: (NWEndpoint, ConnectTransport)?
        for candidate in discovery.nearby.prefix(8) {
            let channel = ConnectTransport(endpoint: candidate.endpoint)
            do { try await channel.connect(identity: identity, peer: peer.identity); selected = (candidate.endpoint, channel); break }
            catch { await channel.close() }
        }
        let (endpoint, channel) = try XCTUnwrap(selected, "Authenticate the real paired desktop first")
        func request(_ operation: String, job: String? = nil, arguments: ConnectJSON = .object([:])) throws -> ConnectJSON {
            try InferenceWire.request(source: source, target: peer.id, operation: operation, job: job, arguments: arguments)
        }
        func start(_ channel: ConnectTransport, _ text: String) async throws -> String {
            let req = try request("start", arguments: InferenceWire.startArguments(preset: "normal", messages: [("user", text)]))
            let answer = try await channel.exchange(req)
            XCTAssertEqual(answer["error"], .null)
            guard answer["error"] == .null else { throw ConnectFailure.resourceBusy }
            return try req["job_id"].uuid()
        }
        func cancel(_ channel: ConnectTransport, _ job: String) async throws -> String {
            let answer = try await channel.exchange(request("cancel", job: job))
            XCTAssertEqual(answer["error"], .null)
            return try answer["result"]["state"].text()
        }
        func complete(_ channel: ConnectTransport, _ job: String) async throws {
            var accumulator = InferenceAccumulator()
            let deadline = ContinuousClock.now.advanced(by: .seconds(135))
            while ContinuousClock.now < deadline {
                let answer = try await channel.exchange(request("poll", job: job, arguments: .object(["after": .int(accumulator.sequence)])))
                XCTAssertEqual(answer["error"], .null)
                try accumulator.consume(answer["result"])
                if InferenceWire.terminal.contains(accumulator.state) {
                    XCTAssertEqual(accumulator.state, "completed")
                    XCTAssertFalse(accumulator.text.isEmpty)
                    return
                }
                try await Task.sleep(for: .milliseconds(250))
            }
            throw ConnectFailure.requestTimeout
        }
        do {
            let status = try await channel.exchange(request("status"))
            XCTAssertEqual(status["result"]["permission"], .string("allow"))
            guard status["result"]["permission"] == .string("allow") else { throw ConnectFailure.permissionDenied }
            let longPrompt = "Write a detailed 1000-word explanation of Swift arrays, dictionaries, sets, loops and functions, with small code examples."
            let early = try await start(channel, longPrompt)
            let beforeStop = ContinuousClock.now
            let stopped = try await cancel(channel, early)
            XCTAssertEqual(stopped, "cancelled")
            let repeated = try await cancel(channel, early)
            XCTAssertEqual(repeated, "cancelled")
            print("C9.2 early cancel: \(early) terminal=\(stopped) acknowledgement=\(beforeStop.duration(to: .now)) repeated=\(repeated)")
            let completed = try await start(channel, "What is 17 * 23? Answer with the number and a short explanation.")
            try await complete(channel, completed)
            let raced = try await cancel(channel, completed)
            XCTAssertEqual(raced, "completed", "Late Stop must not relabel a completed task")
            print("C9.2 completion-race cancel: \(completed) terminal=\(raced)")
            let lost = try await start(channel, longPrompt)
            try await channel.acceptanceDisconnectDuringCancel(request("cancel", job: lost))
            let replacement = ConnectTransport(endpoint: endpoint)
            do {
                try await replacement.connect(identity: identity, peer: peer.identity)
                var idle = false
                for _ in 0..<40 {
                    let state = try await replacement.exchange(request("status"))
                    if state["result"]["busy"] == .bool(false) { idle = true; break }
                    try await Task.sleep(for: .milliseconds(250))
                }
                XCTAssertTrue(idle, "Desktop must release inference after the cancel connection is lost")
                let fresh = try await start(replacement, "Explain in two sentences what a hash function does.")
                try await complete(replacement, fresh)
                print("C9.2 cancel acknowledgement deliberately lost: \(lost); fresh pinned connection, desktop idle, new request completed: \(fresh)")
                await replacement.close()
            } catch { await replacement.close(); throw error }
            await channel.close()
        } catch { await channel.close(); throw error }
    }
}

@MainActor
final class BackgroundOperationTests: XCTestCase {
    func testLaunchNeverReplaysUnfinishedWork() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let coordinator = BackgroundWorkCoordinator(directory: directory, register: false)
        let record = BackgroundOperationRecord(id: UUID().uuidString.lowercased(), capability: "files.receive",
            peerID: UUID().uuidString.lowercased(), label: "Sending file", protocolID: UUID().uuidString.lowercased(),
            requestDigest: String(repeating: "a", count: 64), startedAt: Date(), totalUnits: 100)
        try coordinator.begin(record) { XCTFail("Relaunch must not execute a stored callback") }
        try coordinator.progress(40, total: 100)
        XCTAssertThrowsError(try coordinator.progress(39, total: 100))
        XCTAssertThrowsError(try coordinator.progress(101, total: 100))
        XCTAssertFalse(coordinator.continuationGranted)
        let restarted = BackgroundWorkCoordinator(directory: directory, register: false)
        XCTAssertNil(restarted.active)
        XCTAssertEqual(restarted.records.first?.state, .interrupted)
        XCTAssertEqual(restarted.records.first?.verifiedUnits, 40)
        XCTAssertEqual(restarted.records.first?.retrySafety, "explicitFreshRequestOnly")
        XCTAssertEqual(restarted.records.first?.desktopMayContinueIndependently, false)
    }
    func testCancellationIsPersistedBeforeCleanupAndOnlyOnce() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let coordinator = BackgroundWorkCoordinator(directory: directory, register: false)
        var calls = 0
        try coordinator.begin(BackgroundOperationRecord(id: "operation", capability: "models.remote", peerID: "peer",
            label: "Receiving response", protocolID: "request", requestDigest: "digest", startedAt: Date())) {
                calls += 1
                XCTAssertNil(coordinator.active)
            }
        await coordinator.cancel(expired: true)
        await coordinator.cancel()
        XCTAssertEqual(calls, 1)
        XCTAssertEqual(coordinator.records.last?.state, .expired)
    }
    func testOldProgressCannotUpdateNewOperationAndV1MetadataMigrates() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let coordinator = BackgroundWorkCoordinator(directory: directory, register: false)
        let record = BackgroundOperationRecord(id: "new", capability: "files.receive", peerID: "peer",
            label: "Sending file", protocolID: "new", requestDigest: "digest", startedAt: Date(), totalUnits: 100)
        var legacy = try JSONSerialization.jsonObject(with: JSONEncoder().encode(record)) as! [String: Any]
        legacy.removeValue(forKey: "scope")
        legacy.removeValue(forKey: "failure")
        legacy.removeValue(forKey: "finishedAt")
        let migrated = try JSONDecoder().decode(BackgroundOperationRecord.self, from: JSONSerialization.data(withJSONObject: legacy))
        XCTAssertNil(migrated.scope)
        XCTAssertNil(migrated.failure)
        XCTAssertNil(migrated.finishedAt)
        XCTAssertEqual(migrated.retrySafety, "explicitFreshRequestOnly")
        try coordinator.begin(migrated) {}
        try coordinator.progress(90, total: 100, id: "old")
        coordinator.finish(.completed, id: "old")
        XCTAssertEqual(coordinator.active?.verifiedUnits, 0)
        try coordinator.progress(10, total: 100, id: "new")
        XCTAssertEqual(coordinator.active?.verifiedUnits, 10)
    }
    func testTypedFailureSurvivesRelaunchAndLateFinishCannotReplaceIt() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let coordinator = BackgroundWorkCoordinator(directory: directory, register: false)
        try coordinator.begin(BackgroundOperationRecord(id: "limited", capability: "models.remote", peerID: "peer",
            label: "Receiving response", protocolID: "limited", requestDigest: "digest", startedAt: Date())) {}
        try coordinator.progress(123, id: "limited")
        coordinator.finish(.interrupted, id: "limited", failure: .outputLimit)
        coordinator.finish(.completed, id: "limited")
        let restored = BackgroundWorkCoordinator(directory: directory, register: false)
        XCTAssertNil(restored.active)
        XCTAssertEqual(restored.records.last?.state, .interrupted)
        XCTAssertEqual(restored.records.last?.failure, .outputLimit)
        XCTAssertEqual(restored.records.last?.verifiedUnits, 123)
        XCTAssertNotNil(restored.records.last?.finishedAt)
    }
    func testUnknownStoreVersionIsPreserved() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = directory.appendingPathComponent("operations-v1.json")
        let bytes = Data("{\"version\":2,\"value\":[]}".utf8)
        try bytes.write(to: url)
        let coordinator = BackgroundWorkCoordinator(directory: directory, register: false)
        XCTAssertFalse(coordinator.canWrite)
        XCTAssertEqual(try Data(contentsOf: url), bytes)
    }
    func testCompletedTurnIdempotenceAndConflict() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = MobileChatStore(directory: directory)
        let turn = MobileChatTurn(id: "request", userID: "u", assistantID: "a", peerID: "p", preset: "normal",
            user: "2+2", answer: "4", createdAt: Date())
        try store.append(turn); try store.append(turn)
        XCTAssertEqual(MobileChatStore(directory: directory).turns.count, 1)
        XCTAssertThrowsError(try store.append(MobileChatTurn(id: "request", userID: "u", assistantID: "a",
            peerID: "p", preset: "normal", user: "2+2", answer: "5", createdAt: Date())))
    }
}

@MainActor
final class CompanionProtocolTests: XCTestCase {
    func testSignedSyncConflictStaleTombstoneAndChangedRevision() throws {
        let identity = try ConnectIdentity.generate(), other = try ConnectIdentity.generate()
        let record = try SyncWire.author(kind: "task", payload: SyncPayload.task(title: "Owned fixture"), identity: identity)
        var snapshot = SyncSnapshot()
        XCTAssertEqual(try MobileSyncStore.apply(record, peer: identity.publicIdentity.deviceID, in: &snapshot), "applied")
        XCTAssertEqual(try MobileSyncStore.apply(record, peer: identity.publicIdentity.deviceID, in: &snapshot), "duplicate")
        let left = try SyncWire.author(kind: "task", id: record.id, payload: SyncPayload.task(title: "Left"), parents: [record], identity: identity)
        let right = try SyncWire.author(kind: "task", id: record.id, payload: SyncPayload.task(title: "Right"), parents: [record], identity: other)
        XCTAssertEqual(try MobileSyncStore.apply(left, peer: identity.publicIdentity.deviceID, in: &snapshot), "applied")
        XCTAssertEqual(try MobileSyncStore.apply(right, peer: other.publicIdentity.deviceID, in: &snapshot), "conflict")
        XCTAssertEqual(snapshot.conflicts.count, 1)
        XCTAssertEqual(snapshot.records[record.id]?.revision, left.revision)
        let tombstone = try SyncWire.author(kind: "task", id: record.id, payload: .object([:]), deleted: true, parents: [left, right], identity: identity)
        XCTAssertEqual(try MobileSyncStore.apply(tombstone, peer: identity.publicIdentity.deviceID, in: &snapshot), "applied")
        XCTAssertTrue(snapshot.conflicts.isEmpty)
        XCTAssertEqual(try MobileSyncStore.apply(record, peer: identity.publicIdentity.deviceID, in: &snapshot), "stale")
        let resurrected = try SyncWire.author(kind: "task", id: record.id, payload: record.payload, parents: [tombstone], identity: identity)
        XCTAssertEqual(try MobileSyncStore.apply(resurrected, peer: identity.publicIdentity.deviceID, in: &snapshot), "conflict")
        var changed = left.wire.object!; changed["payload"] = SyncPayload.task(title: "Tamper")
        XCTAssertThrowsError(try SignedSyncRecord(.object(changed)))
        XCTAssertTrue(snapshot.records[record.id]!.deleted)
    }
    func testUnresolvedConflictSurvivesDuplicateExchangeAndRelaunchUntilResolution() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let phone = try ConnectIdentity.generate(), desktop = try ConnectIdentity.generate()
        let peer = desktop.publicIdentity.deviceID
        let base = try SyncWire.author(kind: "task", payload: SyncPayload.task(title: "Shared"), identity: phone)
        let local = try SyncWire.author(kind: "task", id: base.id, payload: SyncPayload.task(title: "Phone edit"), parents: [base], identity: phone)
        let remote = try SyncWire.author(kind: "task", id: base.id, payload: SyncPayload.task(title: "Desktop edit"), parents: [base], identity: desktop)
        var value = SyncSnapshot()
        try MobileSyncStore.put(local, in: &value)
        XCTAssertEqual(try MobileSyncStore.apply(remote, peer: peer, in: &value), "conflict")
        // A receipt and repeated version do not resolve the competing edits.
        value.acknowledged[peer + ":tasks"] = [local.revision]
        XCTAssertEqual(try MobileSyncStore.apply(local, peer: peer, in: &value), "duplicate")
        let store = MobileSyncStore(directory: directory); try store.commit(value)
        let restored = MobileSyncStore(directory: directory)
        XCTAssertTrue(MobileSyncStore.hasConflict(domain: "tasks", peer: peer, in: restored.snapshot))
        XCTAssertFalse(MobileSyncStore.hasConflict(domain: "calendar", peer: peer, in: restored.snapshot))
        XCTAssertFalse(MobileSyncStore.hasConflict(domain: "tasks", peer: phone.publicIdentity.deviceID, in: restored.snapshot))
        XCTAssertEqual(restored.snapshot.records[base.id]?.payload["title"], .string("Phone edit"))
        XCTAssertEqual(restored.snapshot.conflicts.first?.incoming.payload["title"], .string("Desktop edit"))
        value = restored.snapshot
        let resolved = try SyncWire.author(kind: "task", id: base.id, payload: remote.payload, parents: [local, remote], identity: desktop)
        XCTAssertEqual(try MobileSyncStore.apply(resolved, peer: peer, in: &value), "applied")
        XCTAssertFalse(MobileSyncStore.hasConflict(domain: "tasks", peer: peer, in: value))
    }
    func testChatSelectionImmutableOrderAndDeletedPredecessor() throws {
        let identity = try ConnectIdentity.generate(), peer = identity.publicIdentity.deviceID
        let conversation = try SyncWire.author(kind: "conversation", payload: .object([
            "title": .string("Selected fixture"), "project_id": .null, "created_at": .string(SyncWire.now())]), identity: identity)
        var value = SyncSnapshot()
        XCTAssertEqual(try MobileSyncStore.apply(conversation, peer: peer, in: &value), "applied")
        func message(after: String?) throws -> SignedSyncRecord {
            try SyncWire.author(kind: "message", payload: .object(["conversation_id": .string(conversation.id),
                "after": after.map(ConnectJSON.string) ?? .null, "role": .string("user"),
                "content": .string("Owned fixture"), "created_at": .string(SyncWire.now())]), identity: identity)
        }
        let first = try message(after: nil), second = try message(after: first.id)
        XCTAssertEqual(try MobileSyncStore.apply(first, peer: peer, in: &value), "applied")
        XCTAssertEqual(try MobileSyncStore.apply(second, peer: peer, in: &value), "applied")
        var reordered = second.payload.object!; reordered["after"] = .null
        let changed = try SyncWire.author(kind: "message", id: second.id, payload: .object(reordered), parents: [second], identity: identity)
        XCTAssertEqual(try MobileSyncStore.apply(changed, peer: peer, in: &value), "conflict")
        let deleted = try SyncWire.author(kind: "message", id: first.id, payload: .object([:]), deleted: true, parents: [first], identity: identity)
        XCTAssertEqual(try MobileSyncStore.apply(deleted, peer: peer, in: &value), "applied")
        XCTAssertEqual(value.messagePredecessors?[second.id], first.id)
        XCTAssertTrue(MobileSyncStore.dependency(second, in: value))
        value.selection[peer + ":" + conversation.id] = false
        XCTAssertEqual(try MobileSyncStore.apply(message(after: second.id), peer: peer, in: &value), "conflict")
    }
    func testSyncStoreAtomicReopenAndMissingDependency() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let identity = try ConnectIdentity.generate()
        let reminder = try SyncWire.author(kind: "reminder", payload: .object(["target_kind": .string("task"), "target_id": .string(UUID().uuidString.lowercased()), "at": .string(""), "offset_minutes": .int(30), "timezone": .string("UTC")]), identity: identity)
        let store = MobileSyncStore(directory: directory); var value = store.snapshot
        XCTAssertEqual(try MobileSyncStore.apply(reminder, peer: identity.publicIdentity.deviceID, in: &value), "conflict")
        XCTAssertNil(value.records[reminder.id])
        try store.commit(value)
        let restarted = MobileSyncStore(directory: directory)
        XCTAssertEqual(restarted.snapshot.conflicts.count, 1)
        XCTAssertNotNil(restarted.snapshot.receipts[reminder.revision])
    }
    func testTodayDraftRetainsOriginalRevisionAcrossLaunchWithoutApplying() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let identity = try ConnectIdentity.generate()
        let original = try SyncWire.author(kind: "task", payload: SyncPayload.task(title: "Original"), identity: identity)
        let changed = SyncPayload.task(title: "Offline draft")
        let store = MobileSyncStore(directory: directory)
        try store.drafts.save(original.id, original: original, fields: changed.object)
        let restarted = MobileSyncStore(directory: directory)
        XCTAssertTrue(restarted.snapshot.records.isEmpty)
        let draft = try XCTUnwrap(restarted.drafts.get(original.id))
        XCTAssertEqual(draft.original?.revision, original.revision)
        XCTAssertEqual(try ConnectJSON.decode(draft.fields), changed)
        try restarted.drafts.save(original.id, original: nil, fields: nil)
        XCTAssertNil(try TodayDraftStore(directory: directory).get(original.id))
    }
    func testC6BoundsRawBytesAndOwnedStaging() throws {
        let source = UUID().uuidString.lowercased(), target = UUID().uuidString.lowercased(), id = UUID().uuidString.lowercased()
        let meta = try FileMetadata(name: "fixture.bin", size: 3, sha256: String(repeating: "a", count: 64), mime: "application/octet-stream")
        let req = FileWire.request(source: source, target: target, transfer: id, operation: "chunk", arguments: .object(["offset": .int(0)]))
        let bytes = Data([0, 255, 1]), decoded = try FileWire.decode(FileWire.packet(req, bytes: bytes))
        XCTAssertEqual(decoded.1, bytes)
        XCTAssertThrowsError(try FileMetadata(name: "../secret", size: 1, sha256: meta.sha256, mime: meta.mime))
        XCTAssertThrowsError(try FileMetadata(name: "CON.txt", size: 1, sha256: meta.sha256, mime: meta.mime))
        XCTAssertThrowsError(try FileMetadata(name: "large", size: FileWire.maximumFile + 1, sha256: meta.sha256, mime: meta.mime))
        XCTAssertThrowsError(try FileWire.packet(req, bytes: Data(repeating: 0, count: 65537)))
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let staging = FileStaging(directory: directory); try staging.prepare()
        XCTAssertThrowsError(try staging.path("../../outside", "out"))
        let file = directory.appendingPathComponent("owned.bin"); try bytes.write(to: file)
        let copied = try staging.copySelection(file, id: id)
        XCTAssertEqual(copied.size, 3)
        XCTAssertEqual(try staging.digest(staging.path(id, "out")).1, copied.sha256)
        XCTAssertEqual(try Data(contentsOf: file), bytes)
    }
    func testC6FinalizationRehashesStoredBytesAndRefusesCollision() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let staging = FileStaging(directory: directory); try staging.prepare()
        let id = UUID().uuidString.lowercased(), bytes = Data("owned fixture".utf8)
        let partial = try staging.path(id, "part"), final = try staging.path(id, "bin")
        try bytes.write(to: partial)
        let metadata = try FileMetadata(name: "fixture.bin", size: Int64(bytes.count), sha256: Data(SHA256.hash(data: bytes)).hex, mime: "application/octet-stream")
        try Data("changed bytes".utf8).write(to: partial)
        XCTAssertThrowsError(try staging.finalize(id, metadata: metadata)) { XCTAssertEqual($0 as? ConnectFailure, .fileHashMismatch) }
        XCTAssertFalse(FileManager.default.fileExists(atPath: final.path))
        try bytes.write(to: partial)
        try Data("keep existing".utf8).write(to: final)
        XCTAssertThrowsError(try staging.finalize(id, metadata: metadata))
        XCTAssertEqual(try Data(contentsOf: final), Data("keep existing".utf8))
        try FileManager.default.removeItem(at: final)
        try staging.finalize(id, metadata: metadata)
        XCTAssertEqual(try Data(contentsOf: final), bytes)
    }
    @MainActor func testC6RelaunchInterruptsPartialTransferWithoutReplayOrDeletingVerifiedFiles() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let staging = FileStaging(directory: directory); try staging.prepare()
        let peer = UUID().uuidString.lowercased(), bytes = Data("owned fixture".utf8)
        let metadata = try FileMetadata(name: "fixture.bin", size: Int64(bytes.count), sha256: Data(SHA256.hash(data: bytes)).hex, mime: "application/octet-stream")
        var partial = MobileFileReceipt(id: UUID().uuidString.lowercased(), peerID: peer, incoming: true, metadata: metadata, created: Date(), touched: Date())
        partial.state = "transferring"; partial.received = 3
        var verified = MobileFileReceipt(id: UUID().uuidString.lowercased(), peerID: peer, incoming: true, metadata: metadata, created: Date(), touched: Date())
        verified.state = "completed"; verified.received = metadata.size
        try Data(bytes.prefix(3)).write(to: staging.path(partial.id, "part"))
        try bytes.write(to: staging.path(verified.id, "bin"))
        let unrelated = directory.appendingPathComponent("keep.txt"); try bytes.write(to: unrelated)
        let store = ProtectedStore<[MobileFileReceipt]>(url: directory.appendingPathComponent("receipts-v1.json"), maximumBytes: 8_000_000)
        try store.save([partial, verified])
        let model = FilesModel(session: nil, background: nil, directory: directory)
        XCTAssertTrue(model.available)
        XCTAssertEqual(model.receipts.first(where: { $0.id == partial.id })?.state, "interrupted")
        XCTAssertFalse(FileManager.default.fileExists(atPath: try staging.path(partial.id, "part").path))
        await model.cancel(partial.id); await model.cancel(verified.id)
        XCTAssertEqual(try store.load()?.map(\.state), ["interrupted", "completed"])
        XCTAssertEqual(try Data(contentsOf: staging.path(verified.id, "bin")), bytes)
        XCTAssertEqual(try Data(contentsOf: unrelated), bytes)
    }
    func testStudioReadHashAndStaleSaveResponse() throws {
        let source = UUID().uuidString.lowercased(), target = UUID().uuidString.lowercased(), workspace = UUID().uuidString.lowercased()
        let req = try StudioWire.request(source: source, target: target, operation: "read", workspace: workspace, revision: 1, arguments: .object(["path": .string("main.py")]))
        let response = ConnectJSON.object(["protocol_version": .string("olive-studio/1"), "request_id": req["request_id"], "error": .null,
            "result": .object(["path": .string("main.py"), "text": .string("changed"), "revision": .string(String(repeating: "a", count: 64))])])
        XCTAssertThrowsError(try StudioWire.response(response.canonical, request: req))
        XCTAssertThrowsError(try StudioWire.request(source: source, target: target, operation: "terminal", workspace: workspace, revision: 1))
        XCTAssertThrowsError(try StudioWire.path(.string("../secret")))
        XCTAssertEqual(StudioWire.failure("revision_conflict"), .studioRevisionStale)
        XCTAssertThrowsError(try ConnectJSON.decode(Data("1.5".utf8)))
        XCTAssertEqual(try ConnectJSON.decode(Data("1.5".utf8), allowDecimals: true), .decimal("1.5"))
        for value in ["1e999", "1.e2", "1.2.3", "NaN"] { XCTAssertThrowsError(try ConnectJSON.decode(Data(value.utf8), allowDecimals: true)) }
    }
    func testNotificationLabelsContainNoContent() {
        XCTAssertEqual(CompletionNotifications.message(for: "models.remote"), "Response ready")
        XCTAssertEqual(CompletionNotifications.message(for: "files.receive"), "File transfer complete")
        XCTAssertEqual(CompletionNotifications.message(for: "studio.test"), "Studio operation finished")
    }
}
