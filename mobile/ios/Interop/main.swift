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
try ConnectJSON.object(result).canonical.write(to: URL(fileURLWithPath: CommandLine.arguments[2]))
print("Swift decoded Python C2/C3/C7 and independently encoded C7 requests byte-for-byte.")
