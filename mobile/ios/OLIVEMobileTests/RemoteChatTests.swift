import XCTest
import CryptoKit
import ImageIO
import UniformTypeIdentifiers
import UIKit
@testable import OLIVEMobile

@MainActor private final class RemoteChatShellStore: ShellStore {
    let directory: URL
    var text = ""
    init(_ directory: URL) { self.directory = directory }
    var companionDirectory: URL? { directory }
    func loadDestination() -> Destination { .chat }
    func saveDestination(_ value: Destination) {}
    func loadDraft() throws -> String { text }
    func saveDraft(_ value: String) throws { text = value }
}

/// Remote Chat v2 on the phone: wire strictness, negotiation, attachments, media and recovery.
@MainActor
final class RemoteChatTests: XCTestCase {
    private lazy var directory: URL = {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("RemoteChatTests-\(UUID().uuidString)")
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }()
    private let peer = "dddddddd-2222-4222-8222-222222222222"

    private func waitUntil(_ seconds: Double = 12, _ condition: () async -> Bool) async throws {
        let deadline = Date().addingTimeInterval(seconds)
        while Date() < deadline { if await condition() { return }; try await Task.sleep(for: .milliseconds(50)) }
        XCTFail("Timed out")
    }

    // MARK: Wire

    func testStartFingerprintMatchesDesktopVector() throws {
        let arguments = try ChatWire.startArguments(job: "11111111-1111-4111-8111-111111111111", conversation: "22222222-2222-4222-8222-222222222222",
            mode: "deep", voice: nil, messages: [("user", "Earlier question"), ("assistant", "Earlier answer — café"), ("user", "What does \"the report\" say?\n\tLine two")],
            attachments: [ChatAttachmentDescriptor(id: String(repeating: "a", count: 64), kind: "document", mime: "application/pdf", size: 1234, name: "Report 3.pdf")])
        // Computed by olive.connect.chat_protocol.start_fingerprint for the same arguments.
        XCTAssertEqual(arguments["input_fingerprint"], .string("e7e77df93301e818836b62d66b2f55f6376c8f80555a42950727f612795607dc"))
        XCTAssertThrowsError(try ChatWire.startArguments(job: UUID().uuidString.lowercased(), conversation: UUID().uuidString.lowercased(),
            mode: "terminal", voice: nil, messages: [("user", "x")], attachments: []))
        XCTAssertThrowsError(try ChatWire.startArguments(job: UUID().uuidString.lowercased(), conversation: UUID().uuidString.lowercased(),
            mode: "fast", voice: nil, messages: [("user", "   ")], attachments: []))
    }

    func testPacketsAndResponsesAreStrict() throws {
        let source = UUID().uuidString.lowercased(), target = UUID().uuidString.lowercased()
        let request = try ChatWire.request(source: source, target: target, operation: "poll", arguments: .object(["job_id": .string(source), "after": .int(0)]))
        func packet(_ value: ConnectJSON, binary: Data = Data()) throws -> Data { try ChatWire.packet(value, binary: binary) }
        let good: ConnectJSON = .object(["protocol_version": .string(ChatWire.name), "request_id": request["request_id"], "result": .object([:]), "error": .null])
        XCTAssertNoThrow(try ChatWire.response(try packet(good), request: request))
        // Another request's id, a binary tail on a non-artifact reply, an extra key or a malformed code are refused.
        XCTAssertThrowsError(try ChatWire.response(try packet(.object(["protocol_version": .string(ChatWire.name), "request_id": .string(target),
            "result": .object([:]), "error": .null])), request: request))
        XCTAssertThrowsError(try ChatWire.response(try packet(good, binary: Data([1])), request: request))
        XCTAssertThrowsError(try ChatWire.response(try packet(.object(["protocol_version": .string(ChatWire.name), "request_id": request["request_id"],
            "result": .null, "error": .string("DROP TABLE")])), request: request))
        XCTAssertThrowsError(try ChatWire.unpack(Data([0, 0, 0, 9]) + Data("{}".utf8)))
        XCTAssertThrowsError(try ChatWire.packet(.string(String(repeating: "x", count: ChatWire.maximumJSON))))
        XCTAssertThrowsError(try ChatWire.request(source: source, target: target, operation: "run_terminal", arguments: .object([:])))
        XCTAssertEqual(try ConnectFrame.limit(17), ChatWire.maximumFrame)
        XCTAssertThrowsError(try ConnectFrame.limit(19), "19 remains unknown")
    }

