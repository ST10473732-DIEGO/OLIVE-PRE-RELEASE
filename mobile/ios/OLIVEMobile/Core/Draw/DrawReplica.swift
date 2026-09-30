import Foundation

/// The record set of one open drawing and the picture it means (in memory).
///
/// A Swift port of `desktop/src/features/draw/replica.ts`; the durable store
/// (`DrawStore`) applies the same rules in SQL. Both are checked against the
/// shared `conformance_v1.json` in random arrival orders.
///
///  * records are immutable and unique by record_id; applying one twice does nothing;
///  * operations are drawn in (lamport, device, record_id) order — never wall-clock;
///  * an operation is hidden iff the greatest visibility record targeting it
///    *made by the operation's own device* says so (local-origin Undo/Redo);
///  * title and trashed take the value of their greatest meta record.
struct DrawReplica: Sendable {
    struct Change: Equatable, Sendable {
        /// The visible picture changed.
        var changed = false
        /// The only change was a new visible operation after every other one.
        var appended = false
        /// Title/trash/size changed.
        var meta = false
    }
    struct Create: Equatable, Sendable {
        let width: Int, height: Int, background: String, title: String, createdAt: String
    }
    private struct Entry: Sendable { let key: DrawKey; let op: DrawOp }
    private struct Winner: Sendable { let key: DrawKey; let hidden: Bool }

    let drawingID: String
    private(set) var ids = Set<String>()
    private var entries: [Entry] = []
    private var authors: [String: String] = [:]           // op id -> device
    private var visibility: [String: Winner] = [:]
    private var pendingVisibility: [String: [DrawRecord]] = [:]
    private var titleKey: DrawKey?
    private var trashKey: DrawKey?
    private(set) var create: Create?
    private(set) var title = ""
    private(set) var trashed = false
    private(set) var clock: Int64 = 0
    private var cache: [DrawOp]?

    init(drawingID: String) { self.drawingID = drawingID }

    /// Apply one validated record (idempotent, order-independent).
    @discardableResult
    mutating func apply(_ record: DrawRecord) -> Change {
        guard record.drawingID == drawingID, !ids.contains(record.recordID) else { return Change() }
        ids.insert(record.recordID)
        clock = max(clock, record.lamport)
        let key = record.key
        switch record.kind {
        case "create":
            let body = record.body
            create = Create(width: Int(body["width"].integer ?? 0), height: Int(body["height"].integer ?? 0),
                            background: body["background"].string ?? "#ffffff", title: body["title"].string ?? "",
                            createdAt: body["created_at"].string ?? "")
            if titleKey == nil { title = create!.title }
            return Change(changed: true, appended: false, meta: true)
        case "op":
            guard let op = try? DrawOp(json: record.body) else { return Change() }
            var index = entries.count
            while index > 0 && key < entries[index - 1].key { index -= 1 }
            entries.insert(Entry(key: key, op: op), at: index)
            authors[record.recordID] = record.device
            for early in pendingVisibility.removeValue(forKey: record.recordID) ?? [] { fold(early) }
            cache = nil
            let hidden = visibility[record.recordID]?.hidden ?? false
            return Change(changed: !hidden, appended: !hidden && index == entries.count - 1, meta: false)
        case "visibility":
            guard let target = record.body["target"].string else { return Change() }
            guard authors[target] != nil else {
                pendingVisibility[target, default: []].append(record)
                return Change()
            }
            let before = visibility[target]?.hidden ?? false
            fold(record)
            let after = visibility[target]?.hidden ?? false
            if before != after { cache = nil }
            return Change(changed: before != after, appended: false, meta: false)
        case "meta":
            let field = record.body["field"].string
            if field == "title", titleKey.map({ $0 < key }) ?? true {
                titleKey = key
                title = record.body["value"].string ?? title
                return Change(changed: false, appended: false, meta: true)
            }
            if field == "trashed", trashKey.map({ $0 < key }) ?? true {
                trashKey = key
                trashed = record.body["value"].boolean ?? trashed
                return Change(changed: false, appended: false, meta: true)
            }
            return Change()
        default:
            return Change()
        }
    }

    private mutating func fold(_ record: DrawRecord) {
        guard let target = record.body["target"].string, let author = authors[target], author == record.device,
              let hidden = record.body["hidden"].boolean else { return }   // Only the author's device can undo it.
        let key = record.key
        if let current = visibility[target], !(current.key < key) { return }
        visibility[target] = Winner(key: key, hidden: hidden)
    }

    /// Every operation id in drawing order (hidden ones included).
    var order: [String] { entries.map(\.op.id) }

    /// The visible operations in drawing order.
    mutating func visible() -> [DrawOp] {
        if let cache { return cache }
        let value = entries.filter { !(visibility[$0.op.id]?.hidden ?? false) }.map(\.op)
        cache = value
        return value
    }

    func isHidden(_ id: String) -> Bool { visibility[id]?.hidden ?? false }
    var operationCount: Int { entries.count }
}
