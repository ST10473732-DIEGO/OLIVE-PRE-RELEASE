import Foundation

struct BackgroundOperationRecord: Codable, Identifiable, Equatable, Sendable {
    enum State: String, Codable { case running, completed, interrupted, cancelled, failed, expired }
    let id: String
    let capability: String
    let peerID: String
    let label: String
    let protocolID: String
    let requestDigest: String
    let startedAt: Date
    var verifiedUnits: Int64 = 0
    var totalUnits: Int64?
    var state: State = .running
    // C6 has no offset resume; C7/C8 jobs are channel-owned. Never replay effects.
    private(set) var retrySafety = "explicitFreshRequestOnly"
    private(set) var desktopMayContinueIndependently = false

    mutating func reconcileAfterLaunch() {
        if state == .running { state = .interrupted }
    }
}

enum MobileLifecycleState: String {
    case foregroundConnected, foregroundConnecting, backgroundActiveTask
    case backgroundSuspendedExpected, pairedOffline, reconnecting, revoked, unpaired
}
