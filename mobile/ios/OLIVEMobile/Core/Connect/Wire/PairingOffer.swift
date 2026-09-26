import Foundation
import Darwin

struct PairingOffer: Sendable {
    let wire: ConnectJSON
    let identity: ConnectPublicIdentity
    let sessionID: String
    let name: String
    let address: String
    let port: UInt16
    let expires: Int64
    init(_ data: Data, now: Int64 = Int64(Date().timeIntervalSince1970)) throws {
        let v = try ConnectJSON.decode(data, limit: 4096)
        try v.fields(["protocol", "session_id", "created_at", "expires_at", "identity", "endpoint", "display_name"])
        guard v["protocol"] == .string("olive-pairing-tls13/2") else { throw ConnectFailure.protocolVersionUnsupported }
        sessionID = try v["session_id"].uuid()
        let created = try v["created_at"].number(0...253402300799)
        expires = try v["expires_at"].number(0...253402300799)
        guard (1...120).contains(expires - created), created <= now + 5, expires > now else { throw ConnectFailure.pairingExpired }
        try v["endpoint"].fields(["address", "port"])
        address = try v["endpoint"]["address"].text()
        guard Self.localAddress(address) else { throw ConnectFailure.responseMalformed }
        port = UInt16(try v["endpoint"]["port"].number(1...65535))
        name = try v["display_name"].text()
        guard (1...100).contains(name.trimmingCharacters(in: .whitespacesAndNewlines).unicodeScalars.count),
              !name.unicodeScalars.contains(where: { $0.value < 32 }) else { throw ConnectFailure.responseMalformed }
        identity = try ConnectPublicIdentity(v["identity"]); wire = v
    }
    static func localAddress(_ s: String) -> Bool {
        var v4 = in_addr(), v6 = in6_addr()
        var buffer = [CChar](repeating: 0, count: Int(INET6_ADDRSTRLEN))
        if inet_pton(AF_INET, s, &v4) == 1 {
            guard inet_ntop(AF_INET, &v4, &buffer, socklen_t(buffer.count)) != nil, String(decoding: buffer.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }, as: UTF8.self) == s else { return false }
            let x = UInt32(bigEndian: v4.s_addr)
            return x >> 24 == 10 || x >> 24 == 127 || x >> 20 == 0xac1 || x >> 16 == 0xc0a8
        }
        if inet_pton(AF_INET6, s, &v6) == 1 {
            guard inet_ntop(AF_INET6, &v6, &buffer, socklen_t(buffer.count)) != nil, String(decoding: buffer.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }, as: UTF8.self) == s else { return false }
            return withUnsafeBytes(of: v6) { $0[0] & 0xfe == 0xfc } || s == "::1"
        }
        return false
    }
    func reply(identity: ConnectPublicIdentity, name: String) throws -> PairingOffer {
        var o = wire.object!; o["identity"] = identity.wire; o["display_name"] = .string(name)
        return try PairingOffer(ConnectJSON.object(o).canonical)
    }
    static func receiptMessage(offer: PairingOffer, reply: PairingOffer, deviceID: String) -> Data {
        ConnectJSON.object(["protocol": .string("olive-pairing-completion/1"), "session_id": .string(offer.sessionID),
            "transcript": .string(ConnectJSON.array([offer.wire, reply.wire]).digest), "device_id": .string(deviceID),
            "confirmed_before": .int(offer.expires)]).canonical
    }
}
