import Foundation
import CryptoKit
import Darwin

struct FileStaging: Sendable {
    let directory: URL
    func path(_ id: String, _ suffix: String) throws -> URL {
        _ = try ConnectJSON.string(id).uuid()
        guard ["part", "bin", "out"].contains(suffix) else { throw ConnectFailure.responseMalformed }
        return directory.appendingPathComponent(id + "." + suffix)
    }
    func prepare() throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
            attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        var url = directory; var values = URLResourceValues(); values.isExcludedFromBackup = true; try url.setResourceValues(values)
    }
    func clearExportCopies() throws {
        let exports = directory.appendingPathComponent("Exports", isDirectory: true)
        guard FileManager.default.fileExists(atPath: exports.path) else { return }
        let values = try exports.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
        guard values.isDirectory == true, values.isSymbolicLink != true else { throw ConnectFailure.localStorageUnavailable }
        for file in try FileManager.default.contentsOfDirectory(at: exports, includingPropertiesForKeys: [.isRegularFileKey, .isSymbolicLinkKey]) {
            let info = try file.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
            guard info.isRegularFile == true, info.isSymbolicLink != true else { continue }
            try FileManager.default.removeItem(at: file)
        }
    }
    func capacity(_ bytes: Int64) throws {
        let attributes = try FileManager.default.attributesOfFileSystem(forPath: directory.path)
        guard let free = attributes[.systemFreeSize] as? NSNumber, free.int64Value >= bytes + 16 * 1024 * 1024 else { throw ConnectFailure.localStorageUnavailable }
    }
    private func selectedHandle(_ url: URL) throws -> FileHandle {
        let descriptor = url.withUnsafeFileSystemRepresentation { name in
            guard let name else { return Int32(-1) }
            return Darwin.open(name, O_RDONLY | O_NOFOLLOW | O_NONBLOCK)
        }
        guard descriptor >= 0 else { throw ConnectFailure.localStorageUnavailable }
        var info = stat()
        guard fstat(descriptor, &info) == 0, (info.st_mode & S_IFMT) == S_IFREG else {
            Darwin.close(descriptor); throw ConnectFailure.responseMalformed
        }
        return FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
    }
    func digest(_ url: URL) throws -> (Int64, String) {
        let handle = try FileHandle(forReadingFrom: url); defer { try? handle.close() }
        var hash = SHA256(), count: Int64 = 0
        while let data = try handle.read(upToCount: 65536), !data.isEmpty {
            count += Int64(data.count); guard count <= FileWire.maximumFile else { throw ConnectFailure.fileTooLarge }; hash.update(data: data)
        }
        return (count, Data(hash.finalize()).hex)
    }
    func finalize(_ id: String, metadata: FileMetadata) throws {
        let partial = try path(id, "part"), final = try path(id, "bin")
        let handle = try FileHandle(forWritingTo: partial)
        do { try handle.synchronize(); try handle.close() }
        catch { try? handle.close(); throw error }
        // Match C6: verify the stored artifact, not only the streaming digest.
        let checked = try digest(partial)
        guard checked.0 == metadata.size, checked.1 == metadata.sha256 else { throw ConnectFailure.fileHashMismatch }
        try FileManager.default.linkItem(at: partial, to: final) // Exclusive publication; never overwrite.
    }
    func copySelection(_ url: URL, id: String) throws -> FileMetadata {
        let access = url.startAccessingSecurityScopedResource(); defer { if access { url.stopAccessingSecurityScopedResource() } }
        let properties = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
        guard url.isFileURL, properties.isRegularFile == true, properties.isSymbolicLink != true else { throw ConnectFailure.responseMalformed }
        guard let size = properties.fileSize, size <= FileWire.maximumFile else { throw ConnectFailure.fileTooLarge }
        try prepare(); try capacity(Int64(size))
        let destination = try path(id, "out")
        try Data().write(to: destination, options: [.withoutOverwriting, .completeFileProtectionUntilFirstUserAuthentication])
        do {
            let source = try selectedHandle(url); defer { try? source.close() }
            let target = try FileHandle(forWritingTo: destination); defer { try? target.close() }
            var count: Int64 = 0, hash = SHA256()
            while let data = try source.read(upToCount: 65536), !data.isEmpty {
                count += Int64(data.count); guard count <= FileWire.maximumFile else { throw ConnectFailure.fileTooLarge }
                hash.update(data: data); try target.write(contentsOf: data)
            }
            try target.synchronize()
            return try FileMetadata(name: url.lastPathComponent, size: count, sha256: Data(hash.finalize()).hex, mime: "application/octet-stream")
        } catch { try? FileManager.default.removeItem(at: destination); throw error }
    }
}