    func testCapabilitiesParseAllNineModesAndIgnoreFutureOnes() throws {
        var value = FixtureChatDesktop.capabilities(unavailable: ["video"])
        if case .object(var root) = value, case .array(var modes) = root["modes"]! {
            if case .object(var future) = modes[0] { future["id"] = .string("hologram"); modes.append(.object(future)) }
            root["modes"] = .array(modes); value = .object(root)
        }
        let parsed = try ChatWire.capabilities(value)
        XCTAssertEqual(parsed.modes.map(\.id), ChatWire.modes)
        XCTAssertFalse(parsed.mode("video")!.available)
        XCTAssertEqual(parsed.mode("reimagine")!.imageMax, 1)
        XCTAssertEqual(parsed.mode("audio")!.voices.map(\.id), ["default", "calm"])
        XCTAssertEqual(parsed.mode("video")!.limitations, ["text_only", "video_with_audio"])
    }

    func testSourceLinksAndArtifactDescriptorsAreValidated() throws {
        func source(_ url: String?) throws -> ChatSource {
            try ChatSource(.object(["id": .string("S1"), "kind": .string("web"), "title": .string("T"), "provider": .null,
                "url": url.map(ConnectJSON.string) ?? .null, "published_at": .null, "updated_at": .null, "retrieved_at": .null,
                "page": .null, "snapshot": .bool(false), "excerpt": .null]))
        }
        XCTAssertEqual(try source("https://example.org/a").url?.host, "example.org")
        XCTAssertNil(try source("javascript:alert(1)").url)
        XCTAssertNil(try source("file:///etc/passwd").url)
        XCTAssertNil(try source("https://user:pw@example.org").url)
        XCTAssertNil(try source(nil).url, "no link is invented")
        func artifact(_ changes: [String: ConnectJSON]) throws -> ChatArtifact {
            var base: [String: ConnectJSON] = ["artifact_id": .string(String(repeating: "a", count: 32)), "kind": .string("image"), "mime": .string("image/png"),
                "size": .int(10), "sha256": .string(String(repeating: "b", count: 64)), "width": .int(64), "height": .int(64), "duration_ms": .null,
                "has_audio": .null, "completion_state": .string("complete"), "mode": .string("reimagine"), "label": .string("")]
            base.merge(changes) { $1 }
            return try ChatArtifact(.object(base))
        }
        XCTAssertNoThrow(try artifact([:]))
        XCTAssertThrowsError(try artifact(["mime": .string("image/jpeg")]), "descriptor says PNG kind but another type")
        XCTAssertThrowsError(try artifact(["width": .int(1_000_000)]), "absurd dimensions")
        XCTAssertThrowsError(try artifact(["kind": .string("video"), "mime": .string("video/mp4"), "size": .int(Int64(1) << 40)]), "absurd size")
        XCTAssertThrowsError(try artifact(["completion_state": .string("partial")]))
        XCTAssertThrowsError(try artifact(["artifact_id": .string("../../x")]))
    }

    // MARK: Old desktop and message migration

    func testOldChatHistoryStillLoadsAndUnknownArtifactsArePlaceholders() throws {
        let old = """
        {"version":1,"value":[{"id":"job","userID":"\(UUID().uuidString)","assistantID":"\(UUID().uuidString)","peerID":"p","preset":"max",
        "user":"Question","answer":"Answer","createdAt":780000000}]}
        """
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try Data(old.utf8).write(to: directory.appendingPathComponent("chat-v1.json"))
        let store = MobileChatStore(directory: directory)
        XCTAssertTrue(store.available)
        XCTAssertEqual(store.turns.first?.preset, "max")
        XCTAssertNil(store.turns.first?.artifacts)
        let future = ChatArtifact(artifactID: String(repeating: "c", count: 32), kind: "hologram", mime: "model/x", size: 1,
                                  sha256: String(repeating: "d", count: 64), mode: "video")
        let decoded = try JSONDecoder().decode(ChatArtifact.self, from: try JSONEncoder().encode(future))
        XCTAssertFalse(decoded.known, "an unknown future kind decodes and renders as a placeholder")
    }

