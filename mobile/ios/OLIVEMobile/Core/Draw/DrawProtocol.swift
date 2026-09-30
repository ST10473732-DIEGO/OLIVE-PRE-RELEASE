import Foundation

/// olive-draw/1 wire format on the phone: strict JSON, explicit schemas,
/// bounded sizes (a port of `olive/draw/protocol.py`; limits mirror the shared
/// `protocol_v1.json`, checked by a unit test). Carried over the existing OLIVE
/// Connect channel, frames 15 (request) and 16 (response). Nothing from the
/// network is executed; records are validated field by field before storage.
enum DrawProtocol {
    static let name = "olive-draw/1"
    static let capability = "sync.draw"
    static let requestFrame: UInt8 = 15
    static let responseFrame: UInt8 = 16
    static let documentSchemas: [Int64] = [1, 2]
    enum Limit {
        static let maxFrameBytes = 512_000
        static let maxRequestLifetimeSeconds: Int64 = 120
        static let futureToleranceSeconds: Int64 = 5
        static let maxEntries = 256
        static let maxRequestBytes = 400_000
        static let maxWants = 32
        static let assetChunkBytes = 262_144
        static let maxAssetBytes = 48_000_000
        static let maxAssetTransfersPerPeer = 2
        static let maxStagedBytesPerPeer = 96_000_000
        static let transferIdleSeconds: Double = 60
        static let maxRoundsPerPump = 64
    }
    static let limitTable: [String: Int] = [
        "max_frame_bytes": Limit.maxFrameBytes, "max_request_lifetime_seconds": Int(Limit.maxRequestLifetimeSeconds),
        "future_tolerance_seconds": Int(Limit.futureToleranceSeconds), "max_entries": Limit.maxEntries,
        "max_request_bytes": Limit.maxRequestBytes, "max_wants": Limit.maxWants, "asset_chunk_bytes": Limit.assetChunkBytes,
        "max_asset_bytes": Limit.maxAssetBytes, "max_asset_transfers_per_peer": Limit.maxAssetTransfersPerPeer,
        "max_staged_bytes_per_peer": Limit.maxStagedBytesPerPeer, "transfer_idle_seconds": Int(Limit.transferIdleSeconds),
        "max_rounds_per_pump": Limit.maxRoundsPerPump,
    ]
    static let operations: [String: [String]] = [
        "hello": ["versions", "schemas"],
        "sync": ["epoch", "entries"],
        "asset": ["epoch", "transfer_id", "asset_id", "mime", "width", "height", "total_bytes", "count", "index", "data"],
    ]
    static let purgeFields = ["drawing_id", "at", "device"]
    static let statuses = ["applied", "duplicate", "purged", "rejected"]
    static let assetStatuses = ["partial", "stored", "exists", "rejected"]
    static let errors = ["unsupported_protocol", "malformed_message", "source_mismatch", "wrong_target", "expired_request",
                         "device_not_paired", "identity_mismatch", "permission_off", "capability_unavailable", "draw_unavailable",
                         "payload_too_large", "rate_limited", "busy", "invalid_record", "drawing_too_large", "too_many_operations",
                         "drawings_capacity", "invalid_image", "unsupported_image", "image_too_large", "checksum_mismatch"]
    static let requestFields: Set<String> = ["protocol_version", "request_id", "source_device_id", "target_device_id",
                                             "operation", "arguments", "timestamp", "expires_at"]

    /// Fixed error codes only.
    struct Failure: Error, Equatable, CustomStringConvertible {
        let code: String
        init(_ code: String) { self.code = errors.contains(code) ? code : "malformed_message" }
        var description: String { code }
    }

    struct Request: Sendable {
        let requestID: String
        let source: String
        let target: String
        let operation: String
        let arguments: ConnectJSON
        let timestamp: Int64
        let expiresAt: Int64
        /// Asset chunk bytes (decoded), for `asset`.
        let data: Data?
    }

    // MARK: Primitives

    static func load(_ raw: Data) throws -> ConnectJSON {
        guard raw.count <= Limit.maxFrameBytes else { throw Failure("payload_too_large") }
        do { return try ConnectJSON.decode(raw, limit: Limit.maxFrameBytes, allowDecimals: true) }
        catch { throw Failure("malformed_message") }
    }

    static func dumps(_ value: ConnectJSON) throws -> Data {
        let raw = value.canonical
        guard raw.count <= Limit.maxFrameBytes else { throw Failure("payload_too_large") }
        return raw
    }

    static func uuid(_ value: ConnectJSON) throws -> String {
        guard let text = value.string, DrawText.isUUID(text), UUID(uuidString: text)?.uuidString.lowercased() == text else {
            throw Failure("malformed_message")
        }
        return text
    }

    static func integer(_ value: ConnectJSON, _ low: Int64 = 0, _ high: Int64 = 1 << 53) throws -> Int64 {
        guard let number = value.integer, number >= low, number <= high else { throw Failure("malformed_message") }
        return number
    }

