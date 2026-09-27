import Foundation
import CryptoKit

struct SignedSyncRecord: Codable, Identifiable, Equatable {
    let bytes: Data
    var wire: ConnectJSON { try! ConnectJSON.decode(bytes) } // Validated on initialization/decoding.
    var id: String { wire["record_id"].string! }
    var kind: String { wire["kind"].string! }
    var revision: String { wire["revision"].string! }
    var deleted: Bool { wire["deleted"].boolean! }
    var payload: ConnectJSON { wire["payload"] }
    var vector: [String: Int64] { wire["ancestry"].object!.mapValues { $0.integer! } }
    init(_ value: ConnectJSON, known: [String: ConnectPublicIdentity] = [:]) throws {
        try value.fields(["kind", "record_id", "schema_version", "revision", "ancestry", "origin_device_id", "editor_device_id", "updated_at", "deleted", "payload", "editor_identity", "signature"])
        guard value.canonical.count <= 72000, value["schema_version"] == .int(1), let kind = value["kind"].string,
              SyncWire.domains[kind] != nil, value["deleted"].boolean != nil, value["payload"].object != nil else { throw ConnectFailure.responseMalformed }
        _ = try SyncWire.recordID(value["record_id"])
        for key in ["revision", "origin_device_id", "editor_device_id"] { _ = try value[key].uuid() }
        guard let vector = value["ancestry"].object, (1...32).contains(vector.count), vector[try value["editor_device_id"].uuid()] != nil else { throw ConnectFailure.responseMalformed }
        for (id, count) in vector { _ = try ConnectJSON.string(id).uuid(); _ = try count.number(1...9007199254740992) }
        try SyncWire.instant(value["updated_at"], requireZone: true)
        if value["deleted"] == .bool(true) { try value["payload"].fields([]) }
        else { try SyncPayload.validate(kind: kind, value: value["payload"]) }
        let identity = try ConnectPublicIdentity(value["editor_identity"])
        guard identity.deviceID == value["editor_device_id"].string, known[identity.deviceID] == nil || known[identity.deviceID] == identity,
              let signatureString = value["signature"].string, signatureString.count == 88,
              let signature = Data(base64Encoded: signatureString), signature.base64EncodedString() == signatureString else { throw ConnectFailure.identityMismatch }
        var unsigned = value.object!; unsigned.removeValue(forKey: "signature")
        let message = Data("OLIVE-SYNC-REVISION/1\0".utf8) + ConnectJSON.object(unsigned).canonical
        guard try Curve25519.Signing.PublicKey(rawRepresentation: identity.publicKey).isValidSignature(signature, for: message) else { throw ConnectFailure.identityMismatch }
        bytes = value.canonical
    }
    init(from decoder: Decoder) throws { try self.init(ConnectJSON.decode(decoder.singleValueContainer().decode(Data.self))) }
    func encode(to encoder: Encoder) throws { var container = encoder.singleValueContainer(); try container.encode(bytes) }
}

enum SyncWire {
    static let domains = ["task": "tasks", "calendar": "calendar", "event": "calendar", "reminder": "reminders", "conversation": "chat", "message": "chat"]
    static func recordID(_ value: ConnectJSON) throws -> String {
        let s = try value.text()
        if s.count == 36 { return try value.uuid() }
        guard s.range(of: "^[0-9a-f]{32}$", options: .regularExpression) != nil else { throw ConnectFailure.responseMalformed }; return s
    }
    static func instant(_ value: ConnectJSON, requireZone: Bool = false) throws {
        _ = try SyncDate.parse(value.text(), zoned: requireZone)
    }
    static func dominates(_ left: [String: Int64], _ right: [String: Int64]) -> Bool { right.allSatisfy { (left[$0.key] ?? 0) >= $0.value } }
    static func now() -> String { ISO8601DateFormatter().string(from: Date()).replacingOccurrences(of: "Z", with: "+00:00") }
    static func author(kind: String, id: String = UUID().uuidString.lowercased(), payload: ConnectJSON, deleted: Bool = false,
                       parents: [SignedSyncRecord] = [], identity: ConnectIdentity) throws -> SignedSyncRecord {
        let source = identity.publicIdentity.deviceID
        var vector: [String: Int64] = [:]
        for parent in parents { for (key, count) in parent.vector { vector[key] = max(vector[key] ?? 0, count) } }
        vector[source] = (vector[source] ?? 0) + 1
        var value: [String: ConnectJSON] = ["kind": .string(kind), "record_id": .string(id), "schema_version": .int(1),
            "revision": .string(UUID().uuidString.lowercased()), "ancestry": .object(vector.mapValues(ConnectJSON.int)),
            "origin_device_id": parents.first?.wire["origin_device_id"] ?? .string(source), "editor_device_id": .string(source),
            "updated_at": .string(now()), "deleted": .bool(deleted), "payload": deleted ? .object([:]) : payload,
            "editor_identity": identity.publicIdentity.wire]
        value["signature"] = .string(try identity.sign(Data("OLIVE-SYNC-REVISION/1\0".utf8) + ConnectJSON.object(value).canonical).base64EncodedString())
        return try SignedSyncRecord(.object(value))
    }
    static func request(source: String, target: String, domain: String, records: [SignedSyncRecord], cursor: Int64,
                        id: String = UUID().uuidString.lowercased(), now: Int64 = Int64(Date().timeIntervalSince1970)) throws -> ConnectJSON {
        guard Set(domains.values).contains(domain), records.count <= 8, (0...9007199254740992).contains(cursor),
              records.allSatisfy({ domains[$0.kind] == domain }), Set(records.map(\.id)).count == records.count else { throw ConnectFailure.responseMalformed }
        let value = ConnectJSON.object(["protocol_version": .string("olive-sync/1"), "request_id": .string(id),
            "source_device_id": .string(source), "target_device_id": .string(target), "updated_by_device_id": .string(source),
            "capability": .string("sync." + domain), "operation": .string("exchange"),
            "arguments": .object(["records": .array(records.map(\.wire)), "cursor": .int(cursor)]), "timestamp": .int(now), "expires_at": .int(now + 120)])
        for uuid in [id, source, target] { _ = try ConnectJSON.string(uuid).uuid() }
        guard value.canonical.count <= 256000 else { throw ConnectFailure.inputTooLarge }; return value
    }
}
