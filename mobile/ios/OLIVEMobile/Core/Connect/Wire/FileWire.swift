import Foundation

struct FileMetadata: Codable, Equatable, Sendable {
    let name: String
    let size: Int64
    let sha256: String
    let mime: String
    var wire: ConnectJSON { .object(["name": .string(name), "size": .int(size), "sha256": .string(sha256), "mime": .string(mime)]) }
    init(name: String, size: Int64, sha256: String, mime: String) throws {
        try self.init(.object(["name": .string(name), "size": .int(size), "sha256": .string(sha256), "mime": .string(mime)]))
    }
    init(_ value: ConnectJSON) throws {
        try value.fields(["name", "size", "sha256", "mime"])
        let name = try value["name"].text()
        let base = name.components(separatedBy: ".")[0].precomposedStringWithCompatibilityMapping.uppercased()
        let reserved = ["CON", "PRN", "AUX", "NUL"] + (1...9).flatMap { ["COM\($0)", "LPT\($0)"] }
        guard (1...180).contains(name.utf8.count), name == name.trimmingCharacters(in: .whitespacesAndNewlines),
              !name.hasSuffix("."), !name.contains(".."), !name.contains(where: { "/\\:<>\"|?*".contains($0) }),
              !name.unicodeScalars.contains(where: { [.control, .format, .surrogate, .privateUse, .unassigned].contains($0.properties.generalCategory) }),
              !reserved.contains(base) else { throw ConnectFailure.responseMalformed }
        guard let size = value["size"].integer, (0...FileWire.maximumFile).contains(size) else { throw ConnectFailure.fileTooLarge }
        let mime = try value["mime"].text()
        guard mime.utf8.count <= 100, mime.range(of: "^[a-zA-Z0-9.+-]+/[a-zA-Z0-9.+-]+$", options: .regularExpression) != nil else { throw ConnectFailure.responseMalformed }
        self.name = name; self.size = size; self.mime = mime; sha256 = try StudioWire.hash(value["sha256"])
    }
}

enum FileWire {
    static let maximumFile: Int64 = 64 * 1024 * 1024
    static let terminal: Set<String> = ["completed", "declined", "cancelled", "failed", "interrupted", "dismissed"]
    static let states = terminal.union(["offered", "awaiting_approval", "accepted", "transferring", "verifying"])
    static func request(source: String, target: String, transfer: String, operation: String,
                        arguments: ConnectJSON = .object([:]), id: String = UUID().uuidString.lowercased(), now: Int64 = Int64(Date().timeIntervalSince1970)) -> ConnectJSON {
        .object(["protocol_version": .string("olive-files/1"), "request_id": .string(id), "transfer_id": .string(transfer),
            "source_device_id": .string(source), "target_device_id": .string(target), "operation": .string(operation),
            "arguments": arguments, "timestamp": .int(now), "expires_at": .int(now + 120)])
    }
    static func packet(_ value: ConnectJSON, bytes: Data = Data()) throws -> Data {
        let result = ConnectFrame.length(value.canonical.count) + value.canonical + bytes
        _ = try decode(result); return result
    }
    static func decode(_ packet: Data) throws -> (ConnectJSON, Data) {
        guard (4...69636).contains(packet.count) else { throw ConnectFailure.responseMalformed }
        let size = packet.prefix(4).reduce(0) { ($0 << 8) | Int($1) }
        guard (1...4096).contains(size), size + 4 <= packet.count else { throw ConnectFailure.responseMalformed }
        let value = try ConnectJSON.decode(Data(packet.dropFirst(4).prefix(size)), limit: 4096)
        try value.fields(["protocol_version", "request_id", "transfer_id", "source_device_id", "target_device_id", "operation", "arguments", "timestamp", "expires_at"])
        for k in ["request_id", "transfer_id", "source_device_id", "target_device_id"] { _ = try value[k].uuid() }
        guard value["protocol_version"] == .string("olive-files/1") else { throw ConnectFailure.protocolVersionUnsupported }
        let now = try value["timestamp"].number(0...253402300799), expiry = try value["expires_at"].number(0...253402300799)
        guard (1...120).contains(expiry - now) else { throw ConnectFailure.responseMalformed }
        let bytes = Data(packet.dropFirst(size + 4)), op = try value["operation"].text(), a = value["arguments"]
        switch op {
        case "offer": _ = try FileMetadata(a)
        case "chunk":
            try a.fields(["offset"]); _ = try a["offset"].number(0...maximumFile)
            guard (1...65536).contains(bytes.count) else { throw ConnectFailure.responseMalformed }
        case "complete", "cancel", "status": try a.fields([])
        default: throw ConnectFailure.responseMalformed
        }
        guard op == "chunk" || bytes.isEmpty else { throw ConnectFailure.responseMalformed }
        return (value, bytes)
    }
    static func response(_ data: Data, id: String) throws -> ConnectJSON {
        let v = try ConnectJSON.decode(data, limit: 16384)
        guard v["protocol_version"] == .string("olive-files/1"), v["request_id"] == .string(id) else { throw ConnectFailure.responseMalformed }
        if v["state"] == .string("rejected") {
            try v.fields(["protocol_version", "request_id", "state", "error"])
            let code = try v["error"].text()
            guard code.range(of: "^[a-z_]{1,80}$", options: .regularExpression) != nil else { throw ConnectFailure.responseMalformed }
            switch code {
            case "permission_off", "permission_denied": throw ConnectFailure.remotePermissionDenied
            case "content_integrity_failed": throw ConnectFailure.fileHashMismatch
            case "inbox_quota_exhausted": throw ConnectFailure.fileInboxFull
            case "unknown_transfer": throw ConnectFailure.fileReceiptUnavailable
            case "transfer_capacity_reached": throw ConnectFailure.resourceBusy
            case "transfer_ledger_full": throw ConnectFailure.requestLedgerFull
            default: throw ConnectFailure.fileTransferInterrupted
            }
        }
        try v.fields(["protocol_version", "request_id", "state", "result"])
        guard v["state"] == .string("completed") else { throw ConnectFailure.responseMalformed }
        let r = v["result"]; try r.fields(["state", "received_size"])
        guard states.contains(r["state"].string ?? "") else { throw ConnectFailure.responseMalformed }
        _ = try r["received_size"].number(0...maximumFile); return r
    }
}
