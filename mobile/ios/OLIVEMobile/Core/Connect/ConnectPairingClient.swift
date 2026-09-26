import Foundation
import CryptoKit
import Network
import Observation

@MainActor @Observable
final class ConnectPairingClient {
    enum State: Equatable { case idle, connecting, comparing, waiting, completed, failed(String) }
    private(set) var state: State = .idle
    private(set) var comparison = ""
    private(set) var fingerprint = ""
    private(set) var candidateName = ""
    private(set) var diagnostic = "idle"
    private(set) var pairingSeconds: Double?
    private var offer: PairingOffer?
    private var reply: PairingOffer?
    private var identity: ConnectIdentity?
    private var tls: ConnectTLS?
    private var binding = Data()
    private var confirmed = false
    private var task: Task<Void, Never>?
    private var socket: ConnectSocket?
    private var generation = UUID()
    private let repository: ConnectTrustRepository
    private let identities: ConnectIdentityStore
    init(repository: ConnectTrustRepository, identities: ConnectIdentityStore) {
        self.repository = repository; self.identities = identities
    }
    func begin(_ data: Data) {
        guard task == nil else { return }
        let token = UUID(); generation = token
        let started = ContinuousClock.now; pairingSeconds = nil; diagnostic = "validating_offer"
        state = .connecting; confirmed = false; comparison = ""; fingerprint = ""
        task = Task {
            do {
                let offer = try PairingOffer(data)
                guard !offer.address.hasPrefix("127."), offer.address != "::1" else { throw ConnectFailure.peerOffline }
                let mayCreateIdentity = repository.isPristine
                try repository.reserve(offer)
                self.offer = offer
                diagnostic = "pairing_tcp · \(offer.address):\(offer.port)"
                let identity = try await identities.load(allowCreation: mayCreateIdentity)
                guard generation == token else { return }
                guard offer.identity.deviceID != identity.publicIdentity.deviceID else { throw ConnectFailure.identityMismatch }
                let reply = try offer.reply(identity: identity.publicIdentity, name: "OLIVE iPhone")
                self.identity = identity; self.reply = reply
                binding = Data(SHA256.hash(data: ConnectJSON.array([offer.wire, reply.wire]).canonical))
                tls = try identity.makeTLS(peer: offer.identity)
                candidateName = offer.name; fingerprint = offer.identity.fingerprint
                let socket = ConnectSocket(endpoint: .hostPort(host: .init(offer.address), port: .init(rawValue: offer.port)!))
                self.socket = socket
                try await socket.open()
                diagnostic = "pairing_tls"
                try await socket.send(ConnectFrame.length(reply.wire.canonical.count) + reply.wire.canonical)
                try await pump(socket: socket, offer: offer, reply: reply, token: token)
                pairingSeconds = started.duration(to: .now).secondsValue
                diagnostic = "paired"
                await socket.close()
            } catch {
                if generation == token {
                    diagnostic += " · " + (error as? ConnectFailure ?? .pairingInterrupted).rawValue
                    state = .failed((error as? ConnectFailure) == .peerOffline ? "Could not reach the temporary pairing listener. Keep Connect on and scan a fresh pairing code." : (error as? ConnectFailure ?? .pairingInterrupted).localizedDescription)
                    if let socket { await socket.close() }
                    // Preserve locally confirmed receipts for diagnosis/reconciliation;
                    // they do not create a trusted peer by themselves.
                }
            }
            if generation == token { tls = nil; socket = nil; task = nil; identity = nil }
        }
    }
    private func pump(socket: ConnectSocket, offer: PairingOffer, reply: PairingOffer, token: UUID) async throws {
        var incoming = Data(), proof = Data(), budget = 0, frames = 0
        let deadline = ContinuousClock.now.advanced(by: .seconds(max(0, Double(offer.expires) - Date().timeIntervalSince1970)))
        let handshakeDeadline = ContinuousClock.now.advanced(by: .seconds(5))
        var ready = false
        while generation == token && !Task.isCancelled {
            guard ContinuousClock.now < deadline, Date().timeIntervalSince1970 < Double(offer.expires) else { throw ConnectFailure.pairingExpired }
            guard let tls else { throw ConnectFailure.pairingInterrupted }
            try tls.feed(incoming)
            ready = try tls.handshake()
            if ready {
                if comparison.isEmpty { comparison = try tls.comparison(binding: binding); state = .comparing }
                for _ in 0..<5 {
                    let part = try tls.read(); if part.isEmpty { break }; proof.append(part)
                }
            } else if ContinuousClock.now >= handshakeDeadline { throw ConnectFailure.requestTimeout }
            // Match C4.1's request/reply pump, including empty records while users compare.
            let outgoing = try tls.drain()
            guard outgoing.count <= 32768 else { throw ConnectFailure.responseMalformed }
            try await socket.send(ConnectFrame.length(outgoing.count) + outgoing)
            // Validate prefix as it arrives, not only after both users confirm.
            let expected = Data("OLIVE-CONFIRM/1:".utf8) + binding
            guard proof.count <= expected.count + 90, expected.starts(with: proof.prefix(expected.count)) else { throw ConnectFailure.pairingDenied }
            if proof.count > expected.count { guard proof[expected.count] == 10 else { throw ConnectFailure.pairingDenied } }
            if proof.count == expected.count + 90 && confirmed {
                guard proof.last == 10,
                      let receipt = Data(base64Encoded: Data(proof.dropFirst(expected.count + 1).dropLast())), receipt.count == 64,
                      try Curve25519.Signing.PublicKey(rawRepresentation: offer.identity.publicKey).isValidSignature(receipt,
                         for: PairingOffer.receiptMessage(offer: offer, reply: reply, deviceID: offer.identity.deviceID)) else { throw ConnectFailure.pairingDenied }
                try repository.commit(offer: offer, peerReceipt: receipt)
                state = .completed; return
            }
            let header = try await socket.exact(4)
            let size = header.reduce(0) { ($0 << 8) | Int($1) }
            frames += 1; budget += size + 4
            guard size <= 32768, frames <= 3000, budget <= 262144 else { throw ConnectFailure.responseMalformed }
            incoming = try await socket.exact(size)
            try await Task.sleep(for: .milliseconds(100))
        }
        throw ConnectFailure.pairingInterrupted
    }
    func confirm(observed: String) {
        guard state == .comparing, !confirmed, let offer, let reply, let identity, let tls else { return }
        guard observed == comparison else { cancel(); state = .failed("The comparison values do not match."); return }
        do {
            guard Date().timeIntervalSince1970 < Double(offer.expires) else { throw ConnectFailure.pairingExpired }
            let receipt = try identity.sign(PairingOffer.receiptMessage(offer: offer, reply: reply, deviceID: identity.publicIdentity.deviceID))
            try repository.recordConfirmation(offer: offer, reply: reply, receipt: receipt)
            try tls.write(Data("OLIVE-CONFIRM/1:".utf8) + binding)
            try tls.write(Data(("\n" + receipt.base64EncodedString() + "\n").utf8))
            confirmed = true; state = .waiting
        } catch { cancel(); state = .failed((error as? ConnectFailure ?? .pairingInterrupted).localizedDescription) }
    }
    func cancel() {
        generation = UUID(); task?.cancel(); task = nil
        if let socket { Task { await socket.close() } }
        if let offer { try? repository.cancel(offer.sessionID) }
        socket = nil; tls = nil; identity = nil; offer = nil; reply = nil
        comparison = ""; fingerprint = ""; state = .idle
    }
}
