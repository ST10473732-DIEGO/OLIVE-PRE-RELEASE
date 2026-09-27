import Foundation

/// Small atomic, versioned app-owned stores. Keys remain exclusively in Keychain.
struct ProtectedStore<Value: Codable> {
    let url: URL
    let maximumBytes: Int
    private struct Envelope: Codable { let version: Int; let value: Value }
    func load() throws -> Value? {
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? maximumBytes + 1
        guard size <= maximumBytes else { throw ConnectFailure.localStorageUnavailable }
        let envelope = try JSONDecoder().decode(Envelope.self, from: Data(contentsOf: url))
        guard envelope.version == 1 else { throw ConnectFailure.localStorageUnavailable }
        return envelope.value
    }
    func save(_ value: Value) throws {
        let data = try JSONEncoder().encode(Envelope(version: 1, value: value))
        guard data.count <= maximumBytes else { throw ConnectFailure.localStorageUnavailable }
        var directory = url.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
            attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        var resources = URLResourceValues(); resources.isExcludedFromBackup = true
        try directory.setResourceValues(resources)
        try data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }
}