    func testOlderComputerKeepsLegacyModesAndExplainsTheRest() {
        let session = FixtureChatSession(offline: false, legacy: true)
        let state = AppState(store: RemoteChatShellStore(directory), chatConnection: session)
        XCTAssertEqual(state.availability(.named("reimagine")), .unsupportedComputer)
        XCTAssertEqual(state.availability(.named("reimagine")).explanation, "This computer's OLIVE doesn't support this mode yet.")
        // The fixture's legacy computer has no v1 transport, so text modes read as offline here.
        XCTAssertNotEqual(state.availability(.named("fast")), .unsupportedComputer)
        let offline = AppState(store: RemoteChatShellStore(directory), chatConnection: FixtureChatSession(offline: true, legacy: false))
        offline.draft = "Hello"
        XCTAssertFalse(offline.canSend)
        XCTAssertEqual(offline.sendBlocker, "Computer offline")
    }

    // MARK: Attachments

    private func jpegWithOrientationAndGPS() -> Data {
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        let image = UIGraphicsImageRenderer(size: CGSize(width: 200, height: 100), format: format).image { context in
            UIColor.red.setFill(); context.fill(CGRect(x: 0, y: 0, width: 100, height: 100))
            UIColor.blue.setFill(); context.fill(CGRect(x: 100, y: 0, width: 100, height: 100))
        }
        let output = NSMutableData()
        let destination = CGImageDestinationCreateWithData(output, UTType.jpeg.identifier as CFString, 1, nil)!
        CGImageDestinationAddImage(destination, image.cgImage!, [kCGImagePropertyOrientation: 6,
            kCGImagePropertyGPSDictionary: [kCGImagePropertyGPSLatitude: 33.9, kCGImagePropertyGPSLatitudeRef: "S"]] as CFDictionary)
        CGImageDestinationFinalize(destination)
        return output as Data
    }

    func testPhotoNormalisationAppliesOrientationAndStripsMetadata() throws {
        let prepared = try AttachmentPreparation.photo(jpegWithOrientationAndGPS(), source: "photo", name: "x.jpg", directory: directory)
        let data = try Data(contentsOf: prepared.file)
        let properties = CGImageSourceCopyPropertiesAtIndex(CGImageSourceCreateWithData(data as CFData, nil)!, 0, nil) as! [CFString: Any]
        XCTAssertNil(properties[kCGImagePropertyGPSDictionary], "no location leaves the phone")
        XCTAssertEqual((properties[kCGImagePropertyOrientation] as? Int) ?? 1, 1)
        XCTAssertEqual(prepared.pixelWidth, 100); XCTAssertEqual(prepared.pixelHeight, 200, "rotation is in the pixels, not EXIF")
        XCTAssertEqual(prepared.descriptor.id, Data(SHA256.hash(data: data)).hex)
        XCTAssertEqual(prepared.descriptor.mime, "image/jpeg")
    }

    func testHEICIsConvertedAndLargeImagesKeepAspectWithinLimits() throws {
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        let big = UIGraphicsImageRenderer(size: CGSize(width: 6000, height: 3000), format: format).image { context in
            UIColor.green.setFill(); context.fill(CGRect(x: 0, y: 0, width: 6000, height: 3000))
        }
        let output = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(output, UTType.heic.identifier as CFString, 1, nil) else {
            throw XCTSkip("HEIC encoding unavailable on this device")
        }
        CGImageDestinationAddImage(destination, big.cgImage!, nil)
        XCTAssertTrue(CGImageDestinationFinalize(destination))
        let prepared = try AttachmentPreparation.photo(output as Data, source: "photo", name: "IMG_0001.HEIC", directory: directory)
        XCTAssertEqual(prepared.descriptor.mime, "image/jpeg")
        XCTAssertEqual(prepared.pixelWidth, 4096); XCTAssertEqual(prepared.pixelHeight, 2048)
    }

