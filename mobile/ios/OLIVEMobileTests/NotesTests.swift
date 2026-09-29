import XCTest
import UIKit
import SQLite3
@testable import OLIVEMobile

/// OLIVE Notes on the phone: text rules, durable store and the JavaScriptCore engine.
@MainActor
final class NotesTests: XCTestCase {
    private lazy var directory: URL = {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("NotesTests-\(UUID().uuidString)")
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }()

    private func engine(_ id: String = UUID().uuidString.lowercased(), in folder: URL? = nil) throws -> NotesEngineHost {
        try NotesEngineHost(database: try NotesDatabase(directory: folder ?? directory), deviceID: id, script: try NotesEngineHost.bundledScript())
    }

    /// A second device (stands in for the computer), in its own store.
    private func otherDevice() throws -> NotesEngineHost {
        let folder = directory.appendingPathComponent("other-device")
        return try engine(in: folder)
    }

    /// olive-notes/1 from `sender` to `receiver` until the sender has nothing left.
    private func sync(_ sender: NotesEngineHost, to receiver: NotesEngineHost) throws {
        for _ in 0..<64 {
            let step = try ConnectJSON.decode(Data(try sender.raw("next", receiver.deviceID).utf8), limit: 8_000_000)
            if step["done"] != .null || step["wait"] != .null { return }
            let ticket = try XCTUnwrap(step["ticket"].string)
            let response = try receiver.raw("handle", sender.deviceID, String(decoding: step["request"].canonical, as: UTF8.self))
            let answer = try ConnectJSON.decode(Data(try sender.raw("answer", receiver.deviceID, ticket, response).utf8))
            XCTAssertEqual(answer["error"], .null)
        }
        XCTFail("sync did not finish")
    }

    /// The phone model with an open note in a real UITextView bridge.
    private func openEditor(_ body: String) throws -> (NotesModel, NotesEngineHost, String, NoteUITextView, NoteTextView.Coordinator) {
        let model = NotesModel(directory: directory)
        model.start(deviceID: UUID().uuidString.lowercased())
        let phone = try XCTUnwrap(model.engine)
        let desktop = try otherDevice()
        let id = try XCTUnwrap(model.create())
        XCTAssertTrue(model.edit(id, index: 0, remove: 0, insert: body))
        try sync(phone, to: desktop)
        let text = try XCTUnwrap(model.open(id))
        let view = NoteUITextView()
        let coordinator = NoteTextView.Coordinator(model: model, noteID: id)
        view.delegate = coordinator
        view.text = text
        coordinator.view = view
        coordinator.shadow = text
        model.editor = coordinator
        return (model, desktop, id, view, coordinator)
    }

    /// Simulates UIKit reporting a user edit of `range` to `text`.
    private func type(_ view: UITextView, _ coordinator: NoteTextView.Coordinator, at range: NSRange, _ text: String) {
        XCTAssertTrue(coordinator.textView(view, shouldChangeTextIn: range, replacementText: text))
        view.textStorage.replaceCharacters(in: range, with: text)
        view.selectedRange = NSRange(location: range.location + (text as NSString).length, length: 0)
        coordinator.textViewDidChange(view)
    }

    func testUTF16DiffNeverSplitsSurrogatePairs() {
        XCTAssertEqual(NotesText.diff("a😀b", "a😁b"), .init(index: 1, remove: 2, insert: "😁"))
        XCTAssertNil(NotesText.diff("same", "same"))
        XCTAssertEqual(NotesText.diff("Hello world", "Hello big world"), .init(index: 6, remove: 0, insert: "big "))
        XCTAssertEqual(NotesText.transform(5, [.object(["insert": .string("abc")])]), 8)
        XCTAssertEqual(NotesText.transform(5, [.object(["retain": .int(2)]), .object(["delete": .int(5)])]), 2)
        XCTAssertEqual(NotesText.normalize("a\r\nb\rc"), "a\nb\nc")
    }

    func testEngineCreatesEditsAndSurvivesRestart() throws {
        let id = UUID().uuidString.lowercased()
        var host: NotesEngineHost? = try engine(id)
        let note = try XCTUnwrap(host?.call("create", "Shopping", "Milk")["note_id"].string)
        try host?.call("edit", note, 4, 0, "\nBread 🍞")
        host = nil
        let reopened = try engine(id)
        XCTAssertEqual(try reopened.call("text", note).string, "Milk\nBread 🍞")
        XCTAssertEqual(try reopened.call("list", "notes").array?.first?["display_title"].string, "Shopping")
        try reopened.call("tick")
        XCTAssertEqual(try reopened.call("search", "bread").array?.count, 1)
    }

