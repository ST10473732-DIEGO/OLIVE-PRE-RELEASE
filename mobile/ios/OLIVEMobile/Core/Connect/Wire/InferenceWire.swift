import Foundation

struct InferenceWire {
    static let states: Set<String> = ["awaiting_approval", "queued", "starting", "streaming", "completed", "cancelled", "failed", "timed_out", "connection_lost", "revoked"]
    static let terminal = states.subtracting(["awaiting_approval", "queued", "starting", "streaming"])
    static let errors: Set<String> = ["permission_denied", "confirmation_required", "device_revoked", "device_unavailable", "model_unavailable", "busy", "rate_limited", "input_too_large", "output_limit", "generation_timeout", "cancelled", "connection_lost", "inference_failed", "invalid_request", "changed_duplicate", "expired_request", "unknown_request", "stream_invalid", "request_indeterminate", "ledger_full"]
    /// C7 is duplex even when this device is only a client. Desktop discovery
    /// may query our availability while C5/C6/C8 use the same authenticated TLS
    /// channel. Report no inference provider; never accept executable work.
    static func clientReply(_ bytes: Data, local: String, peer: String,
                            now: Int64 = Int64(Date().timeIntervalSince1970)) throws -> ConnectJSON {
        let v = try ConnectJSON.decode(bytes)
        try v.fields(["protocol_version", "request_id", "source_device_id", "target_device_id",
                      "job_id", "operation", "arguments", "timestamp", "expires_at"])
        guard v["protocol_version"] == .string("olive-inference/1") else { throw ConnectFailure.protocolVersionUnsupported }
        for key in ["request_id", "source_device_id", "target_device_id", "job_id"] { _ = try v[key].uuid() }
        guard v["source_device_id"] == .string(peer), v["target_device_id"] == .string(local) else { throw ConnectFailure.identityMismatch }
        let timestamp = try v["timestamp"].number(0...253402300799)
        let expiry = try v["expires_at"].number(0...253402300799)
        guard (1...120).contains(expiry - timestamp) else { throw ConnectFailure.responseMalformed }
        let operation = try v["operation"].text(), arguments = v["arguments"]
        switch operation {
        case "start":
            try arguments.fields(["preset", "messages", "input_fingerprint", "max_tokens", "max_output_bytes", "seconds"])
            guard let messages = arguments["messages"].array else { throw ConnectFailure.responseMalformed }
            let contents = try messages.map { message -> (String, String) in
                try message.fields(["role", "content"])
                return (try message["role"].text(), try message["content"].text())
            }
            let validated = try startArguments(preset: arguments["preset"].text(), messages: contents)
            guard arguments["input_fingerprint"] == validated["input_fingerprint"], v["request_id"] == v["job_id"] else { throw ConnectFailure.responseMalformed }
            _ = try arguments["max_tokens"].number(1...2048)
            _ = try arguments["max_output_bytes"].number(1...64000)
            _ = try arguments["seconds"].number(1...120)
        case "poll":
            try arguments.fields(["after"]); _ = try arguments["after"].number(0...64000)
        case "status", "capabilities", "cancel": try arguments.fields([])
        default: throw ConnectFailure.responseMalformed
        }
        let expired = timestamp > now + 5 || expiry <= now
        let status = operation == "status" && !expired
        return .object(["protocol_version": .string("olive-inference/1"), "request_id": v["request_id"], "job_id": v["job_id"],
            "result": status ? .object(["presets": .object(["fast": .bool(false), "normal": .bool(false), "max": .bool(false)]),
                                         "permission": .string("deny"), "busy": .bool(false)]) : .null,
            "error": status ? .null : .string(expired ? "expired_request" : "permission_denied")])
    }
    static func request(source: String, target: String, operation: String, job: String? = nil,
                        arguments: ConnectJSON = .object([:]), now: Int64 = Int64(Date().timeIntervalSince1970), id: String = UUID().uuidString.lowercased()) throws -> ConnectJSON {
        _ = try ConnectJSON.string(source).uuid(); _ = try ConnectJSON.string(target).uuid()
        _ = try ConnectJSON.string(id).uuid(); if let job { _ = try ConnectJSON.string(job).uuid() }
        guard ["start", "poll", "cancel", "status", "capabilities"].contains(operation) else { throw ConnectFailure.responseMalformed }
        if operation == "poll" { try arguments.fields(["after"]); _ = try arguments["after"].number(0...64000) }
        if operation == "status" || operation == "capabilities" || operation == "cancel" { try arguments.fields([]) }
        return .object(["protocol_version": .string("olive-inference/1"), "request_id": .string(operation == "start" ? job ?? id : id),
            "source_device_id": .string(source), "target_device_id": .string(target), "job_id": .string(job ?? id),
            "operation": .string(operation), "arguments": arguments, "timestamp": .int(now), "expires_at": .int(now + 120)])
    }
    static func startArguments(preset: String, messages: [(String, String)]) throws -> ConnectJSON {
        guard ["fast", "normal", "max"].contains(preset) else { throw ConnectFailure.capabilityUnavailable }
        guard (1...24).contains(messages.count), messages.last?.0 == "user" else { throw ConnectFailure.responseMalformed }
        var total = 0
        let items = try messages.map { role, content -> ConnectJSON in
            guard ["user", "assistant"].contains(role) else { throw ConnectFailure.responseMalformed }
            guard (1...16000).contains(content.utf8.count) else { throw ConnectFailure.inputTooLarge }
            total += content.utf8.count
            return .object(["role": .string(role), "content": .string(content)])
        }
        guard total <= 48000 else { throw ConnectFailure.inputTooLarge }
        let list = ConnectJSON.array(items)
        return .object(["preset": .string(preset), "messages": list, "input_fingerprint": .string(list.digest),
                        "max_tokens": .int(2048), "max_output_bytes": .int(64000), "seconds": .int(120)])
    }
    static func response(_ bytes: Data) throws -> ConnectJSON {
        let v = try ConnectJSON.decode(bytes)
        try v.fields(["protocol_version", "request_id", "job_id", "result", "error"])
        guard v["protocol_version"] == .string("olive-inference/1") else { throw ConnectFailure.protocolVersionUnsupported }
        _ = try v["request_id"].uuid(); _ = try v["job_id"].uuid()
        if v["error"] != .null {
            guard errors.contains(try v["error"].text()), v["result"] == .null else { throw ConnectFailure.responseMalformed }
            return v
        }
        let r = v["result"]
        if r.object?["presets"] != nil {
            try r.fields(["presets", "permission", "busy"])
            try r["presets"].fields(["fast", "normal", "max"])
            guard ["deny", "ask", "allow"].contains(try r["permission"].text()), r["busy"].boolean != nil,
                  r["presets"].object!.values.allSatisfy({ $0.boolean != nil }) else { throw ConnectFailure.responseMalformed }
        } else if r.object?["connect_version"] != nil {
            try r.fields(["connect_version", "permissions", "supported", "studio_scope"])
            let names: Set<String> = ["sync.tasks", "sync.calendar", "sync.reminders", "sync.chat", "files.receive", "files.send"]
            try r["permissions"].fields(names); try r["supported"].fields(names.union(["studio"]))
            guard r["connect_version"] == .int(1), r["studio_scope"] == .string("workspace"),
                  r["permissions"].object!.values.allSatisfy({ ["deny", "ask", "allow"].contains($0.string ?? "") }),
                  r["supported"].object!.values.allSatisfy({ $0.boolean != nil }) else { throw ConnectFailure.responseMalformed }
        } else {
            try r.fields(["state", "events", "error"])
            guard states.contains(try r["state"].text()), r["error"] == .null || r["error"].string.map(errors.contains) == true,
                  let events = r["events"].array, events.count <= 8 else { throw ConnectFailure.responseMalformed }
            for event in events {
                try event.fields(["sequence", "text"])
                _ = try event["sequence"].number(1...64000)
                guard (1...4096).contains(try event["text"].text().utf8.count) else { throw ConnectFailure.responseMalformed }
            }
        }
        return v
    }
    static func failure(_ code: String) -> ConnectFailure {
        switch code {
        case "permission_denied", "confirmation_required": .permissionDenied
        case "model_unavailable": .capabilityUnavailable
        case "busy": .resourceBusy
        case "rate_limited": .rateLimited
        case "input_too_large": .inputTooLarge
        case "output_limit": .outputLimit
        case "inference_failed": .inferenceFailed
        case "stream_invalid": .streamInvalid
        case "ledger_full": .requestLedgerFull
        case "cancelled": .requestCancelled
        case "generation_timeout", "expired_request": .requestTimeout
        case "device_unavailable": .peerOffline
        case "device_revoked": .deviceRevoked
        case "connection_lost", "request_indeterminate": .connectionLost
        default: .responseMalformed
        }
    }

