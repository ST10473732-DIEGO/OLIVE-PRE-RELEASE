import Foundation

struct SyncConflict: Codable, Identifiable {
    let id: String
    let peer: String
    let recordID: String
    let localRevision: String?
    let incoming: SignedSyncRecord
    let reason: String
}
struct RemoteSyncConflict: Codable {
    let recordID: String
    let vector: [String: Int64]
}
struct SyncSnapshot: Codable {
    // Additive v1 metadata: a remote conflict receipt is not successful convergence.
    var remoteConflicts: [String: [RemoteSyncConflict]]? = nil
    var records: [String: SignedSyncRecord] = [:]
    var receipts: [String: String] = [:]
    var conflicts: [SyncConflict] = []
    var cursors: [String: Int64] = [:]
    var acknowledged: [String: Set<String>] = [:]
    var selection: [String: Bool] = [:]
    var messageParents: [String: String] = [:]
    var messagePredecessors: [String: String]? = nil
    var sequence: [String: Int64] = [:]
    var counter: Int64 = 0
    var importedTurns: Set<String> = []
    var mobileConversation: [String: String] = [:]
}

@MainActor
final class MobileSyncStore {
    let drafts: TodayDraftStore
    private let store: ProtectedStore<SyncSnapshot>
    private(set) var snapshot = SyncSnapshot()
    private(set) var available = true
    init(directory: URL = URL.applicationSupportDirectory.appendingPathComponent("Companion")) {
        drafts = TodayDraftStore(directory: directory)
        store = ProtectedStore(url: directory.appendingPathComponent("sync-v1.json"), maximumBytes: 96 * 1024 * 1024)
        do { snapshot = try store.load() ?? SyncSnapshot(); try bounds(snapshot) }
        catch { available = false }
    }
    func bounds(_ value: SyncSnapshot) throws {
        guard value.records.count <= 10000, value.receipts.count <= 100000, value.conflicts.count <= 128,
              value.records.values.reduce(0, { $0 + $1.bytes.count }) <= 64 * 1024 * 1024,
              value.selection.count <= 16000, value.cursors.count <= 128, value.importedTurns.count <= 100000,
              (value.remoteConflicts ?? [:]).values.reduce(0, { $0 + $1.count }) <= 128,
              value.acknowledged.values.reduce(0, { $0 + $1.count }) <= 100000 else { throw ConnectFailure.localStorageUnavailable }
    }
    func commit(_ value: SyncSnapshot) throws {
        guard available else { throw ConnectFailure.localStorageUnavailable }
        try bounds(value); try store.save(value); snapshot = value
    }
    func recover() throws {
        guard !available else { return }
        try store.archiveAndReplace(with: SyncSnapshot())
        snapshot = SyncSnapshot(); available = true
    }
    static func tombstoneConversation(_ reviewed: SignedSyncRecord, identity: ConnectIdentity, in next: inout SyncSnapshot) throws {
        guard reviewed.kind == "conversation", !reviewed.deleted, next.records[reviewed.id]?.revision == reviewed.revision else { throw ConnectFailure.syncRevisionStale }
        for message in next.records.values.filter({ $0.kind == "message" && !$0.deleted && next.messageParents[$0.id] == reviewed.id }).sorted(by: { $0.id < $1.id }) {
            let tombstone = try SyncWire.author(kind: "message", id: message.id, payload: .object([:]), deleted: true, parents: [message], identity: identity)
            try put(tombstone, in: &next)
        }
        let tombstone = try SyncWire.author(kind: "conversation", id: reviewed.id, payload: .object([:]), deleted: true, parents: [reviewed], identity: identity)
        guard dependency(tombstone, in: next) else { throw ConnectFailure.syncConflict }
        try put(tombstone, in: &next)
    }
    static func recordOutcomes(_ outcomes: [ConnectJSON], batch: [SignedSyncRecord], incoming: [SignedSyncRecord], key: String, in value: inout SyncSnapshot) {
        var conflicts = value.remoteConflicts?[key] ?? []
        for (record, outcome) in zip(batch, outcomes) {
            if outcome == .string("conflict") {
                conflicts.removeAll { $0.recordID == record.id }
                conflicts.append(RemoteSyncConflict(recordID: record.id, vector: record.vector))
            } else if ["applied", "duplicate", "tombstone"].contains(outcome.string ?? "") {
                conflicts.removeAll { $0.recordID == record.id && record.vector != $0.vector && SyncWire.dominates(record.vector, $0.vector) }
            }
        }
        for record in incoming {
            conflicts.removeAll { $0.recordID == record.id && record.vector != $0.vector && SyncWire.dominates(record.vector, $0.vector) }
        }
        if value.remoteConflicts == nil { value.remoteConflicts = [:] }
        if conflicts.isEmpty { value.remoteConflicts?.removeValue(forKey: key) }
        else { value.remoteConflicts?[key] = conflicts }
    }
    static func receipt(_ record: SignedSyncRecord, in value: inout SyncSnapshot) throws {
        let digest = record.wire.digest
        if let old = value.receipts[record.revision], old != digest { throw ConnectFailure.syncConflict }
        value.receipts[record.revision] = digest
    }
    static func hasConflict(domain: String, peer: String, in value: SyncSnapshot) -> Bool {
        value.conflicts.contains { $0.peer == peer && SyncWire.domains[$0.incoming.kind] == domain }
            || !(value.remoteConflicts?[peer + ":" + domain] ?? []).isEmpty
    }
    static func put(_ record: SignedSyncRecord, in value: inout SyncSnapshot) throws {
        try receipt(record, in: &value)
        value.counter += 1; value.records[record.id] = record; value.sequence[record.id] = value.counter
        if record.kind == "message", !record.deleted {
            value.messageParents[record.id] = record.payload["conversation_id"].string
            if value.messagePredecessors == nil { value.messagePredecessors = [:] }
            value.messagePredecessors?[record.id] = record.payload["after"].string ?? ""
        }
        value.conflicts.removeAll { $0.recordID == record.id && SyncWire.dominates(record.vector, $0.incoming.vector) && record.vector != $0.incoming.vector }
    }
    static func dependency(_ record: SignedSyncRecord, in value: SyncSnapshot) -> Bool {
        let p = record.payload
        func live(_ id: String?, _ kind: String) -> Bool {
            guard let id, let r = value.records[id] else { return false }; return r.kind == kind && !r.deleted
        }
        if record.deleted {
            return !value.records.values.contains { other in
                guard !other.deleted, other.id != record.id else { return false }
                let p = other.payload
                return p["calendar_id"].string == record.id || p["event_id"].string == record.id || p["target_id"].string == record.id || p["conversation_id"].string == record.id
            }
        }
        if p["project_id"] != .null && p["project_id"] != .string("") { return false }
        if let contacts = p["contact_ids"].array, !contacts.isEmpty { return false }
        switch record.kind {
        case "event": return live(p["calendar_id"].string, "calendar")
        case "task": return p["event_id"] == .string("") || live(p["event_id"].string, "event")
        case "reminder": return live(p["target_id"].string, p["target_kind"].string ?? "")
        case "message":
            if p["after"].string == record.id { return false }
            if let old = value.records[record.id], !old.deleted,
               old.payload["conversation_id"] != p["conversation_id"] || old.payload["after"] != p["after"] { return false }
            return live(p["conversation_id"].string, "conversation") && (p["after"] == .null || value.records[p["after"].string ?? ""]?.kind == "message" && value.messageParents[p["after"].string ?? ""] == p["conversation_id"].string)
        default: return true
        }
    }
    static func apply(_ incoming: SignedSyncRecord, peer: String, in value: inout SyncSnapshot) throws -> String {
        try receipt(incoming, in: &value)
        let current = value.records[incoming.id]
        if let current, current.kind != incoming.kind { throw ConnectFailure.syncConflict }
        if current?.revision == incoming.revision { return "duplicate" }
        if let current, SyncWire.dominates(current.vector, incoming.vector), current.vector != incoming.vector { return "stale" }
        var reason: String?
        if let current {
            if current.deleted && !incoming.deleted { reason = "deleted_record_update" }
            else if !SyncWire.dominates(incoming.vector, current.vector) || incoming.vector == current.vector { reason = "concurrent_edit" }
        }
        let conversation = incoming.kind == "conversation" ? incoming.id : incoming.kind == "message" ? incoming.payload["conversation_id"].string ?? value.messageParents[incoming.id] : nil
        if let conversation, value.selection[peer + ":" + conversation] == false || value.records[conversation] != nil && value.selection[peer + ":" + conversation] != true { reason = "conversation_not_shared" }
        if reason == nil && !dependency(incoming, in: value) { reason = "missing_dependency" }
        if let reason {
            if !value.conflicts.contains(where: { $0.incoming.revision == incoming.revision && $0.peer == peer }) {
                value.conflicts.append(SyncConflict(id: UUID().uuidString.lowercased(), peer: peer, recordID: incoming.id,
                    localRevision: current?.revision, incoming: incoming, reason: reason))
            }
            return "conflict"
        }
        try put(incoming, in: &value)
        if let conversation, value.selection[peer + ":" + conversation] == nil { value.selection[peer + ":" + conversation] = true }
        return "applied"
    }
}

