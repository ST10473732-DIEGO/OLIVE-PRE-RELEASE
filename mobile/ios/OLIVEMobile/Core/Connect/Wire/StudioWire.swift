import Foundation
import CryptoKit

enum StudioWire {
    static let operations: Set<String> = ["workspaces", "tree", "read", "save", "build", "test", "run", "run_status", "run_cancel"]
    static let errors = Set("permission_denied confirmation_required workspace_unavailable workspace_not_shared file_not_found revision_conflict unsupported_file toolchain_unavailable build_failed test_failed run_failed busy cancelled connection_lost device_revoked invalid_request changed_duplicate expired_request request_indeterminate configuration_changed ledger_full".split(separator: " ").map(String.init))
    static func path(_ value: ConnectJSON) throws -> String {
        let s = try value.text()
        guard (1...500).contains(s.utf8.count), !s.contains("\\"), !s.contains(":"),
              !s.unicodeScalars.contains(where: { $0.value < 32 }),
              !s.split(separator: "/", omittingEmptySubsequences: false).contains(where: { ["", ".", ".."].contains($0) }) else { throw ConnectFailure.responseMalformed }
        return s
    }
    static func hash(_ value: ConnectJSON) throws -> String {
        let s = try value.text()
        guard s.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil else { throw ConnectFailure.responseMalformed }
        return s
    }
    static func bounded(_ value: ConnectJSON, _ max: Int) throws -> String {
        let s = try value.text()
        guard s.utf8.count <= max, !s.contains("\0") else { throw ConnectFailure.responseMalformed }
        return s
    }
    static func request(source: String, target: String, operation: String, workspace: String? = nil, revision: Int64 = 0,
                        arguments: ConnectJSON = .object([:]), id: String = UUID().uuidString.lowercased(), now: Int64 = Int64(Date().timeIntervalSince1970)) throws -> ConnectJSON {
        guard operations.contains(operation) else { throw ConnectFailure.capabilityUnavailable }
        for uuid in [source, target, id] { _ = try ConnectJSON.string(uuid).uuid() }
        if operation == "workspaces" { guard workspace == nil, revision == 0 else { throw ConnectFailure.responseMalformed } }
        else { guard let workspace, revision > 0 else { throw ConnectFailure.workspaceUnavailable }; _ = try ConnectJSON.string(workspace).uuid() }
        let fields: Set<String> = operation == "read" ? ["path"] : operation == "save" ? ["path", "text", "expected_hash"] : ["run_status", "run_cancel"].contains(operation) ? ["job_id"] : []
        try arguments.fields(fields)
        if fields.contains("path") { _ = try path(arguments["path"]) }
        if fields.contains("job_id") { _ = try arguments["job_id"].uuid() }
        if operation == "save" { _ = try hash(arguments["expected_hash"]); _ = try bounded(arguments["text"], 64000) }
        return .object(["protocol_version": .string("olive-studio/1"), "request_id": .string(id),
            "source_device_id": .string(source), "target_device_id": .string(target), "workspace_id": workspace.map(ConnectJSON.string) ?? .null,
            "share_revision": .int(revision), "operation": .string(operation), "arguments": arguments,
            "timestamp": .int(now), "expires_at": .int(now + 120)])
    }
    static func response(_ data: Data, request: ConnectJSON) throws -> ConnectJSON {
        let v = try ConnectJSON.decode(data, limit: 400000, allowDecimals: true)
        try v.fields(["protocol_version", "request_id", "result", "error"])
        guard v["protocol_version"] == .string("olive-studio/1"), v["request_id"] == request["request_id"] else { throw ConnectFailure.responseMalformed }
        if let error = v["error"].string {
            guard errors.contains(error), v["result"] == .null else { throw ConnectFailure.responseMalformed }
            return v
        }
        guard v["error"] == .null else { throw ConnectFailure.responseMalformed }
        let r = v["result"], op = try request["operation"].text()
        switch op {
        case "workspaces":
            try r.fields(["workspaces"])
            guard let list = r["workspaces"].array, list.count <= 8 else { throw ConnectFailure.responseMalformed }
            var seen = Set<String>()
            for w in list {
                try w.fields(["workspace_id", "display_name", "share_revision", "permissions"])
                guard seen.insert(try w["workspace_id"].uuid()).inserted else { throw ConnectFailure.responseMalformed }
                _ = try bounded(w["display_name"], 400); _ = try w["share_revision"].number(1...Int64.max)
                try w["permissions"].fields(Set(["view", "edit", "build", "test", "run", "debug"].map { "studio." + $0 }))
                guard w["permissions"].object!.values.allSatisfy({ ["allow", "ask", "deny"].contains($0.string ?? "") }) else { throw ConnectFailure.responseMalformed }
            }
        case "tree":
            try r.fields(["entries", "truncated"])
            guard r["truncated"].boolean != nil, let entries = r["entries"].array, entries.count <= 512, r["entries"].canonical.count <= 50000 else { throw ConnectFailure.responseMalformed }
            for e in entries {
                try e.fields(["path", "directory"])
                guard try path(e["path"]).split(separator: "/").count <= 8, e["directory"].boolean != nil else { throw ConnectFailure.responseMalformed }
            }
        case "read":
            try r.fields(["path", "text", "revision"])
            _ = try path(r["path"]); let text = try bounded(r["text"], 64000)
            guard r["path"] == request["arguments"]["path"], try hash(r["revision"]) == Data(SHA256.hash(data: Data(text.utf8))).hex else { throw ConnectFailure.responseMalformed }
        case "save":
            if r == .object(["state": .string("request_indeterminate")]) { return v }
            try r.fields(["state", "revision"])
            guard r["state"] == .string("saved"), try hash(r["revision"]) == Data(SHA256.hash(data: Data(try request["arguments"]["text"].text().utf8))).hex else { throw ConnectFailure.responseMalformed }
        default:
            let allowed: Set<String> = ["state", "job_id", "error", "exit_code", "output", "truncated", "tests", "diagnostics"]
            guard let object = r.object, Set(object.keys).isSubset(of: allowed),
                ["starting", "running", "completed", "failed", "cancelled", "cancelling", "request_indeterminate", "connection_lost"].contains(r["state"].string ?? "") else { throw ConnectFailure.responseMalformed }
            if let job = object["job_id"] { _ = try job.uuid(); guard job == (request["arguments"]["job_id"] == .null ? request["request_id"] : request["arguments"]["job_id"]) else { throw ConnectFailure.responseMalformed } }
            if r["error"] != .null { guard errors.contains(try r["error"].text()) else { throw ConnectFailure.responseMalformed } }
            if let output = object["output"] { _ = try bounded(output, 12000) }
            if let truncated = object["truncated"], truncated.boolean == nil { throw ConnectFailure.responseMalformed }
            if r["exit_code"] != .null, r["exit_code"].integer == nil { throw ConnectFailure.responseMalformed }
            if let diagnostics = object["diagnostics"] {
                guard let list = diagnostics.array, list.count <= 32, diagnostics.canonical.count <= 8100 else { throw ConnectFailure.responseMalformed }
                for d in list {
                    try d.fields(["path", "line", "severity", "message"])
                    if d["path"] != .string("") { _ = try path(d["path"]) }
                    _ = try d["line"].number(0...10000000); _ = try bounded(d["message"], 2200)
                    guard ["error", "warning"].contains(d["severity"].string ?? "") else { throw ConnectFailure.responseMalformed }
                }
            }
            if let tests = object["tests"] {
                try tests.fields(["passed", "failed", "skipped", "duration_seconds"])
                for k in ["passed", "failed", "skipped"] { _ = try tests[k].number(0...Int64.max) }
                let n: Double?
                if case .decimal(let token) = tests["duration_seconds"] { n = Double(token) }
                else { n = tests["duration_seconds"].integer.map(Double.init) }
                guard let n, n.isFinite, n >= 0 else { throw ConnectFailure.responseMalformed }
            }
        }
        return v
    }
    static func failure(_ code: String) -> ConnectFailure {
        switch code {
        case "device_revoked": .deviceRevoked
        case "permission_denied": .remotePermissionDenied
        case "revision_conflict", "configuration_changed": .studioRevisionStale
        case "busy": .studioOperationBusy
        case "cancelled": .requestCancelled
        case "connection_lost", "request_indeterminate": .connectionLost
        default: .workspaceUnavailable
        }
    }
}
