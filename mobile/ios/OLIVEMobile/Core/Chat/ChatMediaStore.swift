import Foundation
import CryptoKit
import ImageIO

enum ChatMediaFailure: Error, Equatable, Sendable {
    case storage, integrity, tooLarge
    var message: String {
        switch self {
        case .storage: "Your iPhone doesn't have space for this result. Free space, then tap Retry download."
        case .integrity: "The downloaded result failed verification and was discarded. Tap Retry download."
        case .tooLarge: "This result is larger than OLIVE keeps on this iPhone."
        }
    }
}

/// Generated images, speech and videos from the computer, stored app-private and
/// verified (SHA-256 and content type) before any viewer or player sees them.
/// Transfers resume from a `.part` file after a reconnect or relaunch; a partial
/// file is never presented. Files use the companion protection class and are
/// excluded from backup: the computer keeps the original artifact.
actor ChatMediaStore {
    static let maximumTotal: Int64 = 4 * 1024 * 1024 * 1024
    nonisolated let directory: URL
    private var active = Set<String>()

    init(directory: URL) { self.directory = directory }

    nonisolated func finalURL(_ artifact: ChatArtifact) -> URL { directory.appendingPathComponent(artifact.artifactID + "." + artifact.fileExtension) }
    nonisolated func partURL(_ artifact: ChatArtifact) -> URL { directory.appendingPathComponent(artifact.artifactID + ".part") }
    nonisolated func available(_ artifact: ChatArtifact) -> URL? {
        let url = finalURL(artifact)
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }
    nonisolated func received(_ artifact: ChatArtifact) -> Int64 {
        Int64((try? partURL(artifact).resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0)
    }

    private func prepare() throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true,
            attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
        var url = directory; var values = URLResourceValues(); values.isExcludedFromBackup = true
        try url.setResourceValues(values)
    }

    func totalBytes() -> Int64 {
        let files = (try? FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: [.fileSizeKey])) ?? []
        return files.reduce(0) { $0 + Int64((try? $1.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0) }
    }

    /// Download (or resume) one artifact. Generation is never repeated; only bytes move.
    func download(_ artifact: ChatArtifact, fetch: @Sendable (Int64) async throws -> Data,
                  progress: @Sendable (Int64) async -> Void) async throws -> URL {
        if let url = available(artifact) { return url }
        guard artifact.known else { throw ChatMediaFailure.integrity }
        guard !active.contains(artifact.artifactID) else { throw ConnectFailure.resourceBusy }
        active.insert(artifact.artifactID); defer { active.remove(artifact.artifactID) }
        try prepare()
        let part = partURL(artifact)
        var offset = received(artifact)
        if offset > artifact.size { try? FileManager.default.removeItem(at: part); offset = 0 }
        // Refuse before transferring when the result cannot be stored.
        let attributes = try FileManager.default.attributesOfFileSystem(forPath: directory.path)
        let free = (attributes[.systemFreeSize] as? NSNumber)?.int64Value ?? 0
        guard free >= artifact.size - offset + 64 * 1024 * 1024 else { throw ChatMediaFailure.storage }
        guard totalBytes() + artifact.size - offset <= Self.maximumTotal else { throw ChatMediaFailure.tooLarge }
        if !FileManager.default.fileExists(atPath: part.path) {
            guard FileManager.default.createFile(atPath: part.path, contents: nil,
                attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication]) else { throw ChatMediaFailure.storage }
        }
        let handle = try FileHandle(forWritingTo: part)
        do {
            try handle.seek(toOffset: UInt64(offset))
            while offset < artifact.size {
                try Task.checkCancellation()
                let data = try await fetch(offset)
                // Bytes go straight to disk; a large video is never held in memory.
                try handle.write(contentsOf: data)
                offset += Int64(data.count)
                await progress(offset)
            }
            try handle.synchronize(); try handle.close()
        } catch { try? handle.close(); throw error }
        guard try Self.verify(part, artifact: artifact) else {
            try? FileManager.default.removeItem(at: part)
            throw ChatMediaFailure.integrity
        }
        let final = finalURL(artifact)
        try FileManager.default.moveItem(at: part, to: final)
        return final
    }

    /// Hash first, then check the bytes really are the declared type.
    static func verify(_ url: URL, artifact: ChatArtifact) throws -> Bool {
        let handle = try FileHandle(forReadingFrom: url); defer { try? handle.close() }
        var hash = SHA256(), count: Int64 = 0, head = Data()
        while let data = try handle.read(upToCount: 1 << 20), !data.isEmpty {
            count += Int64(data.count); hash.update(data: data)
            if head.count < 16 { head.append(data.prefix(16 - head.count)) }
        }
        guard count == artifact.size, Data(hash.finalize()).hex == artifact.sha256 else { return false }
        return sniff(head, url: url, kind: artifact.kind)
    }

    static func sniff(_ head: Data, url: URL, kind: String) -> Bool {
        let bytes = [UInt8](head)
        switch kind {
        case "image":
            guard bytes.starts(with: [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]),
                  let source = CGImageSourceCreateWithURL(url as CFURL, nil),
                  let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
                  let width = properties[kCGImagePropertyPixelWidth] as? Int, let height = properties[kCGImagePropertyPixelHeight] as? Int
            else { return false }
            return (1...16384).contains(width) && (1...16384).contains(height)
        case "audio":
            return bytes.count >= 12 && Array(bytes[0..<4]) == Array("RIFF".utf8) && Array(bytes[8..<12]) == Array("WAVE".utf8)
        case "video":
            return bytes.count >= 8 && Array(bytes[4..<8]) == Array("ftyp".utf8)
        default:
            return false
        }
    }

    /// User-requested cleanup. Results referenced by visible Chat history are kept unless
    /// the user explicitly clears them; partial transfers are always removable.
    @discardableResult
    func clear(keeping: Set<String>) -> Int {
        var removed = 0
        for file in (try? FileManager.default.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil)) ?? [] {
            let id = file.deletingPathExtension().lastPathComponent
            if file.pathExtension == "part" || !keeping.contains(id) { try? FileManager.default.removeItem(at: file); removed += 1 }
        }
        return removed
    }
}
