import Foundation
import SQLite3

/// Fixed, content-free storage failure categories (store.py DrawStorageError).
enum DrawStorageError: Error, Equatable {
    case unavailable, newer, unrecognized
    var code: String {
        switch self {
        case .unavailable: "draw_storage_unavailable"
        case .newer: "draw_storage_newer"
        case .unrecognized: "draw_storage_unrecognized"
        }
    }
}

/// One materialized drawing row (the `drawings` table).
struct DrawingRow: Equatable, Sendable {
    var drawingID: String
    var title: String
    var titleKey: String
    var createdAt: String
    var updatedAt: String
    var width: Int
    var height: Int
    var background: String
    var createdBy: String
    var schemaVersion: Int
    var revision: Int
    var lastSeq: Int64
    var clock: Int64
    var opCount: Int
    var recordCount: Int
    var docBytes: Int
    var trashed: Bool
    var trashedAt: String
    var trashedKey: String
    var status: String
}

/// Durable OLIVE Draw storage on the phone: one SQLite database (WAL,
/// synchronous=FULL), the same logical layout as desktop store schema 2:
///
///   meta(store_id, epoch, feed_seq), drawings, draw_records, draw_visibility,
///   draw_history, draw_purges, draw_assets, draw_wanted, draw_peers, draw_thumbnails
///
/// Every change commits in ONE transaction. A newer or unrecognised database is
/// never modified (not even switched to WAL). The replica rules (`insert`,
/// `fold`, `rematerialize`) are a line-by-line port of `olive/draw/records.py`.
///
/// Not thread-safe by design: `DrawEngine` (an actor) is its only owner.
final class DrawStore {
    static let version: Int32 = 2
    static let fileName = "drawings.sqlite3"
    static let defaultTitle = "Untitled drawing"
    let url: URL
    private var db: OpaquePointer?
    private var depth = 0
    /// Harness hook: make the next N transactions fail before commit.
    var failCommits = 0

    private static let schema = """
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE drawings(
        drawing_id TEXT PRIMARY KEY, title TEXT NOT NULL, title_key TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
        background TEXT NOT NULL, created_by TEXT NOT NULL DEFAULT '', schema_version INTEGER NOT NULL DEFAULT 1,
        revision INTEGER NOT NULL DEFAULT 0, last_seq INTEGER NOT NULL DEFAULT 0, clock INTEGER NOT NULL DEFAULT 0,
        op_count INTEGER NOT NULL DEFAULT 0, record_count INTEGER NOT NULL DEFAULT 0, doc_bytes INTEGER NOT NULL DEFAULT 0,
        trashed INTEGER NOT NULL DEFAULT 0, trashed_at TEXT NOT NULL DEFAULT '', trashed_key TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'ok');
    CREATE INDEX drawings_by_change ON drawings(trashed, last_seq);
    CREATE TABLE draw_records(
        seq INTEGER PRIMARY KEY, record_id TEXT NOT NULL UNIQUE, drawing_id TEXT NOT NULL, kind TEXT NOT NULL,
        device TEXT NOT NULL, lamport INTEGER NOT NULL, sort_key TEXT NOT NULL, target TEXT, body TEXT NOT NULL,
        bytes INTEGER NOT NULL, source TEXT NOT NULL DEFAULT '', received_at TEXT NOT NULL);
    CREATE INDEX draw_records_drawing ON draw_records(drawing_id, kind, sort_key);
    CREATE INDEX draw_records_target ON draw_records(target);
    CREATE TABLE draw_visibility(target TEXT PRIMARY KEY, hidden INTEGER NOT NULL, key TEXT NOT NULL);
    CREATE TABLE draw_history(
        drawing_id TEXT NOT NULL, stack TEXT NOT NULL, pos INTEGER NOT NULL, record_id TEXT NOT NULL,
        PRIMARY KEY(drawing_id, stack, pos));
    CREATE TABLE draw_purges(drawing_id TEXT PRIMARY KEY, purged_at TEXT NOT NULL, device TEXT NOT NULL,
        seq INTEGER NOT NULL UNIQUE);
    CREATE TABLE draw_assets(
        asset_id TEXT PRIMARY KEY, mime TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
        size INTEGER NOT NULL, data BLOB NOT NULL, created_at TEXT NOT NULL, origin TEXT NOT NULL);
    CREATE TABLE draw_wanted(asset_id TEXT PRIMARY KEY, drawing_id TEXT NOT NULL, since TEXT NOT NULL);
    CREATE TABLE draw_peers(
        device_id TEXT PRIMARY KEY, acked_seq INTEGER NOT NULL DEFAULT 0,
        peer_epoch TEXT, last_sync TEXT, last_error TEXT, protocol TEXT);
    CREATE TABLE draw_thumbnails(
        drawing_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, mime TEXT NOT NULL,
        image BLOB NOT NULL, created_at TEXT NOT NULL);
    """

