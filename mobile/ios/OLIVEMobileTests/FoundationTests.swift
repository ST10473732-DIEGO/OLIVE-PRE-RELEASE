import XCTest
@testable import OLIVEMobile

@MainActor
final class FoundationTests: XCTestCase {
    private final class MemoryStore: ShellStore {
        var destination: Destination = .home
        var text = ""
        var fails = false
        var writes = 0
        func loadDestination() -> Destination { destination }
        func saveDestination(_ value: Destination) { destination = value }
        func loadDraft() throws -> String {
            if fails { throw CocoaError(.fileReadCorruptFile) }
            return text
        }
        func saveDraft(_ value: String) throws {
            if fails { throw CocoaError(.fileWriteNoPermission) }
            writes += 1
            text = value
        }
    }

    func testFreshStateIsDisconnectedAndEmpty() {
        let state = AppState(store: MemoryStore())
        XCTAssertEqual(state.destination, .home)
        XCTAssertEqual(state.connection, .notPaired)
        XCTAssertEqual(state.connection.title, "Not connected")
        XCTAssertTrue(state.messages.isEmpty)
        XCTAssertFalse(state.canSend)
    }
    func testNavigationPersistsAndRestores() {
        let store = MemoryStore()
        let state = AppState(store: store)
        state.destination = .devices
        XCTAssertEqual(AppState(store: store).destination, .devices)
        state.openChat()
        XCTAssertEqual(store.destination, .chat)
    }
    func testMultilineDraftPersistsWithoutCreatingMessages() {
        let store = MemoryStore()
        let state = AppState(store: store)
        state.draft = "First line\nSecond line 🫒"
        XCTAssertEqual(AppState(store: store).draft, state.draft)
        XCTAssertFalse(state.canSend)
        XCTAssertTrue(state.messages.isEmpty)
        state.draft = ""
        XCTAssertEqual(store.text, "")
    }
    func testUnreadableDraftIsNeverOverwritten() {
        let store = MemoryStore()
        store.text = "Preserve source"
        store.fails = true
        let state = AppState(store: store)
        store.fails = false
        state.draft = "Temporary edit"
        state.saveDraft()
        XCTAssertEqual(store.text, "Preserve source")
        XCTAssertEqual(store.writes, 0)
        XCTAssertNotNil(state.persistenceNotice)
    }
    func testFailedSaveKeepsDraftAndReportsRecovery() {
        let store = MemoryStore()
        let state = AppState(store: store)
        store.fails = true
        state.draft = "Keep this"
        XCTAssertEqual(state.draft, "Keep this")
        XCTAssertNotNil(state.persistenceNotice)
        store.fails = false
        state.saveDraft()
        XCTAssertNil(state.persistenceNotice)
        XCTAssertEqual(store.text, "Keep this")
    }
    func testProtectedFileRoundTripAndUnknownNavigationFallback() throws {
        let suite = "olive.tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(suite)
        defer {
            defaults.removePersistentDomain(forName: suite)
            try? FileManager.default.removeItem(at: dir)
        }
        defaults.set("future-tab", forKey: "shell.v1.destination")
        let store = LocalShellStore(defaults: defaults, directory: dir)
        XCTAssertEqual(store.loadDestination(), .home)
        XCTAssertEqual(try store.loadDraft(), "")
        try store.saveDraft("Line one\nLine two")
        XCTAssertEqual(try store.loadDraft(), "Line one\nLine two")
        let values = try dir.resourceValues(forKeys: [.isExcludedFromBackupKey])
        XCTAssertEqual(values.isExcludedFromBackup, true)
        let file = dir.appendingPathComponent("draft-v1.json")
        let attributes = try FileManager.default.attributesOfItem(atPath: file.path)
        XCTAssertEqual(attributes[.protectionKey] as? FileProtectionType, .complete)
        try Data(#"{"version":2,"text":"future"}"#.utf8).write(to: file)
        let state = AppState(store: store)
        state.draft = "Must not replace v2"
        XCTAssertEqual(try String(contentsOf: file, encoding: .utf8), #"{"version":2,"text":"future"}"#)
    }
    func testMessageBlocksRetainRoleAndLiteralCode() {
        let code = "print(\"<hello>\")\n"
        let assistant = ChatMessage(id: UUID(), role: .assistant,
                                    blocks: [.text("Example"), .code(language: "swift", content: code)])
        XCTAssertEqual(assistant.author, "OLIVE")
        XCTAssertEqual(assistant.blocks.last, .code(language: "swift", content: code))
        let user = ChatMessage(id: UUID(), role: .user, blocks: [.text("A question")])
        XCTAssertEqual(user.author, "You")
        XCTAssertNotEqual(user.id, assistant.id)
    }
    func testAboutUsesBuiltBundleMetadata() {
        let info = AboutInfo(info: ["CFBundleDisplayName": "OLIVE", "CFBundleShortVersionString": "0.1.0", "CFBundleVersion": "7"])
        XCTAssertEqual(info.name, "OLIVE")
        XCTAssertEqual(info.versionDescription, "0.1.0 (7)")
        XCTAssertEqual(AboutInfo(info: [:]).version, "Unknown")
        XCTAssertEqual(AboutInfo().name, "OLIVE")
        XCTAssertEqual(AboutInfo().version, "0.1.0")
    }
    func testTouchTargetsAndSpacing() {
        XCTAssertGreaterThanOrEqual(OliveTheme.minimumTouchTarget, 44)
        XCTAssertGreaterThan(OliveTheme.Space.section, OliveTheme.Space.medium)
        XCTAssertGreaterThan(OliveTheme.Radius.card, OliveTheme.Radius.control)
    }
    func testDisconnectedClientAndUnavailablePairing() async throws {
        let devices = try await DisconnectedConnectClient().pairedDevices()
        XCTAssertTrue(devices.isEmpty)
        do {
            try await UnavailablePairingService().begin(publicOffer: Data())
            XCTFail("Pairing must not report success")
        } catch {
            XCTAssertEqual(error as? ConnectError, .pairingNotImplemented)
        }
        await UnavailablePairingService().cancel()
    }
    func testKeychainRoundTripUpdateAndScopedDelete() async throws {
        // Only synthetic bytes under a unique test-only service; never real identity data.
        let store = KeychainSecretStore(service: "olive.tests.\(UUID().uuidString)")
        let missing = try await store.read(account: "test")
        XCTAssertNil(missing)
        do {
            try await store.write(Data([1, 2]), account: "test")
            let initial = try await store.read(account: "test")
            XCTAssertEqual(initial, Data([1, 2]))
            try await store.write(Data([3]), account: "test")
            let updated = try await store.read(account: "test")
            XCTAssertEqual(updated, Data([3]))
            try await store.remove(account: "test")
            try await store.remove(account: "test")
            let removed = try await store.read(account: "test")
            XCTAssertNil(removed)
        } catch {
            try? await store.remove(account: "test")
            throw error
        }
    }
}
