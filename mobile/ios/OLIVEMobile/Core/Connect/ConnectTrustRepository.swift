import Foundation
import CryptoKit

struct TrustedConnectPeer: Identifiable, Equatable, Sendable {
    let identity: ConnectPublicIdentity
    let displayName: String
    var id: String { identity.deviceID }
    var wire: ConnectJSON { .object(["identity": identity.wire, "display_name": .string(displayName)]) }
}

/// Public trust records and signed receipts only; private identity never enters a file.
@MainActor
final class ConnectTrustRepository {
    private let url: URL
    private(set) var peers: [TrustedConnectPeer] = []
    private var ledger: [String: ConnectJSON] = [:]
    private var available = true
    var isAvailable: Bool { available }
    var isPristine: Bool { available && peers.isEmpty && ledger.isEmpty }
    init(directory: URL = URL.applicationSupportDirectory.appendingPathComponent("Connect")) {
        url = directory.appendingPathComponent("trust-v1.json")
        do {
            if FileManager.default.fileExists(atPath: url.path) {
                let bytes = try Data(contentsOf: url)
                let v = try ConnectJSON.decode(bytes, limit: 4_000_000)
                try v.fields(["version", "peers", "ledger"])
                guard v["version"] == .int(1), let list = v["peers"].array, list.count <= 64,
                      let ledger = v["ledger"].object, ledger.count <= 1000 else { throw ConnectFailure.identityRecoveryRequired }
                peers = try list.map { p in
                    try p.fields(["identity", "display_name"])
                    return try TrustedConnectPeer(identity: ConnectPublicIdentity(p["identity"]), displayName: p["display_name"].text())
                }
                guard Set(peers.map(\.id)).count == peers.count else { throw ConnectFailure.identityRecoveryRequired }
                self.ledger = ledger
            }
        } catch { available = false; peers = [] }
    }
    private func save(peers: [TrustedConnectPeer], ledger: [String: ConnectJSON]) throws {
        guard available else { throw ConnectFailure.identityRecoveryRequired }
        let dir = url.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        var resource = URLResourceValues(); resource.isExcludedFromBackup = true
        var mutableDir = dir; try mutableDir.setResourceValues(resource)
        let bytes = ConnectJSON.object(["version": .int(1), "peers": .array(peers.map(\.wire)), "ledger": .object(ledger)]).canonical
        guard bytes.count <= 4_000_000 else { throw ConnectFailure.resourceBusy }
        try bytes.write(to: url, options: [.atomic, .completeFileProtection])
        self.peers = peers; self.ledger = ledger
    }
    func reserve(_ offer: PairingOffer) throws {
        guard peers.count < 64, ledger.count < 1000 else { throw ConnectFailure.resourceBusy }
        guard ledger[offer.sessionID] == nil, !peers.contains(where: { $0.id == offer.identity.deviceID || $0.identity.publicKey == offer.identity.publicKey }) else { throw ConnectFailure.pairingAlreadyKnown }
        var next = ledger; next[offer.sessionID] = .object(["state": .string("pending")])
        try save(peers: peers, ledger: next)
    }
    func recordConfirmation(offer: PairingOffer, reply: PairingOffer, receipt: Data) throws {
        guard ledger[offer.sessionID]?["state"] == .string("pending") else { throw ConnectFailure.pairingInterrupted }
        var next = ledger
        next[offer.sessionID] = .object(["state": .string("confirmed"), "offer": offer.wire, "reply": reply.wire,
            "receipt": .string(receipt.base64EncodedString())])
        try save(peers: peers, ledger: next)
    }
    func commit(offer: PairingOffer, peerReceipt: Data) throws {
        guard let record = ledger[offer.sessionID], record["state"] == .string("confirmed"), record["offer"] == offer.wire else { throw ConnectFailure.pairingInterrupted }
        let reply = try PairingOffer(record["reply"].canonical, now: offer.wire["created_at"].integer!)
        guard let localReceipt = Data(base64Encoded: try record["receipt"].text()),
              try Curve25519.Signing.PublicKey(rawRepresentation: reply.identity.publicKey).isValidSignature(localReceipt,
                for: PairingOffer.receiptMessage(offer: offer, reply: reply, deviceID: reply.identity.deviceID)),
              try Curve25519.Signing.PublicKey(rawRepresentation: offer.identity.publicKey).isValidSignature(peerReceipt,
                for: PairingOffer.receiptMessage(offer: offer, reply: reply, deviceID: offer.identity.deviceID)) else { throw ConnectFailure.pairingDenied }
        guard !peers.contains(where: { $0.id == offer.identity.deviceID }) else { throw ConnectFailure.pairingAlreadyKnown }
        var next = ledger; var r = record.object!; r["state"] = .string("completed"); r["peer_receipt"] = .string(peerReceipt.base64EncodedString())
        next[offer.sessionID] = .object(r)
        try save(peers: peers + [TrustedConnectPeer(identity: offer.identity, displayName: offer.name)], ledger: next)
    }
    var interruptedSessions: [String] { ledger.keys.filter { ledger[$0]?["state"] == .string("confirmed") }.sorted() }
    func completionCode(_ sid: String) throws -> String {
        guard let r = ledger[sid], r["state"] == .string("confirmed") || r["state"] == .string("completed") else { throw ConnectFailure.pairingInterrupted }
        let localID = try r["reply"]["identity"]["device_id"].uuid()
        var receipts = [localID: r["receipt"]]
        if r["peer_receipt"] != .null { receipts[try r["offer"]["identity"]["device_id"].uuid()] = r["peer_receipt"] }
        return String(decoding: ConnectJSON.object(["protocol": .string("olive-pairing-completion/1"), "offer": r["offer"], "reply": r["reply"], "receipts": .object(receipts)]).canonical, as: UTF8.self)
    }
    func importCompletion(_ data: Data) throws {
        let v = try ConnectJSON.decode(data, limit: 12288)
        try v.fields(["protocol", "offer", "reply", "receipts"])
        guard v["protocol"] == .string("olive-pairing-completion/1") else { throw ConnectFailure.protocolVersionUnsupported }
        let sid = try v["offer"]["session_id"].uuid()
        guard let saved = ledger[sid], saved["state"] == .string("confirmed"), saved["offer"] == v["offer"], saved["reply"] == v["reply"] else { throw ConnectFailure.pairingInterrupted }
        let localID = try saved["reply"]["identity"]["device_id"].uuid(), peerID = try saved["offer"]["identity"]["device_id"].uuid()
        try v["receipts"].fields([localID, peerID])
        guard v["receipts"][localID] == saved["receipt"], let receipt = Data(base64Encoded: try v["receipts"][peerID].text()) else { throw ConnectFailure.pairingDenied }
        let offer = try PairingOffer(saved["offer"].canonical, now: saved["offer"]["created_at"].integer!)
        try commit(offer: offer, peerReceipt: receipt)
    }
    func cancel(_ sid: String) throws {
        guard ledger[sid]?["state"] != .string("completed") else { return }
        var next = ledger; next[sid] = .object(["state": .string("cancelled")]); try save(peers: peers, ledger: next)
    }
    func unpair(_ id: String) throws {
        // Remove the pin from both current trust and historical receipt transcripts.
        let next = ledger.mapValues { r in
            r["offer"]["identity"]["device_id"] == .string(id) ? ConnectJSON.object(["state": .string("unpaired")]) : r
        }
        try save(peers: peers.filter { $0.id != id }, ledger: next)
    }
}
