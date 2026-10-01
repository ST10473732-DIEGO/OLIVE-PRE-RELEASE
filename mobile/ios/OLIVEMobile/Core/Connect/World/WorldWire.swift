import Foundation
import CryptoKit

/// OLIVE Connect World (olive-world/1): the relay rendezvous wire and route
/// credentials. Source of truth: olive/world/wire.py (vectors in
/// tests/fixtures/world_vectors_v1.json). World is a transport beneath OLIVE
/// Connect: after rendezvous the relay forwards the phone's own pinned TLS 1.3
/// bytes. The route credential only lets the relay join two connections; it
/// grants no OLIVE authority.
enum WorldWire {
    static let name = "olive-world/1"
    static let subprotocol = "olive-world.1"
    static let path = "/olive-world/1"
    static let context = Data("olive-connect-world/v1".utf8)
    /// Tunnel messages this phone sends; the relay refuses more than `maxMessage`.
    static let chunk = 65536
    static let maxMessage = 262144
    static let closeNames: [Int: String] = [
        1000: "normal", 1001: "going_away", 4000: "protocol_error", 4001: "unsupported_version",
        4002: "hello_timeout", 4003: "replaced", 4004: "peer_left", 4005: "rate_limited",
        4006: "too_large", 4007: "peer_unavailable", 4008: "capacity", 4009: "idle_timeout",
    ]

    /// HKDF-SHA256(route_secret, salt = context, info = "relay-credential"), 32 bytes.
    static func relayCredential(routeSecret: Data) throws -> Data {
        guard routeSecret.count == 32 else { throw WorldFailure.notProvisioned }
        let key = HKDF<SHA256>.deriveKey(inputKeyMaterial: SymmetricKey(data: routeSecret), salt: context,
                                         info: Data("relay-credential".utf8), outputByteCount: 32)
        return key.withUnsafeBytes { Data($0) }
    }

    /// The phone's hello: canonical JSON, byte-identical to Python's json.dumps(sort_keys=True).
    static func hello(route: Data, credential: Data) throws -> String {
        guard route.count == 16, credential.count == 32 else { throw WorldFailure.notProvisioned }
        let value = ConnectJSON.object(["v": .int(1), "role": .string("phone"),
                                        "route": .string(route.hex), "credential": .string(credential.hex)])
        return String(decoding: value.canonical, as: UTF8.self)
    }

    enum Event: String { case waiting, paired }
    static func event(_ text: String) throws -> Event {
        let value = try ConnectJSON.decode(Data(text.utf8), limit: 256)
        try value.fields(["v", "event"])
        guard value["v"] == .int(1), let name = value["event"].string, let event = Event(rawValue: name) else {
            throw WorldFailure.relayProtocol
        }
        return event
    }