    func testFileValidationUsesContentNotExtension() throws {
        let limit: (String, String) -> Int64? = { kind, mime in kind == "document" && mime != "text/plain" || kind == "document" ? 1_000_000 : 20_000_000 }
        func file(_ name: String, _ data: Data) throws -> URL {
            let url = directory.appendingPathComponent("src-\(UUID().uuidString)").appendingPathComponent(name)
            try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try data.write(to: url); return url
        }
        XCTAssertThrowsError(try AttachmentPreparation.file(try file("fake.pdf", Data("not a pdf".utf8)), limit: limit, directory: directory)) {
            XCTAssertEqual($0 as? ChatAttachmentFailure, .unsupported)
        }
        XCTAssertThrowsError(try AttachmentPreparation.file(try file("fake.png", Data("not a png".utf8)), limit: limit, directory: directory))
        XCTAssertThrowsError(try AttachmentPreparation.file(try file("nul.txt", Data([65, 0, 66])), limit: limit, directory: directory))
        XCTAssertThrowsError(try AttachmentPreparation.file(try file("big.pdf", Data("%PDF-".utf8) + Data(count: 1_100_000)), limit: limit, directory: directory)) {
            XCTAssertEqual($0 as? ChatAttachmentFailure, .tooLarge, "refused before any transfer")
        }
        let markdown = try AttachmentPreparation.file(try file("notes.md", Data("# Title\nçafé".utf8)), limit: limit, directory: directory)
        XCTAssertEqual(markdown.descriptor.mime, "text/markdown")
        let pdf = try AttachmentPreparation.file(try file("doc.pdf", ChatUIFixture.syntheticPDF()), limit: limit, directory: directory)
        XCTAssertEqual(pdf.descriptor.mime, "application/pdf"); XCTAssertEqual(pdf.pageCount, 1)
        let code = try AttachmentPreparation.file(try file("tool.py", Data("print('x')\n".utf8)), limit: limit, directory: directory)
        XCTAssertEqual(code.descriptor.mime, "text/x-source")
    }

    func testDisplayNamesNeverCarryPathsOrControls() {
        XCTAssertEqual(AttachmentPreparation.displayName("../../etc/passwd", fallback: "F"), "..-..-etc-passwd")
        XCTAssertEqual(AttachmentPreparation.displayName("a\u{0}b\tc", fallback: "F"), "a-b-c")
        XCTAssertEqual(AttachmentPreparation.displayName("..", fallback: "F"), "F")
        XCTAssertLessThanOrEqual(AttachmentPreparation.displayName(String(repeating: "é", count: 200), fallback: "F").utf8.count, 180)
    }

    func testUTF8ValidatorAcrossChunkBoundaries() {
        var validator = UTF8Validator()
        let bytes = Array("aé😀".utf8)
        XCTAssertTrue(validator.feed(Data(bytes[0..<2]))); XCTAssertTrue(validator.feed(Data(bytes[2..<5]))); XCTAssertTrue(validator.feed(Data(bytes[5...])))
        XCTAssertTrue(validator.finish())
        var bad = UTF8Validator()
        XCTAssertFalse(bad.feed(Data([0xC3, 0x28])))
    }

