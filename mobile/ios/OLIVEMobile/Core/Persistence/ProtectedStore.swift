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
    /// Explicit recovery only. Preserve the exact unreadable bytes before a fresh
    /// atomic store is published. Refuse rather than evict prior recovery copies.
    func archiveAndReplace(with value: Value) throws {
        let manager = FileManager.default
        let folder = url.deletingLastPathComponent().appendingPathComponent("Recovery", isDirectory: true)
        try manager.createDirectory(at: folder, withIntermediateDirectories: true,
            attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        var protectedFolder = folder; var resources = URLResourceValues(); resources.isExcludedFromBackup = true
        try protectedFolder.setResourceValues(resources)
        let copies = try manager.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)
        guard copies.count < 4 else { throw ConnectFailure.localStorageUnavailable }
        if manager.fileExists(atPath: url.path) {
            let values = try url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey, .isSymbolicLinkKey])
            guard values.isRegularFile == true, values.isSymbolicLink != true,
                  let size = values.fileSize, size <= maximumBytes else { throw ConnectFailure.localStorageUnavailable }
            // Same-volume hard link preserves bytes without doubling a large store;
            // save() atomically replaces only the active directory entry.
            try manager.linkItem(at: url, to: folder.appendingPathComponent(UUID().uuidString + "-" + url.lastPathComponent))
        }
        try save(value)
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
