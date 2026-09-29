import Foundation
import CryptoKit

// Memory-BIO interop fixture only: stdin/stdout carry public messages and TLS records.
// No socket, app profile, Keychain, or automatic production confirmation is used.
func pairingFixture() throws {
    let offer = try PairingOffer(Data(readLine()!.utf8))
    let identity = try ConnectIdentity.generate()
    let reply = try offer.reply(identity: identity.publicIdentity, name: "OLIVE Swift fixture")
    print(String(decoding: reply.wire.canonical, as: UTF8.self)); fflush(stdout)
    let tls = try identity.makeTLS(peer: offer.identity)
    let binding = Data(SHA256.hash(data: ConnectJSON.array([offer.wire,reply.wire]).canonical))
    var confirmed = false
    while let line = readLine() {
        let input = try ConnectJSON.decode(Data(line.utf8))
        try tls.feed(Data(base64Encoded: input["incoming"].string!)!)
        let ready = try tls.handshake()
        var comparison = "", plain = Data()
        if ready {
            comparison = try tls.comparison(binding: binding)
            if input["confirm"] == .bool(true) && !confirmed {
                let receipt = try identity.sign(PairingOffer.receiptMessage(offer: offer, reply: reply, deviceID: identity.publicIdentity.deviceID))
                try tls.write(Data("OLIVE-CONFIRM/1:".utf8) + binding)
                try tls.write(Data(("\n" + receipt.base64EncodedString() + "\n").utf8)); confirmed = true
            }
            for _ in 0..<5 { let part = try tls.read(); if part.isEmpty { break }; plain.append(part) }
        }
        let out = try tls.drain()
        print(String(decoding: ConnectJSON.object(["outgoing": .string(out.base64EncodedString()), "ready": .bool(ready),
            "comparison": .string(comparison), "plain": .string(plain.base64EncodedString())]).canonical, as: UTF8.self)); fflush(stdout)
    }
}
if CommandLine.arguments[1] == "--pair-fixture" {
    try pairingFixture()
    exit(0)
}

if CommandLine.arguments[1] == "--notes-harness" {
    // OLIVE Notes: the real Swift JavaScriptCore host and SQLite store, driven by
    // tests/test_notes_phone_engine.py (JSON lines, same commands as the Node harness).
    let script = try String(contentsOfFile: CommandLine.arguments[2], encoding: .utf8)
    let directory = URL(fileURLWithPath: CommandLine.arguments[3], isDirectory: true)
    var host: NotesEngineHost?
    var events: [ConnectJSON] = []
    func boot(_ deviceID: String) throws {
        host = nil
        let started = try NotesEngineHost(database: try NotesDatabase(directory: directory), deviceID: deviceID, script: script)
        started.onEvent = { events.append($0) }
        host = started
    }
    func plain(_ value: ConnectJSON) -> Any {
        switch value {
        case .string(let text): return text
        case .int(let number): return Int(number)
        case .bool(let flag): return flag
        default: return NSNull()
        }
    }
    while let line = readLine() {
        let message = try ConnectJSON.decode(Data(line.utf8), limit: 16_000_000)
        let arguments = message["args"].array ?? []
        var reply: [String: ConnectJSON] = ["id": message["id"]]
        do {
            switch message["cmd"].string {
            case "boot", "restart": try boot(try arguments[0].text()); reply["result"] = .bool(true)
            case "call":
                guard let host else { throw NotesEngineHost.Failure.unavailable("not_booted") }
                reply["result"] = .string(try host.raw(try arguments[0].text(), arguments: arguments.dropFirst().map(plain)))
            case "failCommits": host?.database.failCommits = Int(arguments.first?.integer ?? 0); reply["result"] = .bool(true)
            case "events": reply["result"] = .array(events); events = []
            default: throw NotesEngineHost.Failure.unavailable("unknown_command")
            }
        } catch { reply["error"] = .string(String(describing: error)) }
        print(String(decoding: ConnectJSON.object(reply).canonical, as: UTF8.self)); fflush(stdout)
    }
    exit(0)
}

if CommandLine.arguments[1] == "--calendar-fixture" {
    let fixture = try ConnectJSON.decode(Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[2])), limit: 256000)
    for (index, row) in fixture["valid"].array!.enumerated() {
        try SyncPayload.validate(kind: "event", value: row["payload"])
        let points = try SyncCalendar.occurrences(row["payload"], after: SyncDate.parse(row["after"].text(), zoned: true), before: SyncDate.parse(row["before"].text(), zoned: true))
        let reduced = points.map { point in ConnectJSON.object(Dictionary(uniqueKeysWithValues: ["start", "end", "title", "occurrence_id"].map { ($0, point[$0]) })) }
        guard .array(reduced) == row["occurrences"] else { print("Calendar mismatch at fixture \(index): \(String(decoding: ConnectJSON.array(reduced).canonical, as: UTF8.self))"); exit(1) }
    }
    for (index, row) in fixture["invalid"].array!.enumerated() {
        var rejected = false
        do { try SyncPayload.validate(kind: "event", value: row) } catch { rejected = true }
        guard rejected else { print("Invalid calendar accepted: \(index)"); exit(1) }
    }
    print("Python/Swift calendar validation and occurrences matched")
    exit(0)
}