    /// Opens (or creates) `drawings.sqlite3` in `directory` with the same iOS
    /// Data Protection class as the Notes companion store.
    init(directory: URL) throws {
        url = directory.appendingPathComponent(Self.fileName)
        let manager = FileManager.default
        do {
            try manager.createDirectory(at: directory, withIntermediateDirectories: true,
                attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        } catch { throw DrawStorageError.unavailable }
        try? manager.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: directory.path)
        var folder = directory
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try? folder.setResourceValues(values)
        if manager.fileExists(atPath: url.path) {
            // Decide with a read-only probe: an unrecognised or newer database
            // must not be modified at all (not even switched to WAL).
            var probe: OpaquePointer?
            guard sqlite3_open_v2(url.path, &probe, SQLITE_OPEN_READONLY, nil) == SQLITE_OK else {
                sqlite3_close(probe); throw DrawStorageError.unavailable
            }
            defer { sqlite3_close(probe) }
            guard let version = Self.scalar(probe, "PRAGMA user_version"),
                  let tables = Self.scalar(probe, "SELECT COUNT(*) FROM sqlite_master WHERE type='table'") else {
                throw DrawStorageError.unavailable
            }
            if version > Int64(Self.version) { throw DrawStorageError.newer }
            if version == 0 && tables > 0 { throw DrawStorageError.unrecognized }
            if version == 1 { throw DrawStorageError.unrecognized }   // Store schema 1 never existed on the phone.
        }
        guard sqlite3_open_v2(url.path, &db, SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_NOMUTEX, nil) == SQLITE_OK else {
            sqlite3_close(db); db = nil; throw DrawStorageError.unavailable
        }
        try? manager.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: url.path)
        do {
            try exec("PRAGMA journal_mode=WAL")
            try exec("PRAGMA synchronous=FULL")
            try exec("PRAGMA foreign_keys=ON")
            try exec("PRAGMA journal_size_limit=8388608")
            try transaction {
                let version = try int("PRAGMA user_version")
                if version > Int64(Self.version) { throw DrawStorageError.newer }
                if version == 0 {
                    if try int("SELECT COUNT(*) FROM sqlite_master WHERE type='table'") > 0 { throw DrawStorageError.unrecognized }
                    try exec(Self.schema)
                    for (key, value) in [("store_id", UUID().uuidString.lowercased()), ("epoch", UUID().uuidString.lowercased()), ("feed_seq", "0")] {
                        try run("INSERT OR IGNORE INTO meta VALUES(?,?)", [.text(key), .text(value)])
                    }
                    try exec("PRAGMA user_version=2")
                }
            }
            // The -wal/-shm companions inherit the directory's protection class; set it explicitly too.
            for suffix in ["-wal", "-shm"] where manager.fileExists(atPath: url.path + suffix) {
                try? manager.setAttributes([.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication], ofItemAtPath: url.path + suffix)
            }
        } catch let failure as DrawStorageError {
            sqlite3_close(db); db = nil; throw failure
        } catch {
            sqlite3_close(db); db = nil; throw DrawStorageError.unavailable
        }
    }

    deinit { sqlite3_close(db) }

    /// Backup/diagnostic validation: integrity and a recognised version.
    func integrityOK() -> Bool {
        var result = ""
        _ = try? run("PRAGMA integrity_check") { result = Self.text($0, 0) }
        return result == "ok"
    }

    // MARK: SQLite plumbing

    enum Value { case text(String), blob(Data), int(Int64), null }
    private static var transient: sqlite3_destructor_type { unsafeBitCast(-1, to: sqlite3_destructor_type.self) }

    private static func scalar(_ handle: OpaquePointer?, _ sql: String) -> Int64? {
        var statement: OpaquePointer?
        defer { sqlite3_finalize(statement) }
        guard sqlite3_prepare_v2(handle, sql, -1, &statement, nil) == SQLITE_OK, sqlite3_step(statement) == SQLITE_ROW else { return nil }
        return sqlite3_column_int64(statement, 0)
    }

    private func exec(_ sql: String) throws {
        guard sqlite3_exec(db, sql, nil, nil, nil) == SQLITE_OK else { throw DrawStorageError.unavailable }
    }

    /// One transaction (nested calls join the outer one). Rolls back on any error.
    func transaction<T>(_ body: () throws -> T) throws -> T {
        if depth > 0 { return try body() }
        try exec("BEGIN IMMEDIATE")
        depth = 1
        defer { depth = 0 }
        do {
            let value = try body()
            if failCommits > 0 { failCommits -= 1; throw DrawStorageError.unavailable }
            try exec("COMMIT")
            return value
        } catch {
            sqlite3_exec(db, "ROLLBACK", nil, nil, nil)
            throw error
        }
    }

    @discardableResult
    func run(_ sql: String, _ values: [Value] = [], row: ((OpaquePointer?) throws -> Void)? = nil) throws -> Int {
        var statement: OpaquePointer?
        defer { sqlite3_finalize(statement) }
        guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK else { throw DrawStorageError.unavailable }
        for (offset, value) in values.enumerated() {
            let index = Int32(offset + 1)
            switch value {
            case .text(let text): sqlite3_bind_text(statement, index, text, -1, Self.transient)
            case .blob(let data):
                _ = data.withUnsafeBytes { sqlite3_bind_blob(statement, index, $0.baseAddress ?? UnsafeRawPointer(bitPattern: 1), Int32(data.count), Self.transient) }
            case .int(let number): sqlite3_bind_int64(statement, index, number)
            case .null: sqlite3_bind_null(statement, index)
            }
        }
        var rows = 0
        while true {
            let result = sqlite3_step(statement)
            if result == SQLITE_ROW { rows += 1; try row?(statement); continue }
            guard result == SQLITE_DONE else { throw DrawStorageError.unavailable }
            return rows
        }
    }

    func int(_ sql: String, _ values: [Value] = []) throws -> Int64 {
        var value: Int64 = 0
        try run(sql, values) { value = sqlite3_column_int64($0, 0) }
        return value
    }

    func optionalText(_ sql: String, _ values: [Value] = []) throws -> String? {
        var value: String?
        try run(sql, values) { value = Self.text($0, 0) }
        return value
    }

    func exists(_ sql: String, _ values: [Value] = []) throws -> Bool { try run(sql, values) > 0 }

    static func text(_ statement: OpaquePointer?, _ column: Int32) -> String {
        guard let pointer = sqlite3_column_text(statement, column) else { return "" }
        return String(cString: pointer)
    }

    static func blob(_ statement: OpaquePointer?, _ column: Int32) -> Data {
        guard let pointer = sqlite3_column_blob(statement, column) else { return Data() }
        return Data(bytes: pointer, count: Int(sqlite3_column_bytes(statement, column)))
    }

    static func isNull(_ statement: OpaquePointer?, _ column: Int32) -> Bool { sqlite3_column_type(statement, column) == SQLITE_NULL }

    // MARK: Feed and meta

    func nextSeq() throws -> Int64 {
        let value = (Int64(try optionalText("SELECT value FROM meta WHERE key='feed_seq'") ?? "0") ?? 0) + 1
        try run("UPDATE meta SET value=? WHERE key='feed_seq'", [.text(String(value))])
        return value
    }

    func meta(_ key: String) throws -> String? { try optionalText("SELECT value FROM meta WHERE key=?", [.text(key)]) }
    func setMeta(_ key: String, _ value: String) throws { try run("INSERT OR REPLACE INTO meta VALUES(?,?)", [.text(key), .text(value)]) }

    private static let drawingColumns = "drawing_id,title,title_key,created_at,updated_at,width,height,background,created_by," +
        "schema_version,revision,last_seq,clock,op_count,record_count,doc_bytes,trashed,trashed_at,trashed_key,status"

    static func drawingRow(_ s: OpaquePointer?, offset: Int32 = 0) -> DrawingRow {
        func t(_ i: Int32) -> String { text(s, offset + i) }
        func n(_ i: Int32) -> Int64 { sqlite3_column_int64(s, offset + i) }
        return DrawingRow(drawingID: t(0), title: t(1), titleKey: t(2), createdAt: t(3), updatedAt: t(4), width: Int(n(5)),
                          height: Int(n(6)), background: t(7), createdBy: t(8), schemaVersion: Int(n(9)), revision: Int(n(10)),
                          lastSeq: n(11), clock: n(12), opCount: Int(n(13)), recordCount: Int(n(14)), docBytes: Int(n(15)),
                          trashed: n(16) != 0, trashedAt: t(17), trashedKey: t(18), status: t(19))
    }

    func drawing(_ did: String) throws -> DrawingRow? {
        var row: DrawingRow?
        try run("SELECT \(Self.drawingColumns) FROM drawings WHERE drawing_id=?", [.text(did)]) { row = Self.drawingRow($0) }
        return row
    }

    func drawings(trashed: Bool) throws -> [(DrawingRow, Int?)] {
        var rows: [(DrawingRow, Int?)] = []
        let order = trashed ? "d.trashed_at DESC, d.last_seq DESC" : "d.last_seq DESC"
        let columns = Self.drawingColumns.split(separator: ",").map { "d." + $0 }.joined(separator: ",")
        try run("SELECT \(columns), t.revision FROM drawings d LEFT JOIN draw_thumbnails t ON t.drawing_id=d.drawing_id " +
                "WHERE d.trashed=? ORDER BY \(order) LIMIT ?", [.int(trashed ? 1 : 0), .int(Int64(DrawSpec.Limit.maxDrawings))]) { s in
            rows.append((Self.drawingRow(s), Self.isNull(s, 20) ? nil : Int(sqlite3_column_int64(s, 20))))
        }
        return rows
    }

    func purged(_ did: String) throws -> Bool { try exists("SELECT 1 FROM draw_purges WHERE drawing_id=?", [.text(did)]) }

    // MARK: Replica rules (records.py)

    /// Validate, store and materialize one record. Returns "applied",
    /// "duplicate", "purged" or "rejected:<code>". Never partially applies:
    /// the caller's transaction commits or rolls back as a whole.
    func insert(_ value: ConnectJSON, source: String = "", now: String? = nil) throws -> String {
        let did = value["drawing_id"].string
        if let did, try purged(did) { return "purged" }
        if let rid = value["record_id"].string, try exists("SELECT 1 FROM draw_records WHERE record_id=?", [.text(rid)]) {
            return "duplicate"
        }
        let record: DrawRecord
        let data: Data
        do {
            record = try DrawRecord.validate(value)
            data = try record.encoded()
        } catch let failure as DrawFormatError { return "rejected:" + failure.code }
        let size = data.count
        let drawing = try self.drawing(record.drawingID)
        if record.kind == "create" {
            let created = try exists("SELECT 1 FROM draw_records WHERE drawing_id=? AND kind='create'", [.text(record.drawingID)])
            if drawing != nil || created {
                return "rejected:invalid_record"
            }
            if try int("SELECT COUNT(*) FROM drawings") >= Int64(DrawSpec.Limit.maxDrawings) { return "rejected:drawings_capacity" }
        } else if let drawing {
            if drawing.recordCount + 1 > DrawSpec.Limit.maxRecords { return "rejected:drawing_too_large" }
            if record.kind == "op" && drawing.opCount + 1 > DrawSpec.Limit.maxOperations { return "rejected:too_many_operations" }
            if record.kind == "op" && drawing.docBytes + size > DrawSpec.Limit.maxDocumentBytes { return "rejected:drawing_too_large" }
        }
        let now = now ?? DrawText.now()
        let seq = try nextSeq()
        let target: Value = record.kind == "visibility" ? .text(record.body["target"].string ?? "") : .null
        try run("INSERT INTO draw_records(seq,record_id,drawing_id,kind,device,lamport,sort_key,target,body,bytes,source,received_at) " +
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                [.int(seq), .text(record.recordID), .text(record.drawingID), .text(record.kind), .text(record.device),
                 .int(record.lamport), .text(record.key.text), target, .text(String(decoding: data, as: UTF8.self)),
                 .int(Int64(size)), .text(source), .text(now)])
        if record.kind == "create" {
            let body = record.body
            let title = body["title"].string ?? ""
            try run("INSERT INTO drawings(drawing_id,title,created_at,updated_at,width,height,background,created_by) VALUES(?,?,?,?,?,?,?,?)",
                    [.text(record.drawingID), .text(title.isEmpty ? Self.defaultTitle : title), .text(body["created_at"].string ?? now),
                     .text(now), .int(body["width"].integer ?? 0), .int(body["height"].integer ?? 0),
                     .text(body["background"].string ?? "#ffffff"), .text(record.device)])
            try rematerialize(record.drawingID, now: now)
        } else if drawing != nil {
            try fold(record, size: size, now: now)
        }
        // Local, monotonic "most recently changed" order for the drawing list.
        try run("UPDATE drawings SET last_seq=? WHERE drawing_id=?", [.int(seq), .text(record.drawingID)])
        return "applied"
    }

    /// Incremental materialization of one new record into an existing drawing.
    private func fold(_ record: DrawRecord, size: Int, now: String) throws {
        let did = record.drawingID, key = record.key.text
        var sets = ["clock=MAX(clock,?)", "record_count=record_count+1", "revision=revision+1", "updated_at=?"]
        var values: [Value] = [.int(record.lamport), .text(now)]
        switch record.kind {
        case "op":
            let op = try DrawOp(json: record.body)
            sets += ["op_count=op_count+1", "doc_bytes=doc_bytes+?", "schema_version=MAX(schema_version,?)"]
            values += [.int(Int64(size)), .int(Int64(op.schema))]
            try resolveVisibility(target: record.recordID, device: record.device)
            if let asset = op.assetID { try want(did, asset, now: now) }
        case "visibility":
            let target = record.body["target"].string ?? ""
            let author = try optionalText("SELECT device FROM draw_records WHERE record_id=?", [.text(target)])
            if author == record.device {
                let current = try optionalText("SELECT key FROM draw_visibility WHERE target=?", [.text(target)])
                if current.map({ Self.greater(key, $0) }) ?? true {
                    try run("INSERT INTO draw_visibility VALUES(?,?,?) ON CONFLICT(target) DO UPDATE SET hidden=excluded.hidden, key=excluded.key",
                            [.text(target), .int(record.body["hidden"].boolean == true ? 1 : 0), .text(key)])
                }
            }
        case "meta":
            guard let row = try drawing(did) else { break }
            let field = record.body["field"].string
            if field == "title" && Self.greater(key, row.titleKey) {
                let title = record.body["value"].string ?? ""
                sets += ["title=?", "title_key=?"]
                values += [.text(title.isEmpty ? Self.defaultTitle : title), .text(key)]
            }
            if field == "trashed" && Self.greater(key, row.trashedKey) {
                let trashed = record.body["value"].boolean == true
                sets += ["trashed=?", "trashed_at=?", "trashed_key=?"]
                values += [.int(trashed ? 1 : 0), .text(trashed ? record.at : ""), .text(key)]
            }
        default:
            break
        }
        try run("UPDATE drawings SET \(sets.joined(separator: ", ")) WHERE drawing_id=?", values + [.text(did)])
    }

    /// Python string comparison of sort keys (code-point order == UTF-8 byte order).
    static func greater(_ a: String, _ b: String) -> Bool { a != b && !a.utf8.lexicographicallyPrecedes(b.utf8) }

    /// Visibility records that arrived before their operation are folded in now.
    private func resolveVisibility(target: String, device: String) throws {
        var latest: (Bool, String)?
        try run("SELECT body, sort_key FROM draw_records WHERE target=? AND kind='visibility' AND device=? ORDER BY sort_key DESC LIMIT 1",
                [.text(target), .text(device)]) { s in
            let body = try? ConnectJSON.decode(Data(Self.text(s, 0).utf8), limit: 4096)
            latest = (body?["body"]["hidden"].boolean == true, Self.text(s, 1))
        }
        if let (hidden, key) = latest {
            try run("INSERT INTO draw_visibility VALUES(?,?,?) ON CONFLICT(target) DO UPDATE SET hidden=excluded.hidden, key=excluded.key",
                    [.text(target), .int(hidden ? 1 : 0), .text(key)])
        }
    }

    /// Recompute a drawing's derived state from its records. The result
    /// depends only on the record set.
    func rematerialize(_ did: String, now: String? = nil) throws {
        struct Row { let recordID: String; let kind: String; let device: String; let lamport: Int64; let body: String; let bytes: Int; let key: String }
        var rows: [Row] = []
        try run("SELECT record_id, kind, device, lamport, body, bytes, sort_key FROM draw_records WHERE drawing_id=? ORDER BY sort_key",
                [.text(did)]) { s in
            rows.append(Row(recordID: Self.text(s, 0), kind: Self.text(s, 1), device: Self.text(s, 2), lamport: sqlite3_column_int64(s, 3),
                            body: Self.text(s, 4), bytes: Int(sqlite3_column_int64(s, 5)), key: Self.text(s, 6)))
        }
        var ops: [String: Row] = [:]
        for row in rows where row.kind == "op" { ops[row.recordID] = row }
        try run("DELETE FROM draw_visibility WHERE target IN (SELECT record_id FROM draw_records WHERE drawing_id=? AND kind='op')", [.text(did)])
        var title: String?, titleKey: String?, trashed = false, trashedKey: String?, trashedAt = ""
        var schema = 1, clock: Int64 = 0, size = 0
        var winners: [String: (String, Bool)] = [:]
        for row in rows {
            clock = max(clock, row.lamport)
            guard let record = try? ConnectJSON.decode(Data(row.body.utf8), limit: DrawSpec.Limit.maxOperationBytes + 1024, allowDecimals: true) else { continue }
            let body = record["body"]
            switch row.kind {
            case "op":
                guard let op = try? DrawOp(json: body) else { continue }
                schema = max(schema, op.schema)
                size += row.bytes
                if let asset = op.assetID { try want(did, asset, now: now ?? DrawText.now()) }
            case "visibility":
                if let target = body["target"].string, let op = ops[target], op.device == row.device {
                    winners[target] = (row.key, body["hidden"].boolean == true)
                }
            case "meta":
                if body["field"].string == "title" { title = body["value"].string; titleKey = row.key }
                else { trashed = body["value"].boolean == true; trashedKey = row.key; trashedAt = trashed ? (record["at"].string ?? "") : "" }
            default: break
            }
        }
        for (target, (key, hidden)) in winners {
            try run("INSERT INTO draw_visibility VALUES(?,?,?)", [.text(target), .int(hidden ? 1 : 0), .text(key)])
        }
        var sets = ["clock=?", "op_count=?", "record_count=?", "doc_bytes=?", "schema_version=?", "revision=revision+1"]
        var values: [Value] = [.int(clock), .int(Int64(ops.count)), .int(Int64(rows.count)), .int(Int64(size)), .int(Int64(schema))]
        if let titleKey {
            let value = title ?? ""
            sets += ["title=?", "title_key=?"]; values += [.text(value.isEmpty ? Self.defaultTitle : value), .text(titleKey)]
        }
        if let trashedKey {
            sets += ["trashed=?", "trashed_at=?", "trashed_key=?"]; values += [.int(trashed ? 1 : 0), .text(trashedAt), .text(trashedKey)]
        }
        if let now { sets.append("updated_at=?"); values.append(.text(now)) }
        try run("UPDATE drawings SET \(sets.joined(separator: ", ")) WHERE drawing_id=?", values + [.text(did)])
    }

    func want(_ did: String, _ assetID: String, now: String) throws {
        if !(try exists("SELECT 1 FROM draw_assets WHERE asset_id=?", [.text(assetID)])) {
            try run("INSERT OR IGNORE INTO draw_wanted VALUES(?,?,?)", [.text(assetID), .text(did), .text(now)])
        }
    }

    /// A new local record with the next Lamport clock value for this drawing.
    func make(device: String, drawingID did: String, kind: String, body: ConnectJSON, recordID: String? = nil,
              lamport: Int64? = nil, at: String? = nil) throws -> ConnectJSON {
        let rid = recordID ?? DrawText.randomID()
        var body = body
        if kind == "op", var fields = body.object { fields["id"] = .string(rid); body = .object(fields) }
        let clock = try drawing(did)?.clock ?? 0
        return .object(["record_id": .string(rid), "drawing_id": .string(did), "device": .string(device),
                        "lamport": .int(lamport ?? clock + 1), "kind": .string(kind), "at": .string(at ?? DrawText.now()), "body": body])
    }

    // MARK: This device's Undo / Redo stacks (local, never synced)

    func push(_ did: String, _ stack: String, _ recordID: String) throws {
        let top = try int("SELECT COALESCE(MAX(pos),0) FROM draw_history WHERE drawing_id=? AND stack=?", [.text(did), .text(stack)])
        try run("INSERT INTO draw_history VALUES(?,?,?,?)", [.text(did), .text(stack), .int(top + 1), .text(recordID)])
        let count = try int("SELECT COUNT(*) FROM draw_history WHERE drawing_id=? AND stack=?", [.text(did), .text(stack)])
        if count > Int64(DrawSpec.Limit.maxUndo) {
            try run("DELETE FROM draw_history WHERE drawing_id=? AND stack=? AND pos IN (SELECT pos FROM draw_history " +
                    "WHERE drawing_id=? AND stack=? ORDER BY pos LIMIT ?)",
                    [.text(did), .text(stack), .text(did), .text(stack), .int(count - Int64(DrawSpec.Limit.maxUndo))])
        }
    }

    func pop(_ did: String, _ stack: String) throws -> String? {
        var found: (Int64, String)?
        try run("SELECT pos, record_id FROM draw_history WHERE drawing_id=? AND stack=? ORDER BY pos DESC LIMIT 1",
                [.text(did), .text(stack)]) { found = (sqlite3_column_int64($0, 0), Self.text($0, 1)) }
        guard let (pos, rid) = found else { return nil }
        try run("DELETE FROM draw_history WHERE drawing_id=? AND stack=? AND pos=?", [.text(did), .text(stack), .int(pos)])
        return rid
    }

    func clearStack(_ did: String, _ stack: String) throws {
        try run("DELETE FROM draw_history WHERE drawing_id=? AND stack=?", [.text(did), .text(stack)])
    }

    func history(_ did: String) throws -> (undo: Int, redo: Int) {
        var counts: [String: Int] = [:]
        try run("SELECT stack, COUNT(*) FROM draw_history WHERE drawing_id=? GROUP BY stack", [.text(did)]) {
            counts[Self.text($0, 0)] = Int(sqlite3_column_int64($0, 1))
        }
        return (counts["undo"] ?? 0, counts["redo"] ?? 0)
    }

    func hidden(_ recordID: String) throws -> Bool {
        try int("SELECT COALESCE(MAX(hidden),0) FROM draw_visibility WHERE target=?", [.text(recordID)]) != 0
    }

    // MARK: Purge (tombstone)

    func purge(_ did: String, device: String, at: String) throws {
        try run("DELETE FROM draw_visibility WHERE target IN (SELECT record_id FROM draw_records WHERE drawing_id=?)", [.text(did)])
        for table in ["draw_records", "draw_history", "draw_thumbnails", "draw_wanted", "drawings"] {
            try run("DELETE FROM \(table) WHERE drawing_id=?", [.text(did)])
        }
        try run("INSERT OR IGNORE INTO draw_purges VALUES(?,?,?,?)", [.text(did), .text(at), .text(device), .int(try nextSeq())])
    }

    // MARK: Records of a drawing

    /// Validated records of a drawing after a feed position, in feed order.
    /// A record that fails validation makes the drawing unreadable (kept for recovery).
    func records(_ did: String, after: Int64, limitBytes: Int) throws -> (records: [DrawRecord], cursor: Int64, more: Bool) {
        var out: [DrawRecord] = [], size = 0, cursor = after, more = false, corrupt = false
        try run("SELECT seq, body FROM draw_records WHERE drawing_id=? AND seq>? ORDER BY seq", [.text(did), .int(after)]) { s in
            guard !more, !corrupt else { return }
            let data = Data(Self.text(s, 1).utf8)
            if !out.isEmpty && size + data.count > limitBytes { more = true; return }
            guard let record = try? DrawRecord.decode(data) else { corrupt = true; return }
            out.append(record); size += data.count; cursor = sqlite3_column_int64(s, 0)
        }
        if corrupt { throw DrawFormatError("drawing_corrupted") }
        return (out, cursor, more)
    }

    func visibleOperations(_ did: String) throws -> [DrawOp] {
        var ops: [DrawOp] = []
        var corrupt = false
        try run("SELECT r.body FROM draw_records r LEFT JOIN draw_visibility v ON v.target=r.record_id " +
                "WHERE r.drawing_id=? AND r.kind='op' AND COALESCE(v.hidden,0)=0 ORDER BY r.sort_key", [.text(did)]) { s in
            guard let record = try? DrawRecord.decode(Data(Self.text(s, 0).utf8)), let op = record.operation else { corrupt = true; return }
            ops.append(op)
        }
        if corrupt { throw DrawFormatError("drawing_corrupted") }
        return ops
    }

    func recordSeq(_ recordID: String) throws -> Int64 { try int("SELECT seq FROM draw_records WHERE record_id=?", [.text(recordID)]) }

    func recordBody(_ recordID: String) throws -> (drawingID: String, device: String, body: String, seq: Int64)? {
        var found: (String, String, String, Int64)?
        try run("SELECT drawing_id, device, body, seq FROM draw_records WHERE record_id=?", [.text(recordID)]) {
            found = (Self.text($0, 0), Self.text($0, 1), Self.text($0, 2), sqlite3_column_int64($0, 3))
        }
        return found.map { (drawingID: $0.0, device: $0.1, body: $0.2, seq: $0.3) }
    }

    func missingAssets(_ did: String) throws -> [String] {
        var ids: [String] = []
        try run("SELECT asset_id FROM draw_wanted WHERE drawing_id=? LIMIT 64", [.text(did)]) { ids.append(Self.text($0, 0)) }
        return ids
    }

    // MARK: Assets

    struct AssetInfo: Equatable, Sendable { let assetID: String; let mime: String; let width: Int; let height: Int; let size: Int }

    func assetInfo(_ id: String) throws -> AssetInfo? {
        var info: AssetInfo?
        try run("SELECT asset_id, mime, width, height, size FROM draw_assets WHERE asset_id=?", [.text(id)]) { s in
            info = AssetInfo(assetID: Self.text(s, 0), mime: Self.text(s, 1), width: Int(sqlite3_column_int64(s, 2)),
                             height: Int(sqlite3_column_int64(s, 3)), size: Int(sqlite3_column_int64(s, 4)))
        }
        return info
    }

    func assetData(_ id: String) throws -> (AssetInfo, Data)? {
        var found: (AssetInfo, Data)?
        try run("SELECT asset_id, mime, width, height, size, data FROM draw_assets WHERE asset_id=?", [.text(id)]) { s in
            found = (AssetInfo(assetID: Self.text(s, 0), mime: Self.text(s, 1), width: Int(sqlite3_column_int64(s, 2)),
                               height: Int(sqlite3_column_int64(s, 3)), size: Int(sqlite3_column_int64(s, 4))), Self.blob(s, 5))
        }
        return found
    }

    /// Stores already-validated asset bytes (content-addressed; stored once).
    func putAsset(_ info: AssetInfo, data: Data, origin: String) throws {
        if !(try exists("SELECT 1 FROM draw_assets WHERE asset_id=?", [.text(info.assetID)])) {
            try run("INSERT INTO draw_assets VALUES(?,?,?,?,?,?,?,?)",
                    [.text(info.assetID), .text(info.mime), .int(Int64(info.width)), .int(Int64(info.height)),
                     .int(Int64(data.count)), .blob(data), .text(DrawText.now()), .text(origin)])
        }
        try run("DELETE FROM draw_wanted WHERE asset_id=?", [.text(info.assetID)])
    }

    func wanted(limit: Int) throws -> [String] {
        var ids: [String] = []
        try run("SELECT asset_id FROM draw_wanted ORDER BY since, asset_id LIMIT ?", [.int(Int64(limit))]) { ids.append(Self.text($0, 0)) }
        return ids
    }

    // MARK: Thumbnails (local cache, never synced)

    func putThumbnail(_ did: String, revision: Int, mime: String, image: Data) throws -> Bool {
        guard try drawing(did) != nil else { return false }
        if let current = try optionalText("SELECT revision FROM draw_thumbnails WHERE drawing_id=?", [.text(did)]),
           let value = Int(current), value > revision { return false }
        try run("INSERT INTO draw_thumbnails VALUES(?,?,?,?,?) ON CONFLICT(drawing_id) DO UPDATE SET " +
                "revision=excluded.revision, mime=excluded.mime, image=excluded.image, created_at=excluded.created_at",
                [.text(did), .int(Int64(revision)), .text(mime), .blob(image), .text(DrawText.now())])
        return true
    }

    func thumbnail(_ did: String) throws -> (revision: Int, image: Data)? {
        var found: (Int, Data)?
        try run("SELECT revision, image FROM draw_thumbnails WHERE drawing_id=?", [.text(did)]) {
            found = (Int(sqlite3_column_int64($0, 0)), Self.blob($0, 1))
        }
        return found.map { (revision: $0.0, image: $0.1) }
    }
}