    /// wss:// with normal system trust. A DEBUG build may opt into a plaintext ws://
    /// relay on loopback or a private LAN address for the Mac test host only.
    static func relayURL(_ text: String, allowTestPlaintext: Bool = false) throws -> URL {
        guard text.utf8.count <= 256, text == text.trimmingCharacters(in: .whitespacesAndNewlines),
              let parts = URLComponents(string: text), let scheme = parts.scheme, let host = parts.host, !host.isEmpty,
              parts.user == nil, parts.password == nil, parts.query == nil, parts.fragment == nil,
              !text.contains("%") else { throw WorldFailure.relayNotConfigured }
        if scheme == "ws" {
            guard allowTestPlaintext, isLocal(host) else { throw WorldFailure.relayNotConfigured }
        } else if scheme != "wss" {
            throw WorldFailure.relayNotConfigured
        }
        if let port = parts.port, !(1...65535).contains(port) { throw WorldFailure.relayNotConfigured }
        var result = parts
        if result.path.isEmpty || result.path == "/" { result.path = path }
        guard result.path.range(of: #"^/[A-Za-z0-9/._~-]{0,127}$"#, options: .regularExpression) != nil,
              let url = result.url else { throw WorldFailure.relayNotConfigured }
        return url
    }

    static func isLocal(_ host: String) -> Bool {
        if host == "localhost" || host == "127.0.0.1" || host == "::1" { return true }
        let octets = host.split(separator: ".").compactMap { Int($0) }
        guard octets.count == 4, octets.allSatisfy({ (0...255).contains($0) }) else { return false }
        return octets[0] == 10 || (octets[0] == 172 && (16...31).contains(octets[1])) || (octets[0] == 192 && octets[1] == 168)
            || (octets[0] == 169 && octets[1] == 254) || octets[0] == 127
    }

    // MARK: Provisioning (olive-connect/1 · connect.ping / "world")

    static func provisioningRequest(source: String, target: String, have: String?, now: Int64 = Int64(Date().timeIntervalSince1970)) -> ConnectJSON {
        .object(["request_id": .string(UUID().uuidString.lowercased()), "protocol_version": .string("olive-connect/1"),
                 "source_device_id": .string(source), "target_device_id": .string(target), "capability": .string("connect.ping"),
                 "operation": .string("world"), "arguments": .object(have.map { ["have": .string($0)] } ?? [:]),
                 "timestamp": .int(now), "expires_at": .int(now + 60)])
    }

    enum Provisioning: Equatable {
        case unavailable(reason: String)
        case current(routeID: String, relayURL: String)
        case provisioned(WorldCredential)
    }

    /// Strict parse of the computer's answer; unknown shapes are refused, never guessed.
    static func provisioning(_ response: ConnectJSON, peerID: String) throws -> Provisioning {
        if response["state"] == .string("rejected") {
            if response["error"] == .string("device_not_paired") { throw ConnectFailure.deviceRevoked }
            throw WorldFailure.unsupported
        }
        guard response["state"] == .string("completed") else { throw ConnectFailure.responseMalformed }
        let result = response["result"]
        guard result["world_protocol"] == .string(name) else { throw ConnectFailure.responseMalformed }
        switch result["state"].string {
        case "unavailable":
            try result.fields(["world_protocol", "state", "reason"])
            let reason = try result["reason"].text()
            guard ["disabled", "relay_not_configured", "secure_storage_unavailable"].contains(reason) else { throw ConnectFailure.responseMalformed }
            return .unavailable(reason: reason)
        case "current":
            try result.fields(["world_protocol", "state", "route_id", "relay_url"])
            return .current(routeID: try hex(result["route_id"], bytes: 16), relayURL: try result["relay_url"].text())
        case "provisioned":
            try result.fields(["world_protocol", "state", "route_id", "route_secret", "relay_url", "generation"])
            return .provisioned(WorldCredential(peerID: peerID, relayURL: try result["relay_url"].text(),
                routeID: try hex(result["route_id"], bytes: 16), routeSecret: try hex(result["route_secret"], bytes: 32),
                generation: try result["generation"].number(1...Int64(1) << 53)))
        default:
            throw ConnectFailure.responseMalformed
        }
    }

    private static func hex(_ value: ConnectJSON, bytes: Int) throws -> String {
        let text = try value.text()
        guard text.count == bytes * 2, text.allSatisfy({ "0123456789abcdef".contains($0) }) else { throw ConnectFailure.responseMalformed }
        return text
    }

    static func bytes(hex: String) -> Data? {
        guard hex.count % 2 == 0 else { return nil }
        var data = Data(capacity: hex.count / 2)
        var index = hex.startIndex
        while index < hex.endIndex {
            let next = hex.index(index, offsetBy: 2)
            guard let byte = UInt8(hex[index..<next], radix: 16) else { return nil }
            data.append(byte); index = next
        }
        return data
    }
}

/// World-specific reasons, kept apart from ConnectFailure (whose switches are exhaustive).
enum WorldFailure: String, Error, Sendable {
    case notProvisioned, relayNotConfigured, relayUnreachable, relayProtocol, computerOffline
    case replaced, rateLimited, unsupported, disabledOnComputer
    var message: String {
        switch self {
        case .notProvisioned: "This device hasn’t been set up for Connect World yet."
        case .relayNotConfigured: "World relay is not configured."
        case .relayUnreachable: "World relay is unreachable."
        case .relayProtocol: "World relay sent an invalid message."
        case .computerOffline: "Your computer is offline."
        case .replaced: "Another connection to this computer replaced this one."
        case .rateLimited: "World relay is busy. Trying again shortly."
        case .unsupported: "Your computer’s OLIVE doesn’t support Connect World yet."
        case .disabledOnComputer: "Connect World is off on your computer."
        }
    }
    static func from(closeCode: Int) -> WorldFailure {
        switch WorldWire.closeNames[closeCode] ?? "" {
        case "peer_unavailable", "peer_left": .computerOffline
        case "replaced": .replaced
        case "rate_limited", "capacity": .rateLimited
        case "protocol_error", "unsupported_version", "too_large": .relayProtocol
        default: .relayUnreachable
        }
    }
}

/// One paired computer's World route. The secret lives only in the Keychain.
struct WorldCredential: Equatable, Sendable {
    let peerID: String
    let relayURL: String
    let routeID: String
    let routeSecret: String
    let generation: Int64
    var wire: ConnectJSON {
        .object(["version": .int(1), "peer_id": .string(peerID), "relay_url": .string(relayURL), "route_id": .string(routeID),
                 "route_secret": .string(routeSecret), "generation": .int(generation)])
    }
    init(peerID: String, relayURL: String, routeID: String, routeSecret: String, generation: Int64) {
        self.peerID = peerID; self.relayURL = relayURL; self.routeID = routeID
        self.routeSecret = routeSecret; self.generation = generation
    }
    init(_ value: ConnectJSON) throws {
        try value.fields(["version", "peer_id", "relay_url", "route_id", "route_secret", "generation"])
        guard value["version"] == .int(1) else { throw ConnectFailure.responseMalformed }
        peerID = try value["peer_id"].uuid(); relayURL = try value["relay_url"].text()
        routeID = try value["route_id"].text(); routeSecret = try value["route_secret"].text()
        generation = try value["generation"].number(1...Int64(1) << 53)
        guard routeID.count == 32, routeSecret.count == 64 else { throw ConnectFailure.responseMalformed }
    }
    func hello() throws -> String {
        guard let route = WorldWire.bytes(hex: routeID), let secret = WorldWire.bytes(hex: routeSecret) else { throw WorldFailure.notProvisioned }
        return try WorldWire.hello(route: route, credential: WorldWire.relayCredential(routeSecret: secret))
    }
}
