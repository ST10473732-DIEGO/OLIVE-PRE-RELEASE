import Foundation
import SQLite3

/// Public, content-free summary of one drawing (library rows, editor header).
struct DrawSummary: Identifiable, Equatable, Sendable {
    let id: String
    let title: String
    let createdAt: String
    let updatedAt: String
    let width: Int
    let height: Int
    let background: String
    let schemaVersion: Int
    let revision: Int
    let opCount: Int
    let bytes: Int
    let trashed: Bool
    let trashedAt: String
    /// "ok", "unsupported" (made by a newer OLIVE) or "corrupt".
    let status: String
    let thumbnailRevision: Int?
    let lastSeq: Int64

    init(_ row: DrawingRow, thumbnail: Int?) {
        id = row.drawingID; title = row.title.isEmpty ? DrawStore.defaultTitle : row.title
        createdAt = row.createdAt; updatedAt = row.updatedAt; width = row.width; height = row.height
        background = row.background; schemaVersion = row.schemaVersion; revision = row.revision
        opCount = row.opCount; bytes = row.docBytes; trashed = row.trashed; trashedAt = row.trashedAt
        status = row.schemaVersion > DrawSpec.schemaVersion ? "unsupported" : row.status
        thumbnailRevision = thumbnail; lastSeq = row.lastSeq
    }
}

/// One page of a drawing's records for an open editor (service.py `since`).
struct DrawPage: Sendable {
    let drawing: DrawSummary
    let records: [DrawRecord]
    let cursor: Int64
    let more: Bool
    let undo: Int
    let redo: Int
    let missingAssets: [String]
}

struct DrawEdit: Sendable {
    let record: DrawRecord?
    let cursor: Int64?
    let undo: Int
    let redo: Int
}

/// Local change notifications (drawing id or nil for library-wide, reason, source peer).
struct DrawEvent: Sendable, Equatable {
    enum Kind: String, Sendable { case records, changed, asset, purged }
    let kind: Kind
    let drawingID: String?
    let reason: String?
    let peer: String?
    let assetID: String?
}

/// User-facing, content-free Draw errors (service.py MESSAGES).
struct DrawError: Error, Equatable, LocalizedError {
    let code: String
    init(_ code: String) { self.code = code }
    var errorDescription: String? { Self.messages[code] ?? "Could not save drawing." }
    static let messages: [String: String] = [
        "draw_unavailable": "Drawing storage unavailable. Your drawings were left untouched.",
        "draw_storage_unavailable": "Drawing storage unavailable. Your drawings were left untouched.",
        "draw_storage_newer": "Drawing storage was created by a newer OLIVE. It was left untouched.",
        "draw_storage_unrecognized": "Drawing storage unavailable: the database was not recognised and was left untouched.",
        "drawing_not_found": "That drawing no longer exists.",
        "drawing_purged": "That drawing was permanently deleted.",
        "drawing_unsupported": "Drawing format unsupported. It was made by a newer OLIVE and was left untouched.",
        "drawing_corrupted": "Could not load drawing. The stored data was kept for recovery.",
        "canvas_too_large": "Canvas too large. Drawings can be up to 8192 pixels on a side and 33.5 million pixels in total.",
        "invalid_canvas": "Canvas too small or invalid. Use whole pixels between 16 and 8192.",
        "invalid_background": "Choose a white or transparent background.",
        "invalid_title": "Drawing titles are plain text.",
        "invalid_operation": "Could not save drawing: an edit was malformed.",
        "invalid_record": "Could not save drawing: an edit was malformed.",
        "drawing_too_large": "Could not save drawing: it reached its size limit. Start a new drawing or clear this one.",
        "too_many_operations": "Could not save drawing: it reached 20,000 edits. Start a new drawing or clear this one.",
        "drawings_capacity": "Drawing limit reached. Delete drawings you no longer need.",
        "in_trash": "This drawing is in Recently Deleted. Restore it to edit it.",
        "not_in_trash": "Move the drawing to Recently Deleted before deleting it permanently.",
        "invalid_image": "Could not import image: the file is not a valid PNG or JPEG image.",
        "unsupported_image": "Could not import image: only PNG, JPEG and iPhone photos can be imported.",
        "image_too_large": "Could not import image: it is too large. Images can be up to 8192 pixels on a side, 33.5 million pixels and 48 MB.",
        "checksum_mismatch": "Could not import image: the data did not arrive intact.",
        "asset_not_found": "That image is not available on this phone yet.",
    ]
}

