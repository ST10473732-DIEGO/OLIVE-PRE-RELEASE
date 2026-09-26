import Foundation

// Domain projections only: these types are NOT wire codecs or trust validators.
// Source: olive/connect/{models,contracts,identity}.py. C9.2 must validate the
// complete bounded protocol before constructing authenticated peer records.
struct ConnectDeviceIdentity: Equatable, Sendable {
    let deviceID: UUID
    let certificateDER: Data
    let keyVersion: Int
    let createdAt: Date
    static let algorithm = "olive-ed25519-x509/1"
}

struct ConnectDevice: Identifiable, Equatable, Sendable {
    let id: UUID
    let displayName: String
    let connection: ConnectConnectionState
    let capabilities: Set<ConnectCapability>
}

// Exact C1 vocabulary. Online alone never grants permission.
enum ConnectConnectionState: String, Sendable {
    case offline, discovering, connecting, online
}

enum ConnectCapability: String, CaseIterable, Sendable {
    case ping = "connect.ping", deviceStatus = "device.status", chatMetadata = "chat.metadata.read"
    case chat, tasks, calendar, reminders, notifications
    case filesReceive = "files.receive", filesSend = "files.send", filesShared = "files.shared"
    case filesystemFull = "filesystem.full"
    case studioView = "studio.view", studioEdit = "studio.edit", studioBuild = "studio.build"
    case studioTest = "studio.test", studioDebug = "studio.debug", studioRun = "studio.run"
    case remoteModels = "models.remote", appsLaunch = "apps.launch", terminal
    case desktopControl = "desktop_control", softwareInstall = "software.install"
    case syncTasks = "sync.tasks", syncCalendar = "sync.calendar"
    case syncReminders = "sync.reminders", syncChat = "sync.chat"
}

/// Local presentation state, intentionally distinct from C1's peer state.
enum MobileConnectionState: Equatable {
    case notPaired
    var title: String { "Not connected" }
    var explanation: String { "Pair an OLIVE computer to chat. Pairing is coming in the next mobile update." }
}

enum ConnectError: Error, Equatable {
    case notPaired
    case pairingNotImplemented
}