struct TodayDraft: Codable {
    let original: SignedSyncRecord?
    let fields: Data
}

@MainActor
final class TodayDraftStore {
    private let store: ProtectedStore<[String: TodayDraft]>
    private var values: [String: TodayDraft] = [:]
    private(set) var available = true
    init(directory: URL) {
        store = ProtectedStore(url: directory.appendingPathComponent("today-drafts-v1.json"), maximumBytes: 8_000_000)
        do {
            values = try store.load() ?? [:]
            guard values.count <= 64 else { throw ConnectFailure.localStorageUnavailable }
            for value in values.values { guard try ConnectJSON.decode(value.fields, limit: 72000).object != nil else { throw ConnectFailure.localStorageUnavailable } }
        } catch { available = false }
    }
    func get(_ key: String) throws -> TodayDraft? {
        guard available else { throw ConnectFailure.localStorageUnavailable }
        return values[key]
    }
    func save(_ key: String, original: SignedSyncRecord?, fields: [String: ConnectJSON]?) throws {
        guard available else { throw ConnectFailure.localStorageUnavailable }
        var next = values
        if let fields {
            let data = ConnectJSON.object(fields).canonical
            guard data.count <= 72000 else { throw ConnectFailure.localStorageUnavailable }
            next[key] = TodayDraft(original: original, fields: data)
        } else { next.removeValue(forKey: key) }
        guard next.count <= 64 else { throw ConnectFailure.localStorageUnavailable }
        try store.save(next); values = next
    }
}