    /// Keep recent complete turns within C7's input bounds. The full conversation
    /// remains visible; older context is omitted, never split or sent oversized.
    static func context(history: [(String, String)], user: String) -> [(String, String)] {
        var result = [("user", user)]
        var bytes = user.utf8.count
        var end = history.count
        while end >= 2, result.count + 2 <= 24 {
            let turn = Array(history[(end - 2)..<end])
            let size = turn.reduce(0) { $0 + $1.1.utf8.count }
            guard turn[0].0 == "user", turn[1].0 == "assistant",
                  turn.allSatisfy({ (1...16000).contains($0.1.utf8.count) }), bytes + size <= 48000 else { break }
            result.insert(contentsOf: turn, at: 0); bytes += size; end -= 2
        }
        return result
    }
}

struct InferenceAccumulator: Sendable {
    private(set) var sequence: Int64 = 0
    private(set) var text = ""
    private(set) var state = "queued"
    mutating func consume(_ result: ConnectJSON) throws {
        guard !InferenceWire.terminal.contains(state) else { return }
        guard let events = result["events"].array, let next = result["state"].string else { throw ConnectFailure.responseMalformed }
        for event in events {
            guard event["sequence"].integer == sequence + 1, let delta = event["text"].string,
                  text.utf8.count + delta.utf8.count <= 64000 else { throw ConnectFailure.responseMalformed }
            text += delta; sequence += 1
        }
        state = next
    }
}
