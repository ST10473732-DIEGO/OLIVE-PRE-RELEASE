import Foundation
import SQLite3
import CryptoKit

/// Durable OLIVE Notes storage on the phone (schema v1, SQLite).
///
/// The JavaScriptCore engine (NotesEngine.js) owns the document logic; this
/// store applies each engine batch in ONE transaction, so a note's CRDT update,
/// metadata row and change-feed position commit together or not at all. An
/// unrecognised or newer database is never modified or replaced.
final class NotesDatabase {
    enum Failure: Error, Equatable { case unavailable, newer, unrecognized }
    static let version: Int32 = 1
    let url: URL
    private var db: OpaquePointer?
    /// Interop-harness hook: make the next N commits fail (tests only).
    var failCommits = 0

    init(directory: URL) throws {
        url = directory.appendingPathComponent("notes-v1.sqlite3")
        let manager = FileManager.default
        try manager.createDirectory(at: directory, withIntermediateDirectories: true,
            attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        var folder = directory
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try? folder.setResourceValues(values)
        let existed = manager.fileExists(atPath: url.path)
        if existed {
            // Decide read-only first: an unknown file must not even switch to WAL.
            var probe: OpaquePointer?
            guard sqlite3_open_v2(url.path, &probe, SQLITE_OPEN_READONLY, nil) == SQLITE_OK else { sqlite3_close(probe); throw Failure.unavailable }
            defer { sqlite3_close(probe) }
            let version = Self.integer(probe, "PRAGMA user_version")
            let tables = Self.integer(probe, "SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
            if version > Self.version { throw Failure.newer }
            if version == 0 && tables > 0 { throw Failure.unrecognized }
        }
        let flags = SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX
        guard sqlite3_open_v2(url.path, &db, flags, nil) == SQLITE_OK else { sqlite3_close(db); db = nil; throw Failure.unavailable }
        try? manager.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: url.path)
        try exec("PRAGMA journal_mode=WAL")
        try exec("PRAGMA synchronous=FULL")
        try exec("PRAGMA foreign_keys=ON")
        if Self.integer(db, "PRAGMA user_version") == 0 {
            try transaction {
                try exec("""
                CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE notes(note_id TEXT PRIMARY KEY, record TEXT NOT NULL);
                CREATE TABLE note_snapshots(note_id TEXT PRIMARY KEY REFERENCES notes(note_id) ON DELETE CASCADE,
                    state BLOB NOT NULL, sha256 TEXT NOT NULL);
                CREATE TABLE note_updates(seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    note_id TEXT NOT NULL REFERENCES notes(note_id) ON DELETE CASCADE, update_id TEXT NOT NULL UNIQUE,
                    payload BLOB NOT NULL, sha256 TEXT NOT NULL, origin TEXT NOT NULL, device_id TEXT NOT NULL);
                CREATE INDEX note_updates_note ON note_updates(note_id, seq);
                CREATE TABLE note_purges(note_id TEXT PRIMARY KEY, record TEXT NOT NULL);
                CREATE TABLE note_peers(device_id TEXT PRIMARY KEY, record TEXT NOT NULL);
                CREATE TABLE note_search(note_id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL);
                INSERT INTO meta VALUES('store_seq','0');
                INSERT INTO meta VALUES('epoch','');
                PRAGMA user_version=1;
                """)
            }
        }
    }

    deinit { sqlite3_close(db) }

    // MARK: SQLite plumbing

    private static func integer(_ handle: OpaquePointer?, _ sql: String) -> Int64 {
        var statement: OpaquePointer?
        defer { sqlite3_finalize(statement) }
        guard sqlite3_prepare_v2(handle, sql, -1, &statement, nil) == SQLITE_OK, sqlite3_step(statement) == SQLITE_ROW else { return -1 }
        return sqlite3_column_int64(statement, 0)
    }

    private func exec(_ sql: String) throws {
        guard sqlite3_exec(db, sql, nil, nil, nil) == SQLITE_OK else { throw Failure.unavailable }
    }

    private func transaction(_ body: () throws -> Void) throws {
        try exec("BEGIN IMMEDIATE")
        do { try body(); try exec("COMMIT") }
        catch { sqlite3_exec(db, "ROLLBACK", nil, nil, nil); throw error }
    }

    private enum Value { case text(String), blob(Data), int(Int64), null }
    private static var transient: sqlite3_destructor_type { unsafeBitCast(-1, to: sqlite3_destructor_type.self) }

    @discardableResult
    private func run(_ sql: String, _ values: [Value] = [], row: ((OpaquePointer?) -> Void)? = nil) throws -> Int {
        var statement: OpaquePointer?
        defer { sqlite3_finalize(statement) }
        guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK else { throw Failure.unavailable }
        for (offset, value) in values.enumerated() {
            let index = Int32(offset + 1)
            switch value {
            case .text(let text): sqlite3_bind_text(statement, index, text, -1, Self.transient)
            case .blob(let data): _ = data.withUnsafeBytes { sqlite3_bind_blob(statement, index, $0.baseAddress, Int32(data.count), Self.transient) }
            case .int(let number): sqlite3_bind_int64(statement, index, number)
            case .null: sqlite3_bind_null(statement, index)
            }
        }
        var rows = 0
        while true {
            let result = sqlite3_step(statement)
            if result == SQLITE_ROW { rows += 1; row?(statement); continue }
            guard result == SQLITE_DONE else { throw Failure.unavailable }
            return rows
        }
    }

    private static func text(_ statement: OpaquePointer?, _ column: Int32) -> String {
        guard let pointer = sqlite3_column_text(statement, column) else { return "" }
        return String(cString: pointer)
    }

    private static func blob(_ statement: OpaquePointer?, _ column: Int32) -> Data {
        guard let pointer = sqlite3_column_blob(statement, column) else { return Data() }
        return Data(bytes: pointer, count: Int(sqlite3_column_bytes(statement, column)))
    }

    static func sha256(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }

    private func json(_ object: Any) -> String {
        (try? JSONSerialization.data(withJSONObject: object)).map { String(decoding: $0, as: UTF8.self) } ?? "null"
    }

    // MARK: Engine host operations

    func loadIndex() throws -> String {
        var rows: [Any] = [], purges: [Any] = [], peers: [Any] = []
        var meta: [String: Any] = [:]
        for (sql, target) in [("SELECT record FROM notes", 0), ("SELECT record FROM note_purges", 1), ("SELECT record FROM note_peers", 2)] {
            try run(sql) { statement in
                guard let value = try? JSONSerialization.jsonObject(with: Data(Self.text(statement, 0).utf8)) else { return }
                if target == 0 { rows.append(value) } else if target == 1 { purges.append(value) } else { peers.append(value) }
            }
        }
        try run("SELECT key, value FROM meta") { statement in meta[Self.text(statement, 0)] = Self.text(statement, 1) }
        let stored: [String: Any] = ["store_seq": Int64(meta["store_seq"] as? String ?? "0") ?? 0, "epoch": meta["epoch"] as? String ?? ""]
        return json(["rows": rows, "purges": purges, "peers": peers, "meta": stored])
    }

    /// Snapshot + ordered updates, or {"corrupt":true} when a checksum fails
    /// (the bytes are kept for recovery; nothing is repaired automatically).
    func loadDocument(_ noteID: String) throws -> String {
        var exists = false
        try run("SELECT 1 FROM notes WHERE note_id=?", [.text(noteID)]) { _ in exists = true }
        guard exists else { return "null" }
        var snapshot: String?
        var corrupt = false
        try run("SELECT state, sha256 FROM note_snapshots WHERE note_id=?", [.text(noteID)]) { statement in
            let state = Self.blob(statement, 0)
            if Self.sha256(state) != Self.text(statement, 1) { corrupt = true } else { snapshot = state.base64EncodedString() }
        }
        var updates: [String] = []
        try run("SELECT payload, sha256 FROM note_updates WHERE note_id=? ORDER BY seq", [.text(noteID)]) { statement in
            let payload = Self.blob(statement, 0)
            if Self.sha256(payload) != Self.text(statement, 1) { corrupt = true } else { updates.append(payload.base64EncodedString()) }
        }
        if corrupt { return json(["corrupt": true]) }
        return json(["snapshot": snapshot.map { $0 as Any } ?? NSNull(), "updates": updates])
    }

    /// Applies one engine batch atomically. false = nothing was written.
    func commit(_ raw: String) -> Bool {
        if failCommits > 0 { failCommits -= 1; return false }
        guard let batch = (try? JSONSerialization.jsonObject(with: Data(raw.utf8))) as? [String: Any] else { return false }
        do {
            try transaction {
                if let epoch = batch["epoch"] as? String { try run("UPDATE meta SET value=? WHERE key='epoch'", [.text(epoch)]) }
                if let seq = batch["store_seq"] as? NSNumber { try run("UPDATE meta SET value=? WHERE key='store_seq'", [.text(seq.stringValue)]) }
                for row in batch["rows"] as? [[String: Any]] ?? [] {
                    guard let id = row["note_id"] as? String else { throw Failure.unavailable }
                    try run("INSERT INTO notes VALUES(?,?) ON CONFLICT(note_id) DO UPDATE SET record=excluded.record", [.text(id), .text(json(row))])
                }
                for id in batch["delete_notes"] as? [String] ?? [] {
                    try run("DELETE FROM notes WHERE note_id=?", [.text(id)])
                    try run("DELETE FROM note_search WHERE note_id=?", [.text(id)])
                }
                for purge in batch["purges"] as? [[String: Any]] ?? [] {
                    guard let id = purge["note_id"] as? String else { throw Failure.unavailable }
                    try run("INSERT OR REPLACE INTO note_purges VALUES(?,?)", [.text(id), .text(json(purge))])
                }
                for update in batch["updates"] as? [[String: Any]] ?? [] {
                    guard let id = update["note_id"] as? String, let key = update["update_id"] as? String,
                          let encoded = update["payload"] as? String, let payload = Data(base64Encoded: encoded) else { throw Failure.unavailable }
                    try run("INSERT OR IGNORE INTO note_updates(note_id,update_id,payload,sha256,origin,device_id) VALUES(?,?,?,?,?,?)",
                        [.text(id), .text(key), .blob(payload), .text(Self.sha256(payload)),
                         .text(update["origin"] as? String ?? ""), .text(update["device"] as? String ?? "")])
                }
                for peer in batch["peers"] as? [[String: Any]] ?? [] {
                    guard let id = peer["device_id"] as? String else { throw Failure.unavailable }
                    try run("INSERT OR REPLACE INTO note_peers VALUES(?,?)", [.text(id), .text(json(peer))])
                }
                for row in batch["search"] as? [[String: Any]] ?? [] {
                    guard let id = row["note_id"] as? String else { throw Failure.unavailable }
                    try run("INSERT OR REPLACE INTO note_search VALUES(?,?,?)", [.text(id), .text(row["title"] as? String ?? ""), .text(row["body"] as? String ?? "")])
                }
                for snapshot in batch["snapshots"] as? [[String: Any]] ?? [] {
                    guard let id = snapshot["note_id"] as? String, let encoded = snapshot["state"] as? String,
                          let state = Data(base64Encoded: encoded), Self.sha256(state) == snapshot["sha256"] as? String else { throw Failure.unavailable }
                    try run("INSERT OR REPLACE INTO note_snapshots VALUES(?,?,?)", [.text(id), .blob(state), .text(Self.sha256(state))])
                    try run("DELETE FROM note_updates WHERE note_id=?", [.text(id)])
                }
            }
            return true
        } catch {
            return false
        }
    }

    /// Local search only. SQLite lower() folds ASCII; other scripts match exactly.
    func search(_ query: String) throws -> String {
        var ids: [String] = []
        try run("SELECT note_id FROM note_search WHERE instr(lower(title) || char(10) || lower(body), lower(?)) > 0 LIMIT 50",
                [.text(query)]) { statement in ids.append(Self.text(statement, 0)) }
        return json(ids)
    }
}
