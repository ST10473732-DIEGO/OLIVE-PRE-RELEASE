import Foundation

struct InferenceWire {
    static let states: Set<String> = ["awaiting_approval", "queued", "starting", "streaming", "completed", "cancelled", "failed", "timed_out", "connection_lost", "revoked"]
    static let terminal = states.subtracting(["awaiting_approval", "queued", "starting", "streaming"])
    static let errors: Set<String> = ["permission_denied", "confirmation_required", "device_revoked", "device_unavailable", "model_unavailable", "busy", "rate_limited", "input_too_large", "output_limit", "generation_timeout", "cancelled", "connection_lost", "inference_failed", "invalid_request", "changed_duplicate", "expired_request", "unknown_request", "stream_invalid", "request_indeterminate", "ledger_full"]
    static func request(source: String, target: String, operation: String, job: String? = nil,
                        arguments: ConnectJSON = .object([:]), now: Int64 = Int64(Date().timeIntervalSince1970), id: String = UUID().uuidString.lowercased()) throws -> ConnectJSON {
        _ = try ConnectJSON.string(source).uuid(); _ = try ConnectJSON.string(target).uuid()
        _ = try ConnectJSON.string(id).uuid(); if let job { _ = try ConnectJSON.string(job).uuid() }
        guard ["start", "poll", "cancel", "status"].contains(operation) else { throw ConnectFailure.responseMalformed }
        if operation == "poll" { try arguments.fields(["after"]); _ = try arguments["after"].number(0...64000) }
        if operation == "status" || operation == "cancel" { try arguments.fields([]) }
        return .object(["protocol_version": .string("olive-inference/1"), "request_id": .string(operation == "start" ? job ?? id : id),
            "source_device_id": .string(source), "target_device_id": .string(target), "job_id": .string(job ?? id),
            "operation": .string(operation), "arguments": arguments, "timestamp": .int(now), "expires_at": .int(now + 120)])
    }
    static func startArguments(preset: String, messages: [(String, String)]) throws -> ConnectJSON {
        guard ["fast", "normal", "max"].contains(preset) else { throw ConnectFailure.capabilityUnavailable }
        guard (1...24).contains(messages.count), messages.last?.0 == "user" else { throw ConnectFailure.responseMalformed }
        var total = 0
        let items = try messages.map { role, content -> ConnectJSON in
            guard ["user", "assistant"].contains(role), (1...16000).contains(content.utf8.count) else { throw ConnectFailure.responseMalformed }
            total += content.utf8.count
            return .object(["role": .string(role), "content": .string(content)])
        }
        guard total <= 48000 else { throw ConnectFailure.responseMalformed }
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
        case "busy", "rate_limited": .resourceBusy
        case "cancelled": .requestCancelled
        case "generation_timeout", "expired_request": .requestTimeout
        case "device_unavailable": .peerOffline
        case "device_revoked", "connection_lost", "request_indeterminate": .connectionLost
        default: .responseMalformed
        }
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