/// The one owner of OLIVE Draw data on the phone: library, edits, local-origin
/// Undo/Redo, image assets and the olive-draw/1 sync engine. All SQLite access
/// is serialized by this actor; every change is one transaction and is durable
/// before the call returns (network acknowledgement is never awaited for that).
///
/// Logs are content-free: ids, counts, sizes and error categories only.
actor DrawEngine {
    private var store: DrawStore?
    nonisolated let unavailable: DrawStorageError?
    private(set) var deviceID: String
    private var listener: (@Sendable (DrawEvent) -> Void)?
    // Sync (transient, per process): peer status, receiver-side staged transfers,
    // and ids a peer refused (never retried in a loop).
    private struct Staging { var fixed: [String: ConnectJSON]; var parts: [Int64: Data]; var size: Int; var expires: ContinuousClock.Instant; var total: Int }
    private var transfers: [String: Staging] = [:]
    private var refused: [String: [String: String]] = [:]
    private var pumping = Set<String>()

    init(directory: URL, deviceID: String) {
        self.deviceID = deviceID
        do { store = try DrawStore(directory: directory); unavailable = nil }
        catch let failure as DrawStorageError { store = nil; unavailable = failure }
        catch { store = nil; unavailable = .unavailable }
    }

    func setListener(_ listener: (@Sendable (DrawEvent) -> Void)?) { self.listener = listener }
    /// The Connect identity appeared (or changed): new records are made by it.
    func setDevice(_ id: String) { if DrawText.isUUID(id) { deviceID = id } }
    var available: Bool { store != nil }
    var storeURL: URL? { store?.url }

    private func require() throws -> DrawStore {
        guard let store else { throw DrawError(unavailable?.code ?? "draw_unavailable") }
        return store
    }

    private func emit(_ kind: DrawEvent.Kind, _ did: String?, reason: String? = nil, peer: String? = nil, asset: String? = nil) {
        listener?(DrawEvent(kind: kind, drawingID: did, reason: reason, peer: peer, assetID: asset))
    }

    private func checkDrawing(_ did: String) throws -> String {
        guard DrawText.isUUID(did), UUID(uuidString: did)?.uuidString.lowercased() == did else { throw DrawError("drawing_not_found") }
        return did
    }

    private func row(_ store: DrawStore, _ did: String) throws -> DrawingRow {
        guard let row = try store.drawing(did) else { throw DrawError(try store.purged(did) ? "drawing_purged" : "drawing_not_found") }
        return row
    }

    private func editable(_ store: DrawStore, _ did: String) throws -> DrawingRow {
        let row = try row(store, did)
        if row.schemaVersion > DrawSpec.schemaVersion { throw DrawError("drawing_unsupported") }
        if row.status != "ok" { throw DrawError("drawing_corrupted") }
        return row
    }

    private func described(_ store: DrawStore, _ row: DrawingRow) throws -> DrawSummary {
        DrawSummary(row, thumbnail: try store.thumbnail(row.drawingID)?.revision)
    }

    /// Make and insert one record by this device; the caller's transaction commits it.
    @discardableResult
    private func local(_ store: DrawStore, _ did: String, _ kind: String, _ body: ConnectJSON, recordID: String? = nil,
                       device: String? = nil) throws -> (DrawRecord, Int64) {
        let value = try store.make(device: device ?? deviceID, drawingID: did, kind: kind, body: body, recordID: recordID)
        let status = try store.insert(value)
        guard status == "applied" else {
            let code = status.hasPrefix("rejected:") ? String(status.dropFirst(9)) : status == "purged" ? "drawing_purged" : "invalid_record"
            throw DrawError(Self.formatCode(code))
        }
        return (try DrawRecord.validate(value), try store.recordSeq(value["record_id"].string ?? ""))
    }

    private static func formatCode(_ code: String) -> String {
        ["invalid_number": "invalid_operation", "invalid_points": "invalid_operation", "unsupported_operation": "invalid_operation",
         "operation_too_large": "invalid_operation", "invalid_record": "invalid_operation"][code] ?? code
    }

    private func wrap<T>(_ body: () throws -> T) throws -> T {
        do { return try body() }
        catch let error as DrawError { throw error }
        catch let error as DrawFormatError { throw DrawError(Self.formatCode(error.code)) }
        catch { throw DrawError("draw_unavailable") }
    }

    // MARK: Library

    func list(trash: Bool) throws -> [DrawSummary] {
        try wrap { try require().drawings(trashed: trash).map { DrawSummary($0.0, thumbnail: $0.1) } }
    }

    func counts() throws -> (drawings: Int, trash: Int) {
        try wrap {
            let store = try require()
            return (Int(try store.int("SELECT COUNT(*) FROM drawings WHERE trashed=0")), Int(try store.int("SELECT COUNT(*) FROM drawings WHERE trashed=1")))
        }
    }

    func summary(_ did: String) throws -> DrawSummary {
        try wrap { let store = try require(); return try described(store, try row(store, try checkDrawing(did))) }
    }

    func create(title: String = "", width: Int = 1920, height: Int = 1080, background: String = "#ffffff") throws -> DrawSummary {
        let did = UUID().uuidString.lowercased()
        let summary = try wrap {
            let store = try require()
            try DrawCanvas.validate(width: width, height: height)
            guard DrawSpec.backgrounds.contains(background) else { throw DrawError("invalid_background") }
            let clean = DrawText.cleanTitle(title)
            let now = DrawText.now()
            return try store.transaction {
                if try store.int("SELECT COUNT(*) FROM drawings") >= Int64(DrawSpec.Limit.maxDrawings) { throw DrawError("drawings_capacity") }
                try local(store, did, "create", .object(["width": .int(Int64(width)), "height": .int(Int64(height)),
                    "background": .string(background), "title": .string(clean.isEmpty ? DrawStore.defaultTitle : clean), "created_at": .string(now)]))
                return try described(store, try row(store, did))
            }
        }
        emit(.changed, did, reason: "created")
        return summary
    }

    private func meta(_ did: String, _ field: String, _ value: ConnectJSON, reason: String) throws -> DrawSummary {
        let did = try checkDrawing(did)
        let summary = try wrap {
            let store = try require()
            return try store.transaction {
                _ = try row(store, did)
                try local(store, did, "meta", .object(["field": .string(field), "value": value]))
                return try described(store, try row(store, did))
            }
        }
        emit(.changed, did, reason: reason)
        return summary
    }

    func rename(_ did: String, title: String) throws -> DrawSummary {
        let clean = DrawText.cleanTitle(title)
        return try meta(did, "title", .string(clean.isEmpty ? DrawStore.defaultTitle : clean), reason: "renamed")
    }
    func trash(_ did: String) throws -> DrawSummary { try meta(did, "trashed", .bool(true), reason: "trashed") }
    func restore(_ did: String) throws -> DrawSummary { try meta(did, "trashed", .bool(false), reason: "restored") }

    /// A new drawing (new id) with copies of the visible operations, in order.
    /// Image operations keep the same asset id: bytes are never duplicated.
    func duplicate(_ did: String) throws -> DrawSummary {
        let did = try checkDrawing(did)
        let copy = UUID().uuidString.lowercased()
        let summary = try wrap {
            let store = try require()
            return try store.transaction {
                let source = try editable(store, did)
                if try store.int("SELECT COUNT(*) FROM drawings") >= Int64(DrawSpec.Limit.maxDrawings) { throw DrawError("drawings_capacity") }
                let title = String(String.UnicodeScalarView((source.title + " (copy)").unicodeScalars.prefix(DrawSpec.Limit.maxTitleChars)))
                let now = DrawText.now()
                try local(store, copy, "create", .object(["width": .int(Int64(source.width)), "height": .int(Int64(source.height)),
                    "background": .string(source.background), "title": .string(DrawText.cleanTitle(title)), "created_at": .string(now)]))
                for op in try store.visibleOperations(did) {
                    let id = DrawText.randomID()
                    let (record, _) = try local(store, copy, "op", op.with(id: id).json, recordID: id)
                    try store.push(copy, "undo", record.recordID)
                }
                try store.run("INSERT INTO draw_thumbnails(drawing_id,revision,mime,image,created_at) SELECT ?, " +
                              "(SELECT revision FROM drawings WHERE drawing_id=?), mime, image, ? FROM draw_thumbnails WHERE drawing_id=?",
                              [.text(copy), .text(copy), .text(now), .text(did)])
                return try described(store, try row(store, copy))
            }
        }
        emit(.changed, copy, reason: "duplicated")
        return summary
    }

    /// Permanent deletion, only from Recently Deleted. A tombstone stays so a
    /// stale peer can never bring the drawing back.
    func purge(_ did: String) throws {
        let did = try checkDrawing(did)
        try wrap {
            let store = try require()
            try store.transaction {
                guard try row(store, did).trashed else { throw DrawError("not_in_trash") }
                try store.purge(did, device: deviceID, at: DrawText.now())
            }
        }
        emit(.purged, did, reason: "purged")
    }

    func isPurged(_ did: String) throws -> Bool { try wrap { try require().purged(did) } }

    // MARK: Document

    /// Records of one drawing after a feed position, a page at a time.
    func since(_ did: String, after: Int64 = 0) throws -> DrawPage {
        let did = try checkDrawing(did)
        return try wrap {
            let store = try require()
            let row = try row(store, did)
            if row.schemaVersion > DrawSpec.schemaVersion { throw DrawError("drawing_unsupported") }
            if row.status != "ok" { throw DrawError("drawing_corrupted") }
            let page = try store.records(did, after: after, limitBytes: 600_000)
            var cursor = page.cursor
            if !page.more { cursor = max(cursor, try store.int("SELECT COALESCE(MAX(seq),0) FROM draw_records WHERE drawing_id=?", [.text(did)])) }
            let history = try store.history(did)
            return DrawPage(drawing: try described(store, row), records: page.records, cursor: max(cursor, after), more: page.more,
                            undo: history.undo, redo: history.redo, missingAssets: try store.missingAssets(did))
        }
    }

    func visibleOperations(_ did: String) throws -> [DrawOp] {
        let did = try checkDrawing(did)
        return try wrap { let store = try require(); _ = try row(store, did); return try store.visibleOperations(did) }
    }

    /// One completed local edit. `op.id` is 128 random bits chosen by the
    /// editor, so a retried call is recognised and not applied twice.
    func append(_ did: String, _ op: DrawOp) throws -> DrawEdit {
        let did = try checkDrawing(did)
        guard DrawText.isRecordID(op.id) else { throw DrawError("invalid_operation") }
        let edit: DrawEdit = try wrap {
            _ = try DrawOp(json: op.json)
            let store = try require()
            return try store.transaction {
                let drawing = try editable(store, did)
                var record: DrawRecord, seq: Int64
                if let existing = try store.recordBody(op.id) {
                    guard existing.drawingID == did else { throw DrawError("invalid_operation") }
                    record = try DrawRecord.decode(Data(existing.body.utf8)); seq = existing.seq
                } else {
                    if drawing.trashed { throw DrawError("in_trash") }
                    (record, seq) = try local(store, did, "op", op.json, recordID: op.id)
                    try store.push(did, "undo", record.recordID)
                    try store.clearStack(did, "redo")
                }
                let history = try store.history(did)
                return DrawEdit(record: record, cursor: seq, undo: history.undo, redo: history.redo)
            }
        }
        emit(.records, did)
        return edit
    }

    private func step(_ did: String, from source: String, to target: String, hidden: Bool) throws -> DrawEdit {
        let did = try checkDrawing(did)
        let edit: DrawEdit = try wrap {
            let store = try require()
            return try store.transaction {
                let drawing = try editable(store, did)
                if drawing.trashed { throw DrawError("in_trash") }
                var result: (DrawRecord, Int64)?
                while let id = try store.pop(did, source) {
                    // The target is this device's own edit; the visibility record is made
                    // by the same device id that made it (only the author may hide it).
                    guard let op = try store.recordBody(id), op.drawingID == did,
                          try store.exists("SELECT 1 FROM draw_records WHERE record_id=? AND kind='op'", [.text(id)]),
                          try store.hidden(id) != hidden else { continue }   // Already undone/redone elsewhere: skip it.
                    result = try local(store, did, "visibility", .object(["target": .string(id), "hidden": .bool(hidden)]), device: op.device)
                    try store.push(did, target, id)
                    break
                }
                let history = try store.history(did)
                return DrawEdit(record: result?.0, cursor: result?.1, undo: history.undo, redo: history.redo)
            }
        }
        if edit.record != nil { emit(.records, did) }
        return edit
    }

    /// Undo this device's latest visible edit (never another device's).
    func undo(_ did: String) throws -> DrawEdit { try step(did, from: "undo", to: "redo", hidden: true) }
    func redo(_ did: String) throws -> DrawEdit { try step(did, from: "redo", to: "undo", hidden: false) }
    func history(_ did: String) throws -> (undo: Int, redo: Int) { try wrap { try require().history(try checkDrawing(did)) } }

    // MARK: Assets and thumbnails

    func assetInfo(_ id: String) throws -> DrawStore.AssetInfo? { try wrap { try require().assetInfo(id) } }
    func assetData(_ id: String) throws -> Data? { try wrap { try require().assetData(id)?.1 } }

    /// Validate and keep one image (content-addressed: the same bytes are stored once).
    @discardableResult
    func storeAsset(_ data: Data, origin: String = "local", expectedID: String? = nil) throws -> DrawStore.AssetInfo {
        let info: DrawAssets.Info
        do { info = try DrawAssets.validate(data, expectedID: expectedID) }
        catch let failure as DrawAssets.Failure { throw DrawError(failure.code) }
        let stored = DrawStore.AssetInfo(assetID: info.assetID, mime: info.mime, width: info.width, height: info.height, size: data.count)
        try wrap { let store = try require(); try store.transaction { try store.putAsset(stored, data: data, origin: origin) } }
        emit(.asset, nil, asset: info.assetID)
        return stored
    }

    /// Stores a canonical imported image and appends its image operation.
    func addImage(_ did: String, _ imported: DrawAssets.Imported) throws -> DrawEdit {
        try storeAsset(imported.data, origin: "local", expectedID: imported.info.assetID)
        let op = DrawOp.image(id: DrawText.randomID(), assetID: imported.info.assetID, x: imported.x, y: imported.y,
                              width: Double(imported.width), height: Double(imported.height), opacity: 1)
        return try append(did, op)
    }

    func putThumbnail(_ did: String, revision: Int, mime: String, image: Data) throws {
        guard image.count <= DrawSpec.Limit.thumbnailMaxBytes else { return }
        try wrap { let store = try require(); _ = try store.transaction { try store.putThumbnail(did, revision: revision, mime: mime, image: image) } }
    }

    func thumbnail(_ did: String) throws -> (revision: Int, image: Data)? { try wrap { try require().thumbnail(did) } }

    // MARK: Sync (olive-draw/1 engine; sync_engine.py)

    struct PeerRecord: Sendable, Equatable { var ackedSeq: Int64; var peerEpoch: String?; var lastSync: String?; var lastError: String? }

    func epoch() throws -> String { try wrap { try require().meta("epoch") ?? "" } }

    func peer(_ peer: String) throws -> PeerRecord {
        try wrap {
            var record = PeerRecord(ackedSeq: 0, peerEpoch: nil, lastSync: nil, lastError: nil)
            try require().run("SELECT acked_seq, peer_epoch, last_sync, last_error FROM draw_peers WHERE device_id=?", [.text(peer)]) { s in
                record = PeerRecord(ackedSeq: sqlite3_column_int64(s, 0), peerEpoch: DrawStore.isNull(s, 1) ? nil : DrawStore.text(s, 1),
                                    lastSync: DrawStore.isNull(s, 2) ? nil : DrawStore.text(s, 2), lastError: DrawStore.isNull(s, 3) ? nil : DrawStore.text(s, 3))
            }
            return record
        }
    }

    private func savePeer(_ peer: String, _ values: [String: DrawStore.Value]) throws {
        let store = try require()
        try store.transaction {
            try store.run("INSERT OR IGNORE INTO draw_peers(device_id) VALUES(?)", [.text(peer)])
            for (key, value) in values {
                guard ["acked_seq", "peer_epoch", "last_sync", "last_error", "protocol"].contains(key) else { throw DrawError("draw_unavailable") }
                try store.run("UPDATE draw_peers SET \(key)=? WHERE device_id=?", [value, .text(peer)])
            }
        }
    }

    /// A changed peer epoch means its store was replaced (restore/reinstall):
    /// it may lack what it once confirmed, so offer everything again.
    @discardableResult
    private func observeEpoch(_ peer: String, _ epoch: String) throws -> Bool {
        let stored = try self.peer(peer)
        guard stored.peerEpoch != epoch else { return false }
        if stored.peerEpoch != nil {
            let store = try require()
            try store.transaction {
                try store.run("UPDATE draw_peers SET acked_seq=0 WHERE device_id=?", [.text(peer)])
                try store.run("UPDATE draw_records SET source='' WHERE source=?", [.text(peer)])
            }
        }
        try savePeer(peer, ["peer_epoch": .text(epoch), "protocol": .text(DrawProtocol.name)])
        return true
    }

    func wants() throws -> [String] { try wrap { try require().wanted(limit: DrawProtocol.Limit.maxWants) } }

    /// Answer one authenticated, authorized olive-draw/1 request from `peer`.
    func handle(peer: String, request: DrawProtocol.Request) throws -> ConnectJSON {
        guard store != nil else { throw DrawProtocol.Failure("draw_unavailable") }
        do {
            let epoch = try self.epoch()
            let arguments = request.arguments
            if request.operation == "hello" {
                guard arguments["versions"].array?.contains(.string(DrawProtocol.name)) == true else { throw DrawProtocol.Failure("unsupported_protocol") }
                return .object(["versions": .array([.string(DrawProtocol.name)]), "epoch": .string(epoch),
                                "schemas": .array(DrawProtocol.documentSchemas.map { .int($0) }), "wants": .array(try wants().map { .string($0) })])
            }
            try observeEpoch(peer, arguments["epoch"].string ?? "")
            if request.operation == "sync" {
                let results = try receiveEntries(peer, arguments["entries"].array ?? [])
                return .object(["epoch": .string(epoch), "results": .array(results), "wants": .array(try wants().map { .string($0) })])
            }
            var result = try receiveChunk(peer, request)
            result["epoch"] = .string(epoch)
            return .object(result)
        } catch let failure as DrawProtocol.Failure { throw failure }
        catch { throw DrawProtocol.Failure("draw_unavailable") }
    }

    private func receiveEntries(_ peer: String, _ entries: [ConnectJSON]) throws -> [ConnectJSON] {
        let store = try require()
        var results: [ConnectJSON] = [], touched = Set<String>(), listed = Set<String>(), purged = Set<String>()
        let now = DrawText.now()
        try store.transaction {
            for entry in entries {
                if entry.object?["purge"] != nil {
                    let purge = entry["purge"]
                    let did = purge["drawing_id"].string ?? ""
                    if try store.purged(did) { results.append(.object(["status": .string("duplicate")])); continue }
                    try store.purge(did, device: purge["device"].string ?? peer, at: purge["at"].string ?? now)
                    results.append(.object(["status": .string("applied")]))
                    purged.insert(did)
                    continue
                }
                let record = entry["record"]
                let status = try store.insert(record, source: peer, now: now)
                if status.hasPrefix("rejected") {
                    let code = String(status.dropFirst("rejected:".count))
                    let error = ["invalid_record", "drawing_too_large", "too_many_operations", "drawings_capacity"].contains(code) ? code : "invalid_record"
                    results.append(.object(["status": .string("rejected"), "error": .string(error)]))
                    continue
                }
                results.append(.object(["status": .string(status)]))
                if status == "applied", let did = record["drawing_id"].string {
                    touched.insert(did)
                    if ["create", "meta"].contains(record["kind"].string ?? "") { listed.insert(did) }
                }
            }
        }
        for did in touched { emit(.records, did, reason: listed.contains(did) ? "remote" : nil, peer: peer) }
        for did in purged { emit(.purged, did, reason: "purged", peer: peer) }
        return results
    }

    private func receiveChunk(_ peer: String, _ request: DrawProtocol.Request) throws -> [String: ConnectJSON] {
        let now = ContinuousClock.now
        transfers = transfers.filter { $0.value.expires > now }
        let a = request.arguments
        let key = peer + " " + (a["transfer_id"].string ?? "")
        let fixedKeys = ["asset_id", "mime", "width", "height", "total_bytes", "count"]
        let fixed = Dictionary(uniqueKeysWithValues: fixedKeys.map { ($0, a[$0]) })
        guard let data = request.data, let index = a["index"].integer, let total = a["total_bytes"].integer,
              let count = a["count"].integer, let assetID = a["asset_id"].string else { throw DrawProtocol.Failure("malformed_message") }
        var staging: Staging
        if let existing = transfers[key] {
            guard existing.fixed == fixed else { transfers.removeValue(forKey: key); throw DrawProtocol.Failure("malformed_message") }
            staging = existing
        } else {
            if try assetInfo(assetID) != nil { return ["status": .string("exists")] }
            let mine = transfers.filter { $0.key.hasPrefix(peer + " ") }.map(\.value)
            if mine.count >= DrawProtocol.Limit.maxAssetTransfersPerPeer ||
                mine.reduce(0, { $0 + $1.total }) + Int(total) > DrawProtocol.Limit.maxStagedBytesPerPeer {
                throw DrawProtocol.Failure("busy")
            }
            staging = Staging(fixed: fixed, parts: [:], size: 0, expires: now, total: Int(total))
        }
        staging.expires = now.advanced(by: .seconds(DrawProtocol.Limit.transferIdleSeconds))
        if staging.parts[index] == nil { staging.parts[index] = data; staging.size += data.count }
        if staging.size > staging.total { transfers.removeValue(forKey: key); throw DrawProtocol.Failure("payload_too_large") }
        if Int64(staging.parts.count) < count { transfers[key] = staging; return ["status": .string("partial")] }
        transfers.removeValue(forKey: key)
        var payload = Data(capacity: staging.size)
        for i in 0..<count { payload.append(staging.parts[i] ?? Data()) }
        guard payload.count == staging.total, DrawText.sha256(payload) == assetID else {
            return ["status": .string("rejected"), "error": .string("checksum_mismatch")]
        }
        let info: DrawStore.AssetInfo
        do { info = try storeAsset(payload, origin: "peer", expectedID: assetID) }
        catch { return ["status": .string("rejected"), "error": .string("invalid_image")] }
        guard .string(info.mime) == a["mime"], .int(Int64(info.width)) == a["width"], .int(Int64(info.height)) == a["height"] else {
            return ["status": .string("rejected"), "error": .string("invalid_image")]
        }
        return ["status": .string("stored")]
    }

    /// Asset chunks staged for a peer (receiver side), for diagnostics/tests.
    var stagedTransfers: Int { transfers.count }

    /// Push this phone's pending feed (and wanted assets) to `peer`.
    /// `send(operation, arguments)` performs one request and returns the
    /// peer's completed result, or throws. Returns "synced" or "partial".
    func pump(peer: String, hello: Bool, send: @Sendable (String, ConnectJSON) async throws -> ConnectJSON,
              keepGoing: @Sendable () async -> Bool = { true }) async throws -> String {
        guard !pumping.contains(peer) else { return "partial" }
        pumping.insert(peer)
        defer { pumping.remove(peer) }
        if hello {
            let result = try DrawProtocol.helloResult(try await send("hello", .object([
                "versions": .array([.string(DrawProtocol.name)]), "schemas": .array(DrawProtocol.documentSchemas.map { .int($0) })])))
            guard result.versions.contains(DrawProtocol.name) else { throw DrawProtocol.Failure("unsupported_protocol") }
            try observeEpoch(peer, result.epoch)
            try await serveAssets(peer, result.wants, send: send, keepGoing: keepGoing)
        }
        for _ in 0..<DrawProtocol.Limit.maxRoundsPerPump {
            guard await keepGoing() else { return "partial" }
            guard let batch = try prepare(peer) else {
                try savePeer(peer, ["last_sync": .text(DrawText.now()), "last_error": .null])
                return "synced"
            }
            if batch.entries.isEmpty { try savePeer(peer, ["acked_seq": .int(batch.last)]); continue }   // Only echo-suppressed entries.
            let arguments = ConnectJSON.object(["epoch": .string(try epoch()), "entries": .array(batch.entries)])
            let result = try DrawProtocol.syncResult(try await send("sync", arguments), entries: batch.entries.count)
            if try observeEpoch(peer, result.epoch), try self.peer(peer).ackedSeq == 0 { continue }  // Peer store changed identity.
            try process(peer, batch: batch, results: result.results)
            try await serveAssets(peer, result.wants, send: send, keepGoing: keepGoing)
        }
        return "partial"
    }

    private struct Batch { let entries: [ConnectJSON]; let last: Int64 }

    private func prepare(_ peer: String) throws -> Batch? {
        let store = try require()
        let acked = try self.peer(peer).ackedSeq
        var entries: [ConnectJSON] = [], last = acked, size = 0, full = false
        try store.run("SELECT seq, 'record' AS kind, body, source, bytes FROM draw_records WHERE seq>? " +
                      "UNION ALL SELECT seq, 'purge', drawing_id || ' ' || purged_at || ' ' || device, '', 64 FROM draw_purges WHERE seq>? " +
                      "ORDER BY seq LIMIT ?", [.int(acked), .int(acked), .int(Int64(DrawProtocol.Limit.maxEntries))]) { s in
            guard !full else { return }
            let seq = sqlite3_column_int64(s, 0), bytes = Int(sqlite3_column_int64(s, 4))
            if !entries.isEmpty && size + bytes > DrawProtocol.Limit.maxRequestBytes { full = true; return }
            last = seq
            if DrawStore.text(s, 1) == "purge" {
                let parts = DrawStore.text(s, 2).split(separator: " ").map(String.init)
                guard parts.count == 3 else { return }
                entries.append(.object(["seq": .int(seq), "purge": .object(["drawing_id": .string(parts[0]), "at": .string(parts[1]), "device": .string(parts[2])])]))
                size += 64
                return
            }
            if DrawStore.text(s, 3) == peer { return }   // Came from this peer: never echo it back.
            // Unreadable or invalid local data is kept, never sent.
            guard let record = try? DrawRecord.decode(Data(DrawStore.text(s, 2).utf8)) else { return }
            entries.append(.object(["seq": .int(seq), "record": record.json]))
            size += bytes
        }
        return last == acked ? nil : Batch(entries: entries, last: last)
    }

    private func process(_ peer: String, batch: Batch, results: [(status: String, error: String?)]) throws {
        let store = try require()
        for (entry, row) in zip(batch.entries, results) {
            guard entry.object?["record"] != nil else { continue }
            let record = entry["record"]
            if row.status == "purged", let did = record["drawing_id"].string {
                // The peer holds a tombstone: this drawing was permanently deleted.
                let purgedNow: Bool = try store.transaction {
                    guard !(try store.purged(did)) else { return false }
                    try store.purge(did, device: peer, at: DrawText.now())
                    return true
                }
                if purgedNow { emit(.purged, did, reason: "purged", peer: peer) }
            } else if row.status == "rejected", let id = record["record_id"].string {
                refused[peer, default: [:]][id] = row.error ?? "invalid_record"   // Never block every later change.
            }
        }
        try savePeer(peer, ["acked_seq": .int(batch.last), "last_error": .null])
    }

    private func serveAssets(_ peer: String, _ wants: [String], send: @Sendable (String, ConnectJSON) async throws -> ConnectJSON,
                             keepGoing: @Sendable () async -> Bool) async throws {
        for assetID in wants {
            guard await keepGoing(), refused[peer]?[assetID] == nil else { continue }
            guard let (info, data) = try require().assetData(assetID) else { continue }   // Not here either.
            let size = DrawProtocol.Limit.assetChunkBytes
            let count = (data.count + size - 1) / size
            let base: [String: ConnectJSON] = ["epoch": .string(try epoch()), "transfer_id": .string(UUID().uuidString.lowercased()),
                "asset_id": .string(assetID), "mime": .string(info.mime), "width": .int(Int64(info.width)), "height": .int(Int64(info.height)),
                "total_bytes": .int(Int64(data.count)), "count": .int(Int64(count))]
            for index in 0..<count {
                var arguments = base
                arguments["index"] = .int(Int64(index))
                arguments["data"] = .string(data.subdata(in: (index * size)..<min(data.count, (index + 1) * size)).base64EncodedString())
                let result = try DrawProtocol.assetResult(try await send("asset", .object(arguments)))
                if ["exists", "stored"].contains(result.status) { break }
                if result.status == "rejected" { refused[peer, default: [:]][assetID] = result.error ?? "invalid_image"; break }
            }
        }
    }

    /// Records (and tombstones) not yet confirmed by `peer`.
    func pending(_ peer: String) throws -> Int {
        try wrap {
            let store = try require()
            let acked = try self.peer(peer).ackedSeq
            return Int(try store.int("SELECT COUNT(*) FROM draw_records WHERE seq>? AND source!=?", [.int(acked), .text(peer)])
                       + store.int("SELECT COUNT(*) FROM draw_purges WHERE seq>?", [.int(acked)]))
        }
    }

    func pendingAssets() throws -> Int { try wrap { Int(try require().int("SELECT COUNT(*) FROM draw_wanted")) } }

    func refusedCount(_ peer: String) -> Int { refused[peer]?.count ?? 0 }

    /// Permission Off / disconnect: drop transient state; durable cursors stay.
    func forget(_ peer: String) {
        transfers = transfers.filter { !$0.key.hasPrefix(peer + " ") }
        refused.removeValue(forKey: peer)
    }

    // MARK: Test and harness hooks

    /// Every operation id of a drawing in canonical order (hidden ones included).
    func operationOrder(_ did: String) throws -> [String] {
        try wrap {
            var ids: [String] = []
            try require().run("SELECT record_id FROM draw_records WHERE drawing_id=? AND kind='op' ORDER BY sort_key", [.text(did)]) {
                ids.append(DrawStore.text($0, 0))
            }
            return ids
        }
    }

    /// Insert records directly, in the given order, in one transaction (conformance).
    func insertRecords(_ values: [ConnectJSON], source: String = "") throws -> [String] {
        let store = try require()
        let statuses = try wrap { try store.transaction { try values.map { try store.insert($0, source: source) } } }
        for did in Set(values.compactMap { $0["drawing_id"].string }) { emit(.records, did, peer: source.isEmpty ? nil : source) }
        return statuses
    }

    /// Simulated store restore: renews this store's epoch and resets its own
    /// cursors, as a Draw backup restore does on the desktop.
    func renewEpochForRestore() throws {
        let store = try require()
        try store.transaction {
            try store.setMeta("epoch", UUID().uuidString.lowercased())
            try store.run("UPDATE draw_peers SET acked_seq=0, peer_epoch=NULL")
        }
    }

    func failNextCommits(_ count: Int) { store?.failCommits = count }
}