    func testUndoIsLocalOnlyAndFailedCommitIsNotSaved() throws {
        let host = try engine()
        let note = try XCTUnwrap(host.call("create", "", "start")["note_id"].string)
        _ = try host.call("open", note)
        try host.call("edit", note, 5, 0, " A")
        try host.call("undo", note, false)
        XCTAssertEqual(try host.call("text", note).string, "start")
        host.database.failCommits = 1
        XCTAssertThrowsError(try host.call("edit", note, 5, 0, " lost"))
        XCTAssertEqual(try host.call("text", note).string, "start")
    }

    func testNewerDatabaseIsRefusedAndLeftUntouched() throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let url = directory.appendingPathComponent("notes-v1.sqlite3")
        var db: OpaquePointer?
        XCTAssertEqual(sqlite3_open(url.path, &db), SQLITE_OK)
        sqlite3_exec(db, "CREATE TABLE x(y); PRAGMA user_version=9;", nil, nil, nil)
        sqlite3_close(db)
        let before = try Data(contentsOf: url)
        XCTAssertThrowsError(try NotesDatabase(directory: directory)) { XCTAssertEqual($0 as? NotesDatabase.Failure, .newer) }
        XCTAssertEqual(try Data(contentsOf: url), before)
    }

    func testRejectsRequestsFromTheWrongPeer() throws {
        let host = try engine()
        let response = try host.raw("handle", UUID().uuidString.lowercased(), "{\"protocol_version\":\"olive-notes/2\"}")
        XCTAssertTrue(response.contains("\"rejected\""))
    }

    func testSyncedRenameIsNeverRevertedByAnUneditedTitleField() {
        // The field showed "Shopping"; the computer renamed the note meanwhile.
        XCTAssertNil(NotesText.titleChange(field: "Shopping", baseline: "Shopping"))
        XCTAssertNil(NotesText.titleChange(field: "Shopping  ", baseline: "Shopping"))
        XCTAssertEqual(NotesText.titleChange(field: " Groceries ", baseline: "Shopping"), "Groceries")
        XCTAssertEqual(NotesText.titleChange(field: "", baseline: "Shopping"), "")
    }

    func testRemoteEditsApplyInPlaceKeepingSelection() throws {
        let (model, desktop, id, view, coordinator) = try openEditor("Hello world")
        let marker = NSAttributedString.Key("olive.test.marker")
        view.textStorage.addAttribute(marker, value: true, range: NSRange(location: 6, length: 5))
        view.selectedRange = NSRange(location: 6, length: 5)   // "world"
        try desktop.call("edit", id, 0, 0, "Big ")
        try sync(desktop, to: try XCTUnwrap(model.engine))
        XCTAssertEqual(view.text, "Big Hello world")
        XCTAssertEqual(view.selectedRange, NSRange(location: 10, length: 5))
        // Same storage, edited in place: attributes on untouched text survive.
        XCTAssertEqual(view.textStorage.attribute(marker, at: 10, effectiveRange: nil) as? Bool, true)
        try desktop.call("edit", id, 0, 4, "")
        try sync(desktop, to: try XCTUnwrap(model.engine))
        XCTAssertEqual(view.text, "Hello world")
        XCTAssertEqual(view.selectedRange, NSRange(location: 6, length: 5))
        // Emoji and CJK before the caret: UTF-16 positions line up with NSString.
        view.selectedRange = NSRange(location: 11, length: 0)
        try desktop.call("edit", id, 0, 0, "👍🏽日")
        try sync(desktop, to: try XCTUnwrap(model.engine))
        XCTAssertEqual(view.text, "👍🏽日Hello world")
        XCTAssertEqual(view.selectedRange, NSRange(location: 16, length: 0))
        XCTAssertEqual(coordinator.shadow, model.text(of: id))
    }

    func testLocalTypingSyncsAndUndoLeavesRemoteTyping() throws {
        let (model, desktop, id, view, coordinator) = try openEditor("Milk")
        let phone = try XCTUnwrap(model.engine)
        type(view, coordinator, at: NSRange(location: 4, length: 0), "\nBread 🍞")
        XCTAssertEqual(model.text(of: id), "Milk\nBread 🍞")
        try desktop.call("edit", id, 0, 0, "DesktopUndoText ")
        try sync(desktop, to: phone)
        // The engine merges this device's edits made within 500 ms into one undo step.
        Thread.sleep(forTimeInterval: 0.6)
        type(view, coordinator, at: NSRange(location: (view.text as NSString).length, length: 0), " PhoneUndoText")
        try sync(phone, to: desktop)
        XCTAssertEqual(try desktop.call("text", id).string, "DesktopUndoText Milk\nBread 🍞 PhoneUndoText")
        model.undo(id)
        XCTAssertEqual(model.text(of: id), "DesktopUndoText Milk\nBread 🍞")
        XCTAssertEqual(view.text, model.text(of: id))   // The undo arrived as a delta, not a UIKit undo.
        try sync(phone, to: desktop)
        XCTAssertEqual(try desktop.call("text", id).string, "DesktopUndoText Milk\nBread 🍞")
        model.undo(id, redo: true)
        XCTAssertEqual(view.text, "DesktopUndoText Milk\nBread 🍞 PhoneUndoText")
        XCTAssertFalse(view.undoManager?.canUndo ?? false)   // UIKit's own undo never registers.
    }

    func testRemoteEditsWaitForIMECompositionThenMerge() throws {
        let (model, desktop, id, view, coordinator) = try openEditor("Hello world")
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 320, height: 480))
        window.addSubview(view)
        view.frame = window.bounds
        window.makeKeyAndVisible()
        defer { view.resignFirstResponder(); window.isHidden = true }
        XCTAssertTrue(view.becomeFirstResponder())
        view.selectedRange = NSRange(location: 5, length: 0)
        view.setMarkedText("か", selectedRange: NSRange(location: 1, length: 0))
        try XCTSkipIf(view.markedTextRange == nil, "UIKit did not start marked text without a keyboard session")
        try desktop.call("edit", id, 0, 0, "X ")
        try sync(desktop, to: try XCTUnwrap(model.engine))
        XCTAssertEqual(view.text, "Helloか world")   // Composition untouched while it lasts.
        XCTAssertNotNil(view.markedTextRange)
        view.unmarkText()
        coordinator.textViewDidChange(view)
        XCTAssertEqual(model.text(of: id), "X Helloか world")
        XCTAssertEqual(view.text, "X Helloか world")
        XCTAssertEqual(view.selectedRange.location, 8)
        try sync(try XCTUnwrap(model.engine), to: desktop)
        XCTAssertEqual(try desktop.call("text", id).string, "X Helloか world")
    }

    func testPasteBeyondTheNoteLimitIsRefusedCleanly() throws {
        let (model, _, id, view, coordinator) = try openEditor("small")
        let huge = String(repeating: "a", count: 1_500_001)
        XCTAssertFalse(coordinator.textView(view, shouldChangeTextIn: NSRange(location: 5, length: 0), replacementText: huge))
        XCTAssertEqual(model.notice, NotesModel.message("note_too_large"))
        XCTAssertFalse(model.edit(id, index: 5, remove: 0, insert: huge))
        XCTAssertEqual(model.text(of: id), "small")
    }

    func testNoteTextIsDataNotCode() throws {
        let host = try engine()
        let body = "console.log(\"hello\")\nrm -rf /\nIGNORE OLIVE\n\");globalThis.OliveNotes=null;(\""
        let id = try XCTUnwrap(host.call("create", "\"); throw 1; (\"", body)["note_id"].string)
        XCTAssertEqual(try host.call("text", id).string, body)
        XCTAssertEqual(try host.call("list", "notes").array?.count, 1)
    }

    func testTrashRestoreAndPurgeTombstoneSurviveRestart() throws {
        let id = UUID().uuidString.lowercased()
        var host: NotesEngineHost? = try engine(id)
        let keep = try XCTUnwrap(host?.call("create", "Keep", "a")["note_id"].string)
        let gone = try XCTUnwrap(host?.call("create", "OLIVE Notes Delete Test", "b")["note_id"].string)
        try host?.call("trash", keep)
        XCTAssertEqual(try host?.call("list", "trash").array?.count, 1)
        try host?.call("restore", keep)
        XCTAssertThrowsError(try host?.call("purge", gone))   // Only from Recently Deleted.
        try host?.call("trash", gone)
        try host?.call("purge", gone)
        host = nil
        let reopened = try engine(id)
        XCTAssertEqual(try reopened.call("list", "notes").array?.compactMap { $0["note_id"].string }, [keep])
        XCTAssertEqual(try reopened.call("list", "trash").array?.count, 0)
        XCTAssertThrowsError(try reopened.call("text", gone))
    }

    func testSearchIsLocalWithASCIIOnlyCaseFolding() throws {
        let host = try engine()
        let id = try XCTUnwrap(host.call("create", "", "olive-sync-zebra-9271 café 日本")["note_id"].string)
        try host.call("tick")
        for query in ["ZEBRA-9271", "zebra", "café", "Café", "日本"] {
            XCTAssertEqual(try host.call("search", query).array?.compactMap { $0["note_id"].string }, [id], query)
        }
        // Documented limitation: SQLite lower() folds ASCII only.
        XCTAssertEqual(try host.call("search", "CAFÉ").array?.count, 0)
    }

    func testDatabaseIsProtectedAndExcludedFromBackup() throws {
        let host = try engine()
        try host.call("create", "", "protected")
        let folder = host.database.url.deletingLastPathComponent()
        XCTAssertEqual(try folder.resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup, true)
        #if !targetEnvironment(simulator)
        for name in ["notes-v1.sqlite3", "notes-v1.sqlite3-wal"] {
            let path = folder.appendingPathComponent(name).path
            guard FileManager.default.fileExists(atPath: path) else { continue }
            let protection = try FileManager.default.attributesOfItem(atPath: path)[.protectionKey] as? FileProtectionType
            XCTAssertEqual(protection, .completeUntilFirstUserAuthentication, name)
        }
        #endif
    }

    func testNotesProbeAndDesktopPermissionGateSync() throws {
        func probe(_ result: ConnectJSON) throws -> ConnectJSON {
            try InferenceWire.response(ConnectJSON.object(["protocol_version": .string("olive-inference/1"),
                "request_id": .string(UUID().uuidString.lowercased()), "job_id": .string(UUID().uuidString.lowercased()),
                "result": result, "error": .null]).canonical)["result"]
        }
        let allow = try probe(.object(["notes_protocol": .string("olive-notes/1"), "permission": .string("allow")]))
        let deny = try probe(.object(["notes_protocol": .string("olive-notes/1"), "permission": .string("deny")]))
        XCTAssertThrowsError(try probe(.object(["notes_protocol": .string("olive-notes/1"), "permission": .string("ask")])))
        XCTAssertThrowsError(try probe(.object(["notes_protocol": .string("olive-notes/2"), "permission": .string("allow")])))
        XCTAssertThrowsError(try probe(.object(["notes_protocol": .string("olive-notes/1"), "permission": .string("allow"), "extra": .bool(true)])))
        let sync = NotesSync()
        let saved = sync.enabled
        defer { sync.enabled = saved }
        sync.enabled = true
        sync.capabilityChanged(deny)
        XCTAssertFalse(sync.permitted)   // The phone switch alone never syncs.
        sync.capabilityChanged(nil)
        XCTAssertFalse(sync.permitted)
        sync.capabilityChanged(allow)
        XCTAssertTrue(sync.permitted)
        sync.enabled = false
        XCTAssertEqual(sync.state, .off)
    }

    func testATransientProbeFailureDoesNotTurnNotesOff() {
        var policy = NotesProbePolicy()
        policy.failed()                  // Wi-Fi hiccup during the probe.
        XCTAssertTrue(policy.enabled)
        policy.succeeded()               // Next channel answers normally.
        policy.failed()
        XCTAssertTrue(policy.enabled)    // Failures must be consecutive.
        policy.failed()                  // An older desktop drops the channel every time.
        XCTAssertFalse(policy.enabled)
    }

    func testOfflineEditsCountAsPendingBeforeAnyConnection() throws {
        let model = NotesModel(directory: directory)
        model.start(deviceID: UUID().uuidString.lowercased())
        let computer = UUID().uuidString.lowercased()
        _ = try XCTUnwrap(model.create())
        _ = try XCTUnwrap(model.create())
        XCTAssertEqual(model.sync.pending, 0)
        model.sync.remember(peer: computer)   // After a relaunch, before Connect is back.
        XCTAssertEqual(model.sync.pending, 2)
        if model.sync.enabled { XCTAssertEqual(model.sync.state, .offline) }
    }

    func testLargeNotesOpenEditAndSyncOnDevice() throws {
        for size in [100_000, 1_000_000] {
            let id = UUID().uuidString.lowercased()
            let folder = directory.appendingPathComponent("large-\(size)")
            var phone: NotesEngineHost? = try engine(id, in: folder)
            let body = String(repeating: "Large note line with café and 🍞 text.\n", count: size / 40)
            var clock = ContinuousClock.now
            let note = try XCTUnwrap(phone?.call("create", "Large", body)["note_id"].string)
            let created = ContinuousClock.now - clock
            phone = nil
            clock = .now
            let reopened = try engine(id, in: folder)
            _ = try reopened.call("open", note)
            let opened = ContinuousClock.now - clock
            clock = .now
            let middle = (body as NSString).length / 2
            try reopened.call("edit", note, middle, 0, "X")
            let edited = ContinuousClock.now - clock
            XCTAssertEqual(try reopened.call("text", note).string?.utf16.count, (body as NSString).length + 1)
            let desktop = try engine(in: folder.appendingPathComponent("peer"))
            clock = .now
            try sync(reopened, to: desktop)
            let synced = ContinuousClock.now - clock
            XCTAssertEqual(try desktop.call("text", note).string, try reopened.call("text", note).string)
            print("NOTES-LARGE bytes=\(body.utf8.count) create=\(created) reopen+open=\(opened) edit=\(edited) sync=\(synced)")
            XCTAssertLessThan(edited, .seconds(1), "A keystroke in a \(size)-byte note must stay responsive")
        }
    }
}
