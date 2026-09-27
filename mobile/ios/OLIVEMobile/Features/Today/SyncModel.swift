import Foundation
import Observation

@MainActor @Observable
final class SyncModel {
    let store: MobileSyncStore
    private let session: ConnectSession?
    private(set) var records: [SignedSyncRecord] = []
    private(set) var conflicts: [SyncConflict] = []
    private(set) var notice = ""
    private(set) var busy = false
    private(set) var domainStatus: [String: String] = [:]
    private var cancelled = false
    var online: Bool { session?.connected == true && store.available }
    init(session: ConnectSession?, store: MobileSyncStore = MobileSyncStore()) { self.session = session; self.store = store; reload() }
    func reload() {
        records = store.snapshot.records.values.sorted { (store.snapshot.sequence[$0.id] ?? 0) < (store.snapshot.sequence[$1.id] ?? 0) }
        conflicts = store.snapshot.conflicts
        if !store.available { notice = ConnectFailure.localStorageUnavailable.localizedDescription }
    }
    func selected(_ id: String) -> Bool { guard let peer = session?.selectedID else { return false }; return store.snapshot.selection[peer + ":" + id] == true }
    func select(_ id: String, _ flag: Bool) {
        guard let peer = session?.selectedID, !busy else { return }
        var value = store.snapshot; value.selection[peer + ":" + id] = flag
        do { try store.commit(value); reload() } catch { notice = error.localizedDescription }
    }
    func sync(_ domain: String) async {
        guard !busy, let session else { return }
        busy = true; cancelled = false; notice = "Syncing…"; defer { busy = false; reload() }
        do {
            let (channel, identity, peer) = try await session.context()
            let key = peer.id + ":" + domain
            let known = Dictionary(uniqueKeysWithValues: (session.peers.map(\.identity) + [identity.publicIdentity]).map { ($0.deviceID, $0) })
            let deadline = ContinuousClock.now.advanced(by: .seconds(90))
            for _ in 0..<8 {
                guard !cancelled, ContinuousClock.now < deadline else { notice = "Partial sync · stopped"; return }
                let snapshot = store.snapshot, cursor = snapshot.cursors[key] ?? 0
                var batch: [SignedSyncRecord] = [], size = 0
                let candidates = snapshot.records.values.sorted { (snapshot.sequence[$0.id] ?? 0) < (snapshot.sequence[$1.id] ?? 0) }
                for record in candidates where SyncWire.domains[record.kind] == domain && !(snapshot.acknowledged[key] ?? []).contains(record.revision) {
                    if domain == "chat" {
                        let conversation = record.kind == "conversation" ? record.id : snapshot.messageParents[record.id] ?? ""
                        guard snapshot.selection[peer.id + ":" + conversation] == true else { continue }
                    }
                    if batch.count == 8 || size + record.bytes.count > 250000 { break }
                    batch.append(record); size += record.bytes.count
                }
                let request = try SyncWire.request(source: identity.publicIdentity.deviceID, target: peer.id, domain: domain, records: batch, cursor: cursor)
                var response: ConnectJSON
                repeat {
                    guard !cancelled, ContinuousClock.now < deadline else { notice = "Partial sync · stopped"; return }
                    response = try ConnectJSON.decode(await channel.exchangeFrame(kind: 5, id: request["request_id"].uuid(), payload: request.canonical), limit: 256000)
                    guard response["protocol_version"] == .string("olive-sync/1"), response["request_id"] == request["request_id"] else { throw ConnectFailure.responseMalformed }
                    if response["state"] == .string("rejected") {
                        try response.fields(["protocol_version", "request_id", "state", "error"])
                        if response["error"] == .string("confirmation_required") {
                            domainStatus[domain] = "Ask · waiting on computer"; try await Task.sleep(for: .seconds(1)); continue
                        }
                        if ["permission_off", "request_denied"].contains(response["error"].string ?? "") { domainStatus[domain] = "Off or denied"; throw ConnectFailure.syncPermissionDenied }
                        throw ConnectFailure.syncConflict
                    }
                    break
                } while true
                try response.fields(["protocol_version", "request_id", "state", "result"])
                guard response["state"] == .string("completed") else { throw ConnectFailure.responseMalformed }
                let result = response["result"]; try result.fields(["ack", "results", "records", "cursor", "more"])
                guard result["ack"] == .array(batch.map { .string($0.revision) }), let outcomes = result["results"].array,
                      outcomes.count == batch.count, outcomes.allSatisfy({ ["applied", "duplicate", "stale", "tombstone", "conflict"].contains($0.string ?? "") }),
                      let incoming = result["records"].array, incoming.count <= 8, let more = result["more"].boolean else { throw ConnectFailure.responseMalformed }
                let nextCursor = try result["cursor"].number(cursor...9007199254740992)
                let verified = try incoming.map { try SignedSyncRecord($0, known: known) }
                guard verified.allSatisfy({ SyncWire.domains[$0.kind] == domain }), Set(verified.map(\.id)).count == verified.count else { throw ConnectFailure.responseMalformed }
                // One atomic file commit binds revisions, receipts, conflicts and cursor.
                var next = store.snapshot, conflict = outcomes.contains(.string("conflict"))
                for record in verified {
                    if try MobileSyncStore.apply(record, peer: peer.id, in: &next) == "conflict" { conflict = true }
                }
                next.cursors[key] = nextCursor
                next.acknowledged[key, default: []].formUnion(batch.map(\.revision))
                try store.commit(next); reload(); domainStatus[domain] = "Sync permitted · last exchange verified"
                if conflict { notice = "Sync conflict · review on the device holding the conflict"; return }
                if !more && batch.isEmpty { notice = "Sync complete"; return }
            }
            notice = "Batch limit reached · Sync again to continue"
        } catch { notice = error.localizedDescription }
    }
    func cancel() { cancelled = true; notice = "Stopping after the current batch; committed records remain." }
    @discardableResult
    func save(kind: String, payload: ConnectJSON, old: SignedSyncRecord? = nil, deleted: Bool = false) async throws -> SignedSyncRecord {
        guard !busy, let session, online else { throw ConnectFailure.peerOffline }
        let (_, identity, _) = try await session.context()
        guard old == nil || store.snapshot.records[old!.id]?.revision == old!.revision else { throw ConnectFailure.syncRevisionStale }
        guard old?.deleted != true else { throw ConnectFailure.syncConflict }
        if let old, old.payload == payload, !deleted { return old }
        let record = try SyncWire.author(kind: kind, id: old?.id ?? UUID().uuidString.lowercased(), payload: payload, deleted: deleted, parents: old.map { [$0] } ?? [], identity: identity)
        guard MobileSyncStore.dependency(record, in: store.snapshot) else { throw ConnectFailure.syncConflict }
        var next = store.snapshot; try MobileSyncStore.put(record, in: &next); try store.commit(next); reload()
        notice = "Saved locally · pending explicit sync"
        return record
    }
    func resolve(_ conflict: SyncConflict, incoming: Bool) async {
        do {
            guard !busy, let session, online else { throw ConnectFailure.peerOffline }
            let (_, identity, _) = try await session.context()
            let current = store.snapshot.records[conflict.recordID]
            guard current?.revision == conflict.localRevision else { throw ConnectFailure.syncRevisionStale }
            let chosen = incoming ? conflict.incoming : current
            guard let chosen, !(current?.deleted == true || conflict.incoming.deleted) || chosen.deleted else { throw ConnectFailure.syncConflict }
            let record = try SyncWire.author(kind: chosen.kind, id: chosen.id, payload: chosen.payload, deleted: chosen.deleted,
                parents: (current.map { [$0] } ?? []) + [conflict.incoming], identity: identity)
            guard MobileSyncStore.dependency(record, in: store.snapshot) else { throw ConnectFailure.syncConflict }
            var next = store.snapshot; try MobileSyncStore.put(record, in: &next); next.conflicts.removeAll { $0.id == conflict.id }
            try store.commit(next); reload(); notice = "Resolution saved · Sync to share it"
        } catch { notice = error.localizedDescription }
    }
    func selectMobileChat(_ turns: [MobileChatTurn]) async {
        do {
            guard !busy, let session else { throw ConnectFailure.peerOffline }
            let (_, identity, peer) = try await session.context()
            var next = store.snapshot
            let conversationID = next.mobileConversation[peer.id] ?? UUID().uuidString.lowercased()
            if next.records[conversationID] == nil {
                let conversation = try SyncWire.author(kind: "conversation", id: conversationID,
                    payload: .object(["title": .string("iPhone Chat"), "project_id": .null, "created_at": .string(SyncWire.now())]), identity: identity)
                try MobileSyncStore.put(conversation, in: &next); next.mobileConversation[peer.id] = conversationID
            }
            guard next.records[conversationID]?.deleted == false else { throw ConnectFailure.syncConflict }
            next.selection[peer.id + ":" + conversationID] = true
            var after = next.records.values.filter { $0.kind == "message" && next.messageParents[$0.id] == conversationID }.max { (next.sequence[$0.id] ?? 0) < (next.sequence[$1.id] ?? 0) }?.id
            for turn in turns where turn.peerID == peer.id && !next.importedTurns.contains(turn.id) {
                for (id, role, content) in [(turn.userID, "user", turn.user), (turn.assistantID, "assistant", turn.answer)] {
                    let record = try SyncWire.author(kind: "message", id: id, payload: .object(["conversation_id": .string(conversationID),
                        "after": after.map(ConnectJSON.string) ?? .null, "role": .string(role), "content": .string(content),
                        "created_at": .string(ISO8601DateFormatter().string(from: turn.createdAt))]), identity: identity)
                    try MobileSyncStore.put(record, in: &next); after = id
                }
                next.importedTurns.insert(turn.id)
            }
            try store.commit(next); reload(); notice = "Completed iPhone turns selected · tap Sync Chat to share"
        } catch { notice = error.localizedDescription }
    }
}