    func testNoteSnapshotIsFrozenAndStoreDeduplicates() throws {
        let store = ChatAttachmentStore(directory: directory.appendingPathComponent("Attachments"))
        let first = try store.commit(try AttachmentPreparation.note(id: "note-1", title: "OLIVE Mobile Attachment Test", text: "Version one",
                                                                    editedAt: "2026-09-30T10:00:00Z", directory: store.directory))
        let again = try store.commit(try AttachmentPreparation.note(id: "note-1", title: "OLIVE Mobile Attachment Test", text: "Version one",
                                                                    editedAt: "2026-09-30T10:00:00Z", directory: store.directory))
        XCTAssertEqual(first.id, again.id); XCTAssertEqual(store.items.count, 1)
        let edited = try store.commit(try AttachmentPreparation.note(id: "note-1", title: "OLIVE Mobile Attachment Test", text: "Version two",
                                                                     editedAt: "2026-09-30T11:00:00Z", directory: store.directory))
        XCTAssertNotEqual(first.id, edited.id)
        XCTAssertEqual(try String(contentsOf: store.url(first.descriptor), encoding: .utf8), "Version one", "a sent snapshot never changes")
        XCTAssertEqual(first.provenance.sourceID, "note-1"); XCTAssertEqual(first.descriptor.kind, "note")
        XCTAssertThrowsError(try AttachmentPreparation.note(id: "n", title: "t", text: String(repeating: "x", count: 200_000), editedAt: "", directory: directory))
        // Unreferenced and older than a day: collectable; referenced: kept.
        XCTAssertEqual(store.collect(referenced: [first.id], now: Date().addingTimeInterval(2 * 86_400)), 1)
        XCTAssertNotNil(store.item(first.id)); XCTAssertNil(store.item(edited.id))
        let values = try store.directory.resourceValues(forKeys: [.isExcludedFromBackupKey])
        XCTAssertEqual(values.isExcludedFromBackup, true)
    }

    func testDrawingSnapshotIsAPNGAtDocumentResolution() throws {
        let prepared = try AttachmentPreparation.drawing(id: "d", title: "Synthetic drawing", revision: 3, ops: [], width: 800, height: 600,
                                                         background: "#ff0000", images: [:], directory: directory)
        let data = try Data(contentsOf: prepared.file)
        XCTAssertTrue(data.starts(with: [0x89, 0x50, 0x4E, 0x47]))
        XCTAssertEqual(prepared.pixelWidth, 800); XCTAssertEqual(prepared.pixelHeight, 600)
        XCTAssertEqual(prepared.provenance.source, "draw"); XCTAssertEqual(prepared.provenance.revision, "revision 3")
        XCTAssertEqual(prepared.descriptor.name, "Synthetic drawing.png")
    }

    // MARK: Media

    private func artifact(_ data: Data, kind: String = "audio", sha: String? = nil) -> ChatArtifact {
        ChatArtifact(artifactID: UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased(), kind: kind,
                     mime: ChatArtifact.mimes[kind]!, size: Int64(data.count), sha256: sha ?? Data(SHA256.hash(data: data)).hex, mode: "audio")
    }

    func testMediaDownloadVerifiesHashTypeAndResumes() async throws {
        let store = ChatMediaStore(directory: directory.appendingPathComponent("Media"))
        let wav = ChatUIFixture.wav(seconds: 0.5)
        let good = artifact(wav)
        let fetched = FetchLog()
        let url = try await store.download(good, fetch: { offset in await fetched.add(offset); return wav.subdata(in: Int(offset)..<min(wav.count, Int(offset) + 4096)) },
                                           progress: { _ in })
        XCTAssertEqual(try Data(contentsOf: url), wav)
        let protection = try FileManager.default.attributesOfItem(atPath: url.path)[.protectionKey] as? FileProtectionType
        XCTAssertEqual(protection, .completeUntilFirstUserAuthentication)
        // Resume: half the bytes already on disk are not transferred again.
        let second = artifact(wav + Data([1]))
        try FileManager.default.createDirectory(at: store.directory, withIntermediateDirectories: true)
        try (wav + Data([1])).prefix(8000).write(to: store.partURL(second))
        let resumed = FetchLog()
        _ = try await store.download(second, fetch: { offset in await resumed.add(offset); let all = wav + Data([1]); return all.subdata(in: Int(offset)..<min(all.count, Int(offset) + 4096)) },
                                     progress: { _ in })
        let first = await resumed.offsets.first
        XCTAssertEqual(first, 8000)
        // Wrong hash: discarded, never presented.
        let wrong = artifact(wav, sha: String(repeating: "0", count: 64))
        do { _ = try await store.download(wrong, fetch: { offset in wav.subdata(in: Int(offset)..<min(wav.count, Int(offset) + 65536)) }, progress: { _ in }); XCTFail() }
        catch { XCTAssertEqual(error as? ChatMediaFailure, .integrity) }
        XCTAssertNil(store.available(wrong)); XCTAssertEqual(store.received(wrong), 0)
        // Declared PNG, actually JPEG bytes (hash matches, content does not).
        let jpeg = jpegWithOrientationAndGPS()
        let liar = artifact(jpeg, kind: "image")
        do { _ = try await store.download(liar, fetch: { offset in jpeg.subdata(in: Int(offset)..<min(jpeg.count, Int(offset) + 65536)) }, progress: { _ in }); XCTFail() }
        catch { XCTAssertEqual(error as? ChatMediaFailure, .integrity) }
        // Truncated WAV header and an invalid video container are refused too.
        XCTAssertFalse(ChatMediaStore.sniff(Data("RIFF".utf8), url: url, kind: "audio"))
        XCTAssertFalse(ChatMediaStore.sniff(Data("not a video!".utf8), url: url, kind: "video"))
        let removed = await store.clear(keeping: [good.artifactID])
        XCTAssertGreaterThanOrEqual(removed, 1); XCTAssertNotNil(store.available(good))
    }

