import Foundation

enum ConnectFailure: String, Error, LocalizedError, Sendable, Codable {
    case discoveryUnavailable, localNetworkDenied, pairingDenied, pairingExpired
    case identityMismatch, certificateMismatch, protocolVersionUnsupported
    case capabilityUnavailable, permissionDenied, peerOffline, connectionLost
    case requestTimeout, requestCancelled, responseMalformed, resourceBusy, rateLimited
    case identityRecoveryRequired, pairingAlreadyKnown, pairingInterrupted
    case inputTooLarge, outputLimit, inferenceFailed, streamInvalid, requestLedgerFull
    case syncConflict, syncRevisionStale, syncPermissionDenied
    case fileTooLarge, fileHashMismatch, fileTransferInterrupted, fileTransferCancelled, fileSaveRequired
    case workspaceUnavailable, studioRevisionStale, studioOperationBusy
    case remotePermissionDenied
    case backgroundTaskUnavailable, backgroundTaskExpired, backgroundTaskCancelled, localStorageUnavailable
    var errorDescription: String? {
        switch self {
        case .remotePermissionDenied: "Enable this capability for this iPhone on your computer. Workspace permissions are managed per share."
        case .syncConflict: "These records have conflicting changes. Review before saving."
        case .syncRevisionStale: "This record changed. Reload before saving."
        case .syncPermissionDenied: "Enable this sync domain on your computer."
        case .fileTooLarge: "Connect supports files up to 64 MiB."
        case .fileHashMismatch: "The file failed integrity verification."
        case .fileTransferInterrupted: "Transfer interrupted. Check its receipt before explicitly sending again."
        case .fileTransferCancelled: "File transfer cancelled."
        case .fileSaveRequired: "Transfer verified. Save or export it to Files."
        case .workspaceUnavailable: "The shared workspace or original operation is unavailable."
        case .studioRevisionStale: "The file or workspace changed. Reload and review your draft."
        case .studioOperationBusy: "A Studio operation is already active."
        case .backgroundTaskUnavailable: "Background continuation is unavailable. Keep OLIVE open to finish."
        case .backgroundTaskExpired: "iOS ended background execution. The operation was interrupted."
        case .backgroundTaskCancelled: "Background work was cancelled."
        case .localStorageUnavailable: "Local storage is unavailable or full. Existing data is preserved."
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
        case .rateLimited: "Remote AI request limit reached. Wait a minute, then send again."
        case .identityRecoveryRequired: "The saved identity could not be opened. It has been preserved."
        case .pairingAlreadyKnown: "This identity or pairing session is already known."
        case .pairingInterrupted: "Pairing was interrupted. No new trust was granted."
        case .inputTooLarge: "This message is too long. Shorten it and send again."
        case .outputLimit: "The answer reached the response size limit. Try a smaller request."
        case .inferenceFailed: "The computer’s model could not finish this request. Try again or choose another role."
        case .streamInvalid: "The computer’s response stream was interrupted or invalid."
        case .requestLedgerFull: "The computer’s Connect request history is full. Check Devices on the computer."
        }
    }
}