if CommandLine.arguments[1] == "--companion-fixture" {
    let fixture = try ConnectJSON.decode(Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[2])), limit: 256000)
    for value in fixture["records"].array! { _ = try SignedSyncRecord(value) }
    for value in fixture["invalid_records"].array! {
        var rejected = false
        do { _ = try SignedSyncRecord(value) } catch { rejected = true }
        precondition(rejected)
    }
    var studio: [String: ConnectJSON] = [:], files: [String: ConnectJSON] = [:]
    for (op, req) in fixture["studio"].object! {
        studio[op] = try StudioWire.request(source: req["source_device_id"].uuid(), target: req["target_device_id"].uuid(), operation: op,
            workspace: req["workspace_id"].string, revision: req["share_revision"].integer!, arguments: req["arguments"],
            id: req["request_id"].uuid(), now: req["timestamp"].integer!)
        precondition(studio[op]!.canonical == req.canonical)
    }
    for (op, packet) in fixture["files"].object! {
        let (req, bytes) = try FileWire.decode(Data(base64Encoded: packet.string!)!)
        let encoded = try FileWire.request(source: req["source_device_id"].uuid(), target: req["target_device_id"].uuid(),
            transfer: req["transfer_id"].uuid(), operation: op, arguments: req["arguments"], id: req["request_id"].uuid(), now: req["timestamp"].integer!)
        files[op] = .string(try FileWire.packet(encoded, bytes: bytes).base64EncodedString())
        precondition(files[op] == packet)
    }
    let identity = try ConnectIdentity.generate()
    let record = try SyncWire.author(kind: "task", payload: SyncPayload.task(title: "Swift authored fixture"), identity: identity)
    let request = try SyncWire.request(source: identity.publicIdentity.deviceID, target: "22222222-2222-4222-8222-222222222222", domain: "tasks", records: [record], cursor: 0)
    let output = ConnectJSON.object(["studio": .object(studio), "files": .object(files), "records": .array([record.wire]), "sync_request": request])
    try output.canonical.write(to: URL(fileURLWithPath: CommandLine.arguments[3]))
    print("Swift C5 signatures, C6 binary packets and C8 requests verified")
    exit(0)
}

let fixture = URL(fileURLWithPath: CommandLine.arguments[1])
let v = try ConnectJSON.decode(Data(contentsOf: fixture), limit: 200_000)
let offer = try PairingOffer(v["offer"].canonical, now: v["offer"]["created_at"].integer!)
let reply = try PairingOffer(v["reply"].canonical, now: v["offer"]["created_at"].integer!)
precondition(offer.identity.fingerprint == v["fingerprint"].string)
precondition(ConnectJSON.array([offer.wire, reply.wire]).digest == v["binding"].string)
precondition(String(decoding: PairingOffer.receiptMessage(offer: offer, reply: reply, deviceID: reply.identity.deviceID), as: UTF8.self) == v["receipt_message"].string)
var result: [String: ConnectJSON] = [:]
for name in ["start", "poll", "cancel", "status"] {
    let expected = v[name]
    let args: ConnectJSON
    if name == "start" {
        args = try InferenceWire.startArguments(preset: expected["arguments"]["preset"].text(),
            messages: expected["arguments"]["messages"].array!.map { (try $0["role"].text(), try $0["content"].text()) })
    } else { args = expected["arguments"] }
    let encoded = try InferenceWire.request(source: reply.identity.deviceID, target: offer.identity.deviceID, operation: name,
        job: expected["job_id"].text(), arguments: args, now: expected["timestamp"].integer!, id: expected["request_id"].text())
    precondition(encoded.canonical == expected.canonical)
    let frame = try ConnectFrame(kind: 9, payload: encoded.canonical).encode()
    precondition(frame.hex == v[name + "_frame"].string)
    result[name] = encoded
}
for name in ["response", "capabilities"] { result[name] = try InferenceWire.response(v[name].canonical) }
var rejections: [String: ConnectJSON] = [:]
for code in ["busy", "rate_limited", "model_unavailable", "unknown_request"] {
    _ = try InferenceWire.response(v["admission_errors"][code].canonical)
    let value = ConnectJSON.object(["protocol_version": .string("olive-inference/1"),
        "request_id": v["start"]["request_id"], "job_id": v["start"]["job_id"], "result": .null, "error": .string(code)])
    precondition(value.canonical == v["admission_errors"][code].canonical)
    let encoded = try ConnectFrame(kind: 10, payload: value.canonical).encode()
    precondition(encoded.hex == v["admission_error_frames"][code].string)
    rejections[code] = value
}
result["admission_errors"] = .object(rejections)
var clientReplies: [String: ConnectJSON] = [:]
for name in ["start", "poll", "cancel", "status"] {
    let request = v[name]
    clientReplies[name] = try InferenceWire.clientReply(request.canonical,
        local: request["target_device_id"].text(), peer: request["source_device_id"].text(), now: request["timestamp"].integer!)
}
result["client_replies"] = .object(clientReplies)
try ConnectJSON.object(result).canonical.write(to: URL(fileURLWithPath: CommandLine.arguments[2]))
print("Swift decoded Python C2/C3/C7 and independently encoded C7 requests byte-for-byte.")