    // MARK: Client against the in-process fixture computer

    func testUploadResumesDeduplicatesAndStartIsIdempotent() async throws {
        let desktop = FixtureChatDesktop()
        let client = RemoteChatClient(transport: desktop, source: "cccccccc-2222-4222-8222-222222222222", target: peer)
        let data = Data((0..<300_000).map { UInt8($0 % 251) })
        let file = directory.appendingPathComponent("blob.txt")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true); try data.write(to: file)
        let descriptor = ChatAttachmentDescriptor(id: Data(SHA256.hash(data: data)).hex, kind: "document", mime: "text/plain", size: Int64(data.count), name: "blob.txt")
        let log = FetchLog()
        try await client.upload(descriptor, file: file) { await log.add($0) }
        let chunks = await log.offsets
        XCTAssertEqual(chunks.last, Int64(data.count)); XCTAssertEqual(chunks.count, 4, "offer + three bounded chunks")
        let again = FetchLog()
        try await client.upload(descriptor, file: file) { await again.add($0) }
        let repeatCount = await again.offsets.count
        XCTAssertEqual(repeatCount, 1, "identical content is not resent")
        let job = UUID().uuidString.lowercased()
        let arguments = try ChatWire.startArguments(job: job, conversation: UUID().uuidString.lowercased(), mode: "deep", voice: nil,
                                                    messages: [("user", "What is the phrase?")], attachments: [descriptor])
        _ = try await client.start(arguments); _ = try await client.start(arguments)
        let starts = await desktop.starts
        XCTAssertEqual(starts, 1, "a resend after a lost acknowledgement never runs twice")
        let unknown = try await client.poll(job: UUID().uuidString.lowercased(), after: 0)
        XCTAssertEqual(unknown.state, "not_received")
    }

    // MARK: AppState end to end (fixture computer)

    private func state(_ session: FixtureChatSession? = nil) -> AppState {
        AppState(store: RemoteChatShellStore(directory), chatConnection: session ?? FixtureChatSession(offline: false, legacy: false))
    }

    func testFastCompletesPersistsAndAttributes() async throws {
        let app = state()
        app.preset = "fast"; app.draft = "Reply with exactly: fast-mobile-ready"
        XCTAssertTrue(app.canSend)
        app.send(); app.send()
        try await waitUntil { !app.active }
        XCTAssertEqual(app.chatStatus, "Completed")
        XCTAssertEqual(app.messages.filter { $0.role == .user }.count, 1, "no duplicate message")
        XCTAssertEqual(app.messages.last?.plainText, "fast-mobile-ready")
        XCTAssertEqual(app.messages.last?.modeLabel, "FAST · This computer")
        XCTAssertEqual(app.chatStore?.turns.last?.preset, "fast")
        XCTAssertTrue(app.draft.isEmpty)
        XCTAssertNil(app.chatStore?.pending(), "no pending record after a conclusive outcome")
    }

    func testReimagineResultDownloadsVerifiedAndSurvivesRestart() async throws {
        let session = FixtureChatSession(offline: false, legacy: false)
        let app = state(session)
        app.preset = "reimagine"; app.draft = "Generate a simple image of a blue square on a white background."
        app.send()
        try await waitUntil { !app.active }
        let artifact = try XCTUnwrap(app.messages.last?.artifacts.first)
        try await waitUntil { app.mediaFiles[artifact.id] != nil }
        XCTAssertEqual(app.messages.last?.modeLabel, "REIMAGINE · IMAGE · This computer")
        // Relaunch: the history reopens the verified local file without generating again.
        let starts = await session.desktop.starts
        let reopened = state(session)
        reopened.restoreCompletedChat()
        XCTAssertEqual(reopened.messages.last?.artifacts.first?.id, artifact.id)
        XCTAssertNotNil(reopened.mediaFiles[artifact.id])
        let after = await session.desktop.starts
        XCTAssertEqual(after, starts)
        XCTAssertEqual(reopened.preset, "reimagine", "the mode is remembered for this conversation")
        reopened.clearChat()
        XCTAssertEqual(reopened.preset, "normal", "a new conversation starts in NORMAL")
    }

    func testModeSwitchRevalidatesAttachments() async throws {
        let app = state()
        app.preset = "deep"; app.draft = "What does it say?"
        let source = directory.appendingPathComponent("synthetic.pdf")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try ChatUIFixture.syntheticPDF().write(to: source)
        app.addAttachment { directory in try AttachmentPreparation.file(source, limit: { _, _ in 30_000_000 }, directory: directory) }
        try await waitUntil { app.preparing == 0 && !app.draftAttachments.isEmpty }
        XCTAssertNil(app.sendBlocker)
        app.preset = "video"
        XCTAssertEqual(app.sendBlocker, "VIDEO currently supports text prompts only. Remove the attachment or switch mode.")
        XCTAssertFalse(app.canSend)
        app.preset = "now"
        XCTAssertNotNil(app.sendBlocker)
        app.preset = "deep"
        XCTAssertTrue(app.canSend)
        app.send()
        try await waitUntil { !app.active }
        XCTAssertTrue(app.messages.last?.plainText.contains("amber-falcon-7") == true)
        XCTAssertEqual(app.messages.last?.sources.first?.id, "D1")
        XCTAssertTrue(app.draftAttachments.isEmpty)
        XCTAssertEqual(app.messages.first(where: { $0.role == .user })?.attachments.count, 1)
    }

    func testStopPreventsLateArtifact() async throws {
        let app = state()
        app.preset = "video"; app.draft = "A slow synthetic city"
        app.send()
        try await waitUntil { app.chatStatus != "Sending" && app.remoteJob != nil && app.pending?.accepted == true }
        app.stop()
        try await waitUntil { !app.active }
        try await Task.sleep(for: .seconds(2))
        XCTAssertEqual(app.chatStatus, "Stopped")
        XCTAssertTrue(app.messages.allSatisfy { $0.artifacts.isEmpty }, "no late artifact after Stop")
        XCTAssertEqual(app.messages.last?.status, "Generation stopped.")
    }

    func testAcceptedRequestRecoversAfterRelaunchWithoutResubmitting() async throws {
        let session = FixtureChatSession(offline: false, legacy: false)
        let app = state(session)
        app.preset = "normal"; app.draft = "Reply with exactly: recovered"
        app.send()
        try await waitUntil { app.pending?.accepted == true }
        app.pauseRemote()  // The app is suspended or killed while the computer keeps working.
        XCTAssertNotNil(app.chatStore?.pending())
        let relaunched = state(session)
        relaunched.restoreCompletedChat()
        try await waitUntil { relaunched.chatStore?.pending() == nil && !relaunched.active }
        XCTAssertEqual(relaunched.messages.last?.plainText, "recovered")
        let starts = await session.desktop.starts
        XCTAssertEqual(starts, 1, "status recovery, not regeneration")
    }
}

actor FetchLog {
    private(set) var offsets: [Int64] = []
    func add(_ value: Int64) { offsets.append(value) }
}
