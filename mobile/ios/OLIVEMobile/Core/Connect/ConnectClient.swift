import Foundation

/// No networking, credentials or request JSON in the foundation milestone.
protocol ConnectClient: Sendable {
    func pairedDevices() async throws -> [ConnectDevice]
}

protocol PairingService: Sendable {
    /// The exact public C4.1 offer bytes, not a home-grown PIN or credentials.
    func begin(publicOffer: Data) async throws
    func cancel() async
}

struct DisconnectedConnectClient: ConnectClient {
    func pairedDevices() async throws -> [ConnectDevice] { [] }
}

struct UnavailablePairingService: PairingService {
    func begin(publicOffer: Data) async throws { throw ConnectError.pairingNotImplemented }
    func cancel() async {}
}
