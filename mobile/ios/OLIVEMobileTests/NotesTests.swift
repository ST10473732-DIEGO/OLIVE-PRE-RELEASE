import XCTest
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

    private func engine(_ id: String = UUID().uuidString.lowercased()) throws -> NotesEngineHost {
        try NotesEngineHost(database: try NotesDatabase(directory: directory), deviceID: id, script: try NotesEngineHost.bundledScript())
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
}