    static func fields(_ value: ConnectJSON, required: [String], optional: [String] = []) throws {
        guard let object = value.object else { throw Failure("malformed_message") }
        let keys = Set(object.keys)
        guard Set(required).isSubset(of: keys), keys.subtracting(required).subtracting(optional).isEmpty else {
            throw Failure("malformed_message")
        }
    }

    static func wants(_ value: ConnectJSON) throws -> [String] {
        guard let items = value.array, items.count <= Limit.maxWants else { throw Failure("malformed_message") }
        let ids = try items.map { item -> String in
            guard let text = item.string, DrawText.isAssetID(text) else { throw Failure("malformed_message") }
            return text
        }
        guard Set(ids).count == ids.count else { throw Failure("malformed_message") }
        return ids
    }

    static func versions(_ value: ConnectJSON) throws -> [String] {
        guard let items = value.array, (1...4).contains(items.count) else { throw Failure("malformed_message") }
        return try items.map { item in
            guard let text = item.string, text.count <= 32 else { throw Failure("malformed_message") }
            return text
        }
    }

    static func schemas(_ value: ConnectJSON) throws -> [Int64] {
        guard let items = value.array, (1...16).contains(items.count) else { throw Failure("malformed_message") }
        return try items.map { item in
            guard let number = item.integer, (1...1000).contains(number) else { throw Failure("malformed_message") }
            return number
        }
    }

    static func validateEntry(_ entry: ConnectJSON) throws -> Int64 {
        guard let object = entry.object else { throw Failure("malformed_message") }
        let keys = Set(object.keys)
        if keys == ["seq", "record"] {
            let seq = try integer(object["seq"]!, 1)
            // Shape only here; the receiver validates each record fully and refuses
            // just that entry, so one record it cannot accept never blocks the rest.
            guard object["record"]!.object != nil, object["record"]!["record_id"].string != nil else { throw Failure("malformed_message") }
            return seq
        }
        if keys == ["seq", "purge"] {
            let seq = try integer(object["seq"]!, 1)
            let purge = object["purge"]!
            try fields(purge, required: purgeFields)
            _ = try uuid(purge["drawing_id"]); _ = try uuid(purge["device"])
            guard let at = purge["at"].string, DrawText.isTimestamp(at) else { throw Failure("malformed_message") }
            return seq
        }
        throw Failure("malformed_message")
    }

    /// Validates arguments; returns decoded asset chunk bytes for `asset`.
    static func validateArguments(_ operation: String, _ arguments: ConnectJSON) throws -> Data? {
        guard let required = operations[operation] else { throw Failure("malformed_message") }
        try fields(arguments, required: required)
        if operation == "hello" {
            _ = try versions(arguments["versions"]); _ = try schemas(arguments["schemas"])
            return nil
        }
        _ = try uuid(arguments["epoch"])
        if operation == "sync" {
            guard let entries = arguments["entries"].array else { throw Failure("malformed_message") }
            guard entries.count <= Limit.maxEntries else { throw Failure("payload_too_large") }
            let seqs = try entries.map(validateEntry)
            guard Set(seqs).count == seqs.count else { throw Failure("malformed_message") }
            return nil
        }
        let chunk = Int64(Limit.assetChunkBytes)
        let countLimit = (Int64(Limit.maxAssetBytes) + chunk - 1) / chunk
        let side = Int64(DrawSpec.Limit.maxAssetSide)
        guard let asset = arguments["asset_id"].string, DrawText.isAssetID(asset) else { throw Failure("malformed_message") }
        guard let mime = arguments["mime"].string, DrawSpec.imageTypes.contains(mime) else { throw Failure("unsupported_image") }
        _ = try uuid(arguments["transfer_id"])
        _ = try integer(arguments["width"], 1, side); _ = try integer(arguments["height"], 1, side)
        let total = try integer(arguments["total_bytes"], 1, Int64(Limit.maxAssetBytes))
        let count = try integer(arguments["count"], 1, countLimit)
        let index = try integer(arguments["index"], 0, countLimit - 1)
        guard index < count, count == (total + chunk - 1) / chunk else { throw Failure("malformed_message") }
        guard let encoded = arguments["data"].string else { throw Failure("malformed_message") }
        guard encoded.utf8.count <= (Limit.assetChunkBytes * 4) / 3 + 4 else { throw Failure("payload_too_large") }
        guard let data = Data(base64Encoded: encoded), !data.isEmpty, data.count <= Limit.assetChunkBytes else {
            throw Failure("malformed_message")
        }
        return data
    }

    // MARK: Envelopes

    static func encodeRequest(requestID: String, source: String, target: String, operation: String,
                              arguments: ConnectJSON, now: Int64) throws -> Data {
        try dumps(.object(["protocol_version": .string(name), "request_id": .string(requestID), "source_device_id": .string(source),
                           "target_device_id": .string(target), "operation": .string(operation), "arguments": arguments,
                           "timestamp": .int(now), "expires_at": .int(now + Limit.maxRequestLifetimeSeconds)]))
    }

