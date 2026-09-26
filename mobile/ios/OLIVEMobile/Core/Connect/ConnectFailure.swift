import Foundation

enum ConnectFailure: String, Error, LocalizedError, Sendable {
    case discoveryUnavailable, localNetworkDenied, pairingDenied, pairingExpired
    case identityMismatch, certificateMismatch, protocolVersionUnsupported
    case capabilityUnavailable, permissionDenied, peerOffline, connectionLost
    case requestTimeout, requestCancelled, responseMalformed, resourceBusy
    case identityRecoveryRequired, pairingAlreadyKnown, pairingInterrupted
    var errorDescription: String? {
        switch self {
        case .discoveryUnavailable: "Nearby discovery is unavailable."
        case .localNetworkDenied: "Allow Local Network access for OLIVE in Settings."
        case .pairingDenied: "Pairing was not confirmed."
        case .pairingExpired: "The pairing code expired. Create a new one on your computer."
        case .identityMismatch, .certificateMismatch: "The computer’s identity could not be verified."
        case .protocolVersionUnsupported: "This computer uses an unsupported Connect version."
        case .capabilityUnavailable: "Remote AI is unavailable on this computer."
        case .permissionDenied: "Enable Remote AI for this iPhone in your computer’s Devices screen."
        case .peerOffline: "Your computer is offline. Your draft is kept here."
        case .connectionLost: "Connection lost. The request will not be sent again automatically."
        case .requestTimeout: "The request timed out."
        case .requestCancelled: "Cancelled."
        case .responseMalformed: "Connect received an invalid message."
        case .resourceBusy: "Your computer is busy. Try again shortly."
        case .identityRecoveryRequired: "The saved identity could not be opened. It has been preserved."
        case .pairingAlreadyKnown: "This identity or pairing session is already known."
        case .pairingInterrupted: "Pairing was interrupted. No new trust was granted."
        }
    }
}
