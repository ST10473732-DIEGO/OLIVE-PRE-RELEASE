import Foundation
import CryptoKit

struct ConnectPublicIdentity: Equatable, Sendable {
    let wire: ConnectJSON
    let deviceID: String
    let certificate: Data
    let publicKey: Data
    init(_ value: ConnectJSON) throws {
        try value.fields(["device_id", "algorithm", "key_version", "created_at", "certificate"])
        let idValue = try value["device_id"].uuid()
        deviceID = idValue
        guard value["algorithm"] == .string("olive-ed25519-x509/1"), value["key_version"] == .int(1) else { throw ConnectFailure.identityMismatch }
        let created = try value["created_at"].number(0...253402300799)
        let b64 = try value["certificate"].text()
        guard b64.utf8.count <= 2048, let der = Data(base64Encoded: b64), der.base64EncodedString() == b64 else { throw ConnectFailure.identityMismatch }
        var key = [UInt8](repeating: 0, count: 32)
        let valid = der.withUnsafeBytes { raw in
            idValue.withCString { id in olive_certificate_validate(raw.bindMemory(to: UInt8.self).baseAddress, der.count, id, created, &key) }
        }
        guard valid == 1 else { throw ConnectFailure.identityMismatch }
        certificate = der; publicKey = Data(key); wire = value
    }
    var fingerprint: String {
        let value = ConnectJSON.object(["algorithm": .string("olive-ed25519-x509/1"), "key_version": .int(1),
                                        "device_id": .string(deviceID), "public_key": .string(publicKey.hex)])
        return "C2/1:" + Data(SHA256.hash(data: value.canonical)).comparison
    }
}

struct ConnectIdentity: Sendable {
    let publicIdentity: ConnectPublicIdentity
    private let seed: Data
    init(publicIdentity: ConnectPublicIdentity, seed: Data) throws {
        let key = try Curve25519.Signing.PrivateKey(rawRepresentation: seed)
        guard key.publicKey.rawRepresentation == publicIdentity.publicKey else { throw ConnectFailure.identityRecoveryRequired }
        self.publicIdentity = publicIdentity; self.seed = seed
    }
    func sign(_ data: Data) throws -> Data { try Curve25519.Signing.PrivateKey(rawRepresentation: seed).signature(for: data) }
    func makeTLS(peer: ConnectPublicIdentity) throws -> ConnectTLS {
        try ConnectTLS(seed: seed, local: publicIdentity.certificate, peer: peer.certificate)
    }
    fileprivate var stored: Data {
        ConnectJSON.object(["version": .int(1), "identity": publicIdentity.wire, "seed": .string(seed.base64EncodedString())]).canonical
    }
    static func generate() throws -> Self {
        let key = Curve25519.Signing.PrivateKey()
        let id = UUID().uuidString.lowercased(), now = Int64(Date().timeIntervalSince1970)
        var der = [UInt8](repeating: 0, count: 1536)
        let count = key.rawRepresentation.withUnsafeBytes { raw in
            id.withCString { olive_certificate_create(raw.bindMemory(to: UInt8.self).baseAddress, $0, now, &der, der.count) }
        }
        guard count > 0 else { throw ConnectFailure.identityRecoveryRequired }
        let pub = try ConnectPublicIdentity(.object(["algorithm": .string("olive-ed25519-x509/1"),
            "device_id": .string(id), "key_version": .int(1), "created_at": .int(now),
            "certificate": .string(Data(der.prefix(Int(count))).base64EncodedString())]))
        return try Self(publicIdentity: pub, seed: key.rawRepresentation)
    }
    fileprivate static func restore(_ bytes: Data) throws -> Self {
        let v = try ConnectJSON.decode(bytes, limit: 4096)
        try v.fields(["version", "identity", "seed"])
        guard v["version"] == .int(1), let seed = Data(base64Encoded: try v["seed"].text()), seed.count == 32 else { throw ConnectFailure.identityRecoveryRequired }
        return try Self(publicIdentity: ConnectPublicIdentity(v["identity"]), seed: seed)
    }
}

actor ConnectIdentityStore {
    private let secrets: any SecretStore
    private var loadTask: Task<ConnectIdentity, Error>?
    private var resetting = false
    private var revision = UUID()
    init(secrets: any SecretStore = KeychainSecretStore()) { self.secrets = secrets }
    func load(allowCreation: Bool = true) async throws -> ConnectIdentity {
        guard !resetting else { throw ConnectFailure.identityRecoveryRequired }
        let token = revision
        let task = loadTask ?? Task { [secrets] in
            if let bytes = try await secrets.read(account: "mobile-identity-v1") {
                let restored = try ConnectIdentity.restore(bytes)
                let marker = Data(restored.publicIdentity.deviceID.utf8)
                if let saved = try await secrets.read(account: "mobile-identity-reservation-v1") {
                    guard saved == marker else { throw ConnectFailure.identityRecoveryRequired }
                } else {
                    // Migration from the first C9.2 development envelope, after key validation.
                    try await secrets.write(marker, account: "mobile-identity-reservation-v1")
                }
                return restored
            }
            guard allowCreation, try await secrets.read(account: "mobile-identity-reservation-v1") == nil else { throw ConnectFailure.identityRecoveryRequired }
            let identity = try ConnectIdentity.generate()
            // Reservation makes loss/interruption distinguishable from a fresh installation.
            try await secrets.write(Data(identity.publicIdentity.deviceID.utf8), account: "mobile-identity-reservation-v1")
            // Public and private material commit atomically as one device-only item.
            try await secrets.write(identity.stored, account: "mobile-identity-v1")
            return identity
        }
        loadTask = task
        do {
            let identity = try await task.value
            guard !resetting, revision == token else { throw ConnectFailure.identityRecoveryRequired }
            return identity
        } catch {
            if revision == token { loadTask = nil }
            throw ConnectFailure.identityRecoveryRequired
        }
    }
    /// Only called after explicit user confirmation and removal of local peer trust.
    func reset() async throws -> ConnectIdentity {
        guard !resetting else { throw ConnectFailure.identityRecoveryRequired }
        resetting = true; revision = UUID()
        defer { resetting = false }
        // Finish any initial Keychain write before replacing it.
        if let loadTask { _ = await loadTask.result }
        loadTask = nil
        let identity = try ConnectIdentity.generate()
        // An interrupted replacement leaves mismatched reservation/envelope and
        // fails closed on relaunch. Only another explicit reset can repair it.
        try await secrets.write(Data(identity.publicIdentity.deviceID.utf8), account: "mobile-identity-reservation-v1")
        try await secrets.write(identity.stored, account: "mobile-identity-v1")
        loadTask = Task { identity }
        return identity
    }
}

extension Data {
    var hex: String { map { String(format: "%02x", $0) }.joined() }
    var comparison: String { map { String(format: "%02X", $0) }.joined(separator: ":") }
}