    static func decodeRequest(_ raw: Data) throws -> Request {
        let value = try load(raw)
        guard let object = value.object, Set(object.keys) == requestFields else { throw Failure("malformed_message") }
        guard object["protocol_version"] == .string(name) else { throw Failure("unsupported_protocol") }
        let requestID = try uuid(value["request_id"]), source = try uuid(value["source_device_id"]), target = try uuid(value["target_device_id"])
        guard let operation = value["operation"].string, operations[operation] != nil else { throw Failure("malformed_message") }
        let timestamp = try integer(value["timestamp"], 0, 253_402_300_799)
        let expires = try integer(value["expires_at"], 0, 253_402_300_799)
        guard expires - timestamp > 0, expires - timestamp <= Limit.maxRequestLifetimeSeconds else { throw Failure("malformed_message") }
        let data = try validateArguments(operation, value["arguments"])
        return Request(requestID: requestID, source: source, target: target, operation: operation, arguments: value["arguments"],
                       timestamp: timestamp, expiresAt: expires, data: data)
    }

    /// The request id of a (possibly invalid) request, for correlated rejections.
    static func requestID(of raw: Data) -> String? {
        guard let value = try? ConnectJSON.decode(raw, limit: Limit.maxFrameBytes, allowDecimals: true),
              let id = try? uuid(value["request_id"]) else { return nil }
        return id
    }

    static func checkFresh(_ request: Request, now: Int64) throws {
        if request.timestamp > now + Limit.futureToleranceSeconds || request.expiresAt <= now { throw Failure("expired_request") }
    }

    static func encodeResponse(requestID: String?, result: ConnectJSON) throws -> Data {
        try dumps(.object(["protocol_version": .string(name), "request_id": requestID.map { .string($0) } ?? .null,
                           "state": .string("completed"), "result": result]))
    }

    static func encodeResponse(requestID: String?, error: String) -> Data {
        let code = errors.contains(error) ? error : "malformed_message"
        return ConnectJSON.object(["protocol_version": .string(name), "request_id": requestID.map { .string($0) } ?? .null,
                                   "state": .string("rejected"), "error": .string(code)]).canonical
    }

    struct Response: Sendable { let requestID: String?; let result: ConnectJSON?; let error: String? }

    static func decodeResponse(_ raw: Data) throws -> Response {
        let value = try load(raw)
        guard let object = value.object, object["protocol_version"] == .string(name),
              let state = object["state"]?.string, ["completed", "rejected"].contains(state) else { throw Failure("malformed_message") }
        let expected: Set<String> = ["protocol_version", "request_id", "state", state == "completed" ? "result" : "error"]
        guard Set(object.keys) == expected else { throw Failure("malformed_message") }
        let id: String? = value["request_id"] == .null ? nil : try uuid(value["request_id"])
        if state == "rejected" {
            guard let error = value["error"].string, error.count <= 64 else { throw Failure("malformed_message") }
            return Response(requestID: id, result: nil, error: error)
        }
        return Response(requestID: id, result: value["result"], error: nil)
    }

    // MARK: Results (sender side)

    struct HelloResult: Sendable { let versions: [String]; let epoch: String; let schemas: [Int64]; let wants: [String] }
    struct SyncResult: Sendable { let epoch: String; let results: [(status: String, error: String?)]; let wants: [String] }
    struct AssetResult: Sendable { let epoch: String; let status: String; let error: String? }

    static func helloResult(_ result: ConnectJSON) throws -> HelloResult {
        try fields(result, required: ["versions", "epoch", "schemas", "wants"])
        return HelloResult(versions: try versions(result["versions"]), epoch: try uuid(result["epoch"]),
                           schemas: try schemas(result["schemas"]), wants: try wants(result["wants"]))
    }

    static func syncResult(_ result: ConnectJSON, entries: Int) throws -> SyncResult {
        try fields(result, required: ["epoch", "results", "wants"])
        let epoch = try uuid(result["epoch"])
        guard let rows = result["results"].array, rows.count == entries else { throw Failure("malformed_message") }
        let decoded = try rows.map { row -> (status: String, error: String?) in
            try fields(row, required: ["status"], optional: ["error"])
            guard let status = row["status"].string, statuses.contains(status) else { throw Failure("malformed_message") }
            if row.object?["error"] != nil {
                guard let error = row["error"].string, errors.contains(error) else { throw Failure("malformed_message") }
                return (status, error)
            }
            return (status, nil)
        }
        return SyncResult(epoch: epoch, results: decoded, wants: try wants(result["wants"]))
    }

    static func assetResult(_ result: ConnectJSON) throws -> AssetResult {
        try fields(result, required: ["epoch", "status"], optional: ["error"])
        let epoch = try uuid(result["epoch"])
        guard let status = result["status"].string, assetStatuses.contains(status) else { throw Failure("malformed_message") }
        if result.object?["error"] != nil {
            guard let error = result["error"].string, errors.contains(error) else { throw Failure("malformed_message") }
            return AssetResult(epoch: epoch, status: status, error: error)
        }
        return AssetResult(epoch: epoch, status: status, error: nil)
    }
}
