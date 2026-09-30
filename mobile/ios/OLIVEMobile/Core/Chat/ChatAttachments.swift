import Foundation
import CryptoKit
import ImageIO
import UniformTypeIdentifiers
import UIKit

/// Where an attachment came from. Internal provenance: shown as a title, never as an id.
struct ChatAttachmentProvenance: Codable, Equatable, Hashable, Sendable {
    /// photo | camera | file | note | draw
    let source: String
    let sourceID: String?
    let title: String?
    /// Note: edit time + content hash; Draw: document revision.
    let revision: String?
}

/// An app-owned, content-addressed copy. Removing it from a draft never touches the
/// original photo, file, note or drawing.
struct StoredChatAttachment: Codable, Equatable, Hashable, Sendable, Identifiable {
    var id: String { descriptor.id }
    let descriptor: ChatAttachmentDescriptor
    let provenance: ChatAttachmentProvenance
    let createdAt: Date
    var lastUsed: Date
    let pixelWidth: Int?
    let pixelHeight: Int?
    let pageCount: Int?

    var typeLabel: String {
        switch provenance.source {
        case "note": "Note"
        case "draw": "Drawing"
        default:
            switch descriptor.mime {
            case "application/pdf": "PDF"
            case "image/png": "PNG image"
            case "image/jpeg": "JPEG image"
            case "text/markdown": "Markdown"
            case "text/x-source": "Code"
            case "text/plain": "Text"
            default: descriptor.mime.hasSuffix("wordprocessingml.document") ? "Word document" : "File"
            }
        }
    }
    var symbol: String {
        switch provenance.source {
        case "note": "note.text"
        case "draw": "scribble.variable"
        default: descriptor.kind == "image" ? "photo" : descriptor.mime == "application/pdf" ? "doc.richtext" : "doc.text"
        }
    }
}

enum ChatAttachmentFailure: Error, Equatable, Sendable {
    case unsupported, tooLarge, unreadable, storage, noteTooLarge, drawingNotReady
    var message: String {
        switch self {
        case .unsupported: "This file type isn't supported."
        case .tooLarge: "This file is too large to attach."
        case .unreadable: "The file couldn't be read."
        case .storage: "Your iPhone doesn't have space to prepare this attachment."
        case .noteTooLarge: "This note is too large to attach."
        case .drawingNotReady: "An image in this drawing hasn't arrived on this iPhone yet. Try again in a moment."
        }
    }
}

/// A prepared, hashed file in the store's incoming folder, ready to commit.
struct PreparedAttachment: Sendable {
    let file: URL
    let descriptor: ChatAttachmentDescriptor
    let provenance: ChatAttachmentProvenance
    let pixelWidth: Int?
    let pixelHeight: Int?
    let pageCount: Int?
}

/// Content-addressed store for Chat attachments: `<sha256>.<ext>` plus a small
/// index. Files use the companion data protection class and are excluded from
/// backup (they are copies; the originals stay where they were).
@MainActor
final class ChatAttachmentStore {
    static let maximumTotal: Int64 = 1024 * 1024 * 1024
    let directory: URL
    private let index: ProtectedStore<[StoredChatAttachment]>
    private(set) var items: [String: StoredChatAttachment] = [:]
    private(set) var available = true

    init(directory: URL) {
        self.directory = directory
        index = ProtectedStore(url: directory.appendingPathComponent("attachments-v1.json"), maximumBytes: 2_000_000)
        do {
            try Self.prepare(directory)
            for item in try index.load() ?? [] where FileManager.default.fileExists(atPath: url(item.descriptor).path) { items[item.id] = item }
        } catch { available = false }
    }

    nonisolated static func prepare(_ directory: URL) throws {
        for folder in [directory, directory.appendingPathComponent("incoming", isDirectory: true)] {
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true,
                attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication])
            var url = folder; var values = URLResourceValues(); values.isExcludedFromBackup = true
            try url.setResourceValues(values)
        }
    }
    nonisolated static func incoming(_ directory: URL) -> URL {
        directory.appendingPathComponent("incoming", isDirectory: true).appendingPathComponent(UUID().uuidString.lowercased())
    }
    nonisolated static func fileExtension(_ mime: String) -> String {
        ["image/png": "png", "image/jpeg": "jpg", "application/pdf": "pdf", "text/plain": "txt", "text/markdown": "md",
         "text/x-source": "txt"][mime] ?? (mime.hasSuffix("wordprocessingml.document") ? "docx" : "bin")
    }
    func url(_ descriptor: ChatAttachmentDescriptor) -> URL {
        directory.appendingPathComponent(descriptor.id + "." + Self.fileExtension(descriptor.mime))
    }
    func item(_ id: String) -> StoredChatAttachment? { items[id] }
    var totalBytes: Int64 { items.values.reduce(0) { $0 + $1.descriptor.size } }

    /// Publish a prepared file under its content address. Identical content is stored once.
    func commit(_ prepared: PreparedAttachment) throws -> StoredChatAttachment {
        guard available else { throw ChatAttachmentFailure.storage }
        let target = url(prepared.descriptor)
        if FileManager.default.fileExists(atPath: target.path) {
            try? FileManager.default.removeItem(at: prepared.file)
        } else {
            guard totalBytes + prepared.descriptor.size <= Self.maximumTotal else { throw ChatAttachmentFailure.storage }
            try FileManager.default.moveItem(at: prepared.file, to: target)
            try? (target as NSURL).setResourceValue(URLFileProtection.completeUntilFirstUserAuthentication, forKey: .fileProtectionKey)
        }
        var item = items[prepared.descriptor.id] ?? StoredChatAttachment(descriptor: prepared.descriptor, provenance: prepared.provenance,
            createdAt: Date(), lastUsed: Date(), pixelWidth: prepared.pixelWidth, pixelHeight: prepared.pixelHeight, pageCount: prepared.pageCount)
        item.lastUsed = Date()
        // Same bytes from a different source keep the first provenance; the turn records its own.
        items[item.id] = item
        try save()
        return StoredChatAttachment(descriptor: prepared.descriptor, provenance: prepared.provenance, createdAt: item.createdAt,
            lastUsed: item.lastUsed, pixelWidth: prepared.pixelWidth, pixelHeight: prepared.pixelHeight, pageCount: prepared.pageCount)
    }

    /// Remove copies no Chat turn, pending request or draft references, once they are a day old.
    /// Referenced attachments are never removed.
    @discardableResult
    func collect(referenced: Set<String>, now: Date = Date()) -> Int {
        var removed = 0
        for (id, item) in items where !referenced.contains(id) && now.timeIntervalSince(item.lastUsed) > 86_400 {
            try? FileManager.default.removeItem(at: url(item.descriptor))
            items[id] = nil; removed += 1
        }
        // Abandoned incoming preparations.
        let incoming = directory.appendingPathComponent("incoming", isDirectory: true)
        for file in (try? FileManager.default.contentsOfDirectory(at: incoming, includingPropertiesForKeys: [.contentModificationDateKey])) ?? [] {
            let date = (try? file.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
            if now.timeIntervalSince(date) > 3600 { try? FileManager.default.removeItem(at: file); removed += 1 }
        }
        if removed > 0 { try? save() }
        return removed
    }

    private func save() throws { try index.save(Array(items.values).sorted { $0.createdAt < $1.createdAt }) }
}

/// Attachment preparation runs off the main actor: normalising, hashing and copying
/// into the store's incoming folder. It never keeps an external file handle.
enum AttachmentPreparation {
    static let maximumSide = 4096
    static let maximumPixels = 24_000_000
    static let maximumImageBytes: Int64 = 20 * 1024 * 1024
    static let maximumTextBytes: Int64 = 2 * 1024 * 1024

    /// Display metadata only; never a path. Replaces characters the computer refuses.
    static func displayName(_ raw: String, fallback: String) -> String {
        let cleaned = String(raw.unicodeScalars.map { scalar -> Character in
            let bad = "/\\:<>\"|?*".unicodeScalars.contains(scalar) || [.control, .format, .surrogate, .privateUse, .unassigned, .lineSeparator, .paragraphSeparator].contains(scalar.properties.generalCategory)
            return bad ? "-" : Character(scalar)
        }).trimmingCharacters(in: .whitespacesAndNewlines)
        var name = cleaned == "." || cleaned == ".." || cleaned.isEmpty ? fallback : cleaned
        while name.utf8.count > 180 { name.removeLast() }
        return name.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func write(_ data: Data, directory: URL) throws -> URL {
        try ChatAttachmentStore.prepare(directory)
        let target = ChatAttachmentStore.incoming(directory)
        try data.write(to: target, options: [.withoutOverwriting, .completeFileProtectionUntilFirstUserAuthentication])
        return target
    }
    private static func sha256(_ data: Data) -> String { Data(SHA256.hash(data: data)).hex }

    // MARK: Images (Photo Library, Camera, image files, drawings)

    /// Normalise orientation into the pixels, strip metadata (EXIF, GPS, maker notes)
    /// and convert HEIC/HEIF/WebP to JPEG (or keep PNG when the source is PNG).
    /// Resolution is preserved up to 4096 px on the long side and 24 MP, the
    /// computer's image limits; aspect ratio is always kept.
    static func normalizedImage(_ data: Data) throws -> (data: Data, mime: String, width: Int, height: Int) {
        guard let source = CGImageSourceCreateWithData(data as CFData, [kCGImageSourceShouldCache: false] as CFDictionary),
              CGImageSourceGetCount(source) > 0,
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              let width = properties[kCGImagePropertyPixelWidth] as? Int, let height = properties[kCGImagePropertyPixelHeight] as? Int,
              width > 0, height > 0 else { throw ChatAttachmentFailure.unsupported }
        let longest = max(width, height)
        let areaScale = min(1, (Double(maximumPixels) / Double(width * height)).squareRoot())
        let side = max(1, min(maximumSide, Int(Double(longest) * areaScale)))
        let options: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true,
                                        kCGImageSourceThumbnailMaxPixelSize: side, kCGImageSourceShouldCacheImmediately: true]
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else { throw ChatAttachmentFailure.unreadable }
        let png = (CGImageSourceGetType(source) as String?) == UTType.png.identifier
        return try encode(image, png: png)
    }

    static func encode(_ image: CGImage, png: Bool) throws -> (data: Data, mime: String, width: Int, height: Int) {
        for quality in png ? [1.0] : [0.92, 0.85, 0.75] {
            let output = NSMutableData()
            let type = (png ? UTType.png : UTType.jpeg).identifier as CFString
            guard let destination = CGImageDestinationCreateWithData(output, type, 1, nil) else { throw ChatAttachmentFailure.unreadable }
            // No source properties are copied: pixels only, so no location or device metadata.
            CGImageDestinationAddImage(destination, image, png ? nil : [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary)
            guard CGImageDestinationFinalize(destination) else { throw ChatAttachmentFailure.unreadable }
            if Int64(output.length) <= maximumImageBytes { return (output as Data, png ? "image/png" : "image/jpeg", image.width, image.height) }
            if png { return try encode(image, png: false) }
        }
        throw ChatAttachmentFailure.tooLarge
    }

    static func photo(_ data: Data, source: String, name: String, directory: URL) throws -> PreparedAttachment {
        let image = try normalizedImage(data)
        let file = try write(image.data, directory: directory)
        let ext = image.mime == "image/png" ? "png" : "jpg"
        let descriptor = ChatAttachmentDescriptor(id: sha256(image.data), kind: "image", mime: image.mime, size: Int64(image.data.count),
            name: displayName(name, fallback: (source == "camera" ? "Camera photo." : "Photo.") + ext))
        return PreparedAttachment(file: file, descriptor: descriptor, provenance: ChatAttachmentProvenance(source: source, sourceID: nil, title: nil, revision: nil),
                                  pixelWidth: image.width, pixelHeight: image.height, pageCount: nil)
    }

    /// A camera capture: draw it upright (the orientation lives only in UIImage), then encode without metadata.
    static func camera(_ picture: UIImage, directory: URL) throws -> PreparedAttachment {
        let size = picture.size, longest = max(size.width, size.height)
        guard longest > 0 else { throw ChatAttachmentFailure.unreadable }
        let scale = min(1, Double(maximumSide) / longest, (Double(maximumPixels) / Double(size.width * size.height)).squareRoot())
        let format = UIGraphicsImageRendererFormat(); format.scale = 1; format.opaque = true
        let target = CGSize(width: (size.width * scale).rounded(), height: (size.height * scale).rounded())
        let upright = UIGraphicsImageRenderer(size: target, format: format).image { _ in picture.draw(in: CGRect(origin: .zero, size: target)) }
        guard let cg = upright.cgImage else { throw ChatAttachmentFailure.unreadable }
        let image = try encode(cg, png: false)
        let file = try write(image.data, directory: directory)
        let descriptor = ChatAttachmentDescriptor(id: sha256(image.data), kind: "image", mime: image.mime, size: Int64(image.data.count), name: "Camera photo.jpg")
        return PreparedAttachment(file: file, descriptor: descriptor, provenance: ChatAttachmentProvenance(source: "camera", sourceID: nil, title: nil, revision: nil),
                                  pixelWidth: image.width, pixelHeight: image.height, pageCount: nil)
    }

    // MARK: Files

    /// Classify by the system type (the extension is only a hint), then verify the bytes.
    static func documentMime(_ type: UTType?) -> String? {
        guard let type else { return nil }
        if type.conforms(to: .pdf) { return "application/pdf" }
        if let markdown = UTType("net.daringfireball.markdown"), type.conforms(to: markdown) { return "text/markdown" }
        if let docx = UTType("org.openxmlformats.wordprocessingml.document"), type.conforms(to: docx) {
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        }
        if type.conforms(to: .sourceCode) || type.conforms(to: .script) || type.conforms(to: .json) || type.conforms(to: .xml)
            || type.conforms(to: .yaml) || type.conforms(to: .commaSeparatedText) { return type.conforms(to: .commaSeparatedText) ? "text/plain" : "text/x-source" }
        if type.conforms(to: .plainText) || type.conforms(to: .text) { return "text/plain" }
        return nil
    }

    /// Copy the user's explicitly chosen file into the app-owned store while the
    /// security-scoped access lasts. `limit` comes from the computer's advertisement.
    static func file(_ url: URL, limit: (String, String) -> Int64?, directory: URL) throws -> PreparedAttachment {
        let access = url.startAccessingSecurityScopedResource()
        defer { if access { url.stopAccessingSecurityScopedResource() } }
        let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey, .contentTypeKey])
        guard url.isFileURL, values.isRegularFile == true, values.isSymbolicLink != true, let size = values.fileSize else { throw ChatAttachmentFailure.unreadable }
        let type = values.contentType ?? UTType(filenameExtension: url.pathExtension)
        let name = displayName(url.lastPathComponent, fallback: "Attachment")
        if let type, type.conforms(to: .image) {
            guard Int64(size) <= 64 * 1024 * 1024 else { throw ChatAttachmentFailure.tooLarge }
            let data = try Data(contentsOf: url, options: .mappedIfSafe)
            var prepared = try photo(data, source: "file", name: name, directory: directory)
            guard let maximum = limit("image", prepared.descriptor.mime), prepared.descriptor.size <= maximum else {
                try? FileManager.default.removeItem(at: prepared.file)
                throw ChatAttachmentFailure.tooLarge
            }
            // Keep the chosen name with the (possibly converted) extension.
            let base = (name as NSString).deletingPathExtension
            prepared = PreparedAttachment(file: prepared.file, descriptor: ChatAttachmentDescriptor(id: prepared.descriptor.id, kind: "image",
                mime: prepared.descriptor.mime, size: prepared.descriptor.size, name: displayName(base + (prepared.descriptor.mime == "image/png" ? ".png" : ".jpg"), fallback: "Image")),
                provenance: prepared.provenance, pixelWidth: prepared.pixelWidth, pixelHeight: prepared.pixelHeight, pageCount: nil)
            return prepared
        }
        guard let mime = documentMime(type) else { throw ChatAttachmentFailure.unsupported }
        guard let maximum = limit("document", mime) else { throw ChatAttachmentFailure.unsupported }
        let bound = mime.hasPrefix("text/") ? min(maximum, maximumTextBytes) : maximum
        guard Int64(size) <= bound else { throw ChatAttachmentFailure.tooLarge }
        try ChatAttachmentStore.prepare(directory)
        let target = ChatAttachmentStore.incoming(directory)
        do {
            guard FileManager.default.createFile(atPath: target.path, contents: nil, attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication]) else { throw ChatAttachmentFailure.storage }
            let input = try FileHandle(forReadingFrom: url); defer { try? input.close() }
            let output = try FileHandle(forWritingTo: target); defer { try? output.close() }
            var hash = SHA256(), count: Int64 = 0, head = Data()
            var decoder = mime.hasPrefix("text/") ? UTF8Validator() : nil
            while let chunk = try input.read(upToCount: 65536), !chunk.isEmpty {
                count += Int64(chunk.count)
                guard count <= bound else { throw ChatAttachmentFailure.tooLarge }
                if head.count < 8 { head.append(chunk.prefix(8 - head.count)) }
                if decoder != nil { guard decoder!.feed(chunk) else { throw ChatAttachmentFailure.unsupported } }
                hash.update(data: chunk); try output.write(contentsOf: chunk)
            }
            guard count > 0 else { throw ChatAttachmentFailure.unreadable }
            if decoder != nil { guard decoder!.finish() else { throw ChatAttachmentFailure.unsupported } }
            if mime == "application/pdf" { guard head.starts(with: Data("%PDF-".utf8)) else { throw ChatAttachmentFailure.unsupported } }
            if mime.hasSuffix("wordprocessingml.document") { guard head.starts(with: Data([0x50, 0x4B, 0x03, 0x04])) else { throw ChatAttachmentFailure.unsupported } }
            try output.synchronize()
            let pages = mime == "application/pdf" ? pdfPages(target) : nil
            return PreparedAttachment(file: target, descriptor: ChatAttachmentDescriptor(id: Data(hash.finalize()).hex, kind: "document", mime: mime, size: count, name: name),
                provenance: ChatAttachmentProvenance(source: "file", sourceID: nil, title: nil, revision: nil), pixelWidth: nil, pixelHeight: nil, pageCount: pages)
        } catch {
            try? FileManager.default.removeItem(at: target)
            throw error
        }
    }

    /// Page count only when cheap (CoreGraphics reads the page tree, not the content).
    static func pdfPages(_ url: URL) -> Int? {
        guard let document = CGPDFDocument(url as CFURL) else { return nil }
        return document.numberOfPages > 0 ? document.numberOfPages : nil
    }

    // MARK: OLIVE Notes and OLIVE Draw snapshots

    /// A frozen snapshot of the note's text as it is now. Later edits never change a sent turn.
    static func note(id: String, title: String, text: String, editedAt: String, directory: URL) throws -> PreparedAttachment {
        let body = Data(text.utf8)
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw ChatAttachmentFailure.unreadable }
        guard Int64(body.count) <= 192 * 1024 else { throw ChatAttachmentFailure.noteTooLarge }
        let digest = sha256(body)
        let file = try write(body, directory: directory)
        let name = displayName(title, fallback: "Note")
        return PreparedAttachment(file: file, descriptor: ChatAttachmentDescriptor(id: digest, kind: "note", mime: "text/markdown", size: Int64(body.count), name: name),
            provenance: ChatAttachmentProvenance(source: "note", sourceID: id, title: title, revision: editedAt + " · " + String(digest.prefix(12))),
            pixelWidth: nil, pixelHeight: nil, pageCount: nil)
    }

    /// A frozen PNG of the drawing at document resolution (bounded by the computer's
    /// image limits). The drawing itself is only read; editable history is never sent.
    static func drawing(id: String, title: String, revision: Int, ops: [DrawOp], width: Int, height: Int, background: String,
                        images: [String: CGImage], directory: URL) throws -> PreparedAttachment {
        guard Set(ops.compactMap(\.assetID)).isSubset(of: images.keys) else { throw ChatAttachmentFailure.drawingNotReady }
        let scale = min(1, Double(maximumSide) / Double(max(width, height)), (Double(maximumPixels) / Double(width * height)).squareRoot())
        guard let image = DrawRender.rasterize(ops, width: width, height: height, background: ops.effectiveBackground(background), jpeg: false,
                                               scale: scale, images: { images[$0] }) else { throw ChatAttachmentFailure.unreadable }
        let encoded = try encode(image, png: true)
        let file = try write(encoded.data, directory: directory)
        let name = displayName((title as NSString).deletingPathExtension + (encoded.mime == "image/png" ? ".png" : ".jpg"), fallback: "Drawing.png")
        return PreparedAttachment(file: file, descriptor: ChatAttachmentDescriptor(id: sha256(encoded.data), kind: "image", mime: encoded.mime,
            size: Int64(encoded.data.count), name: name),
            provenance: ChatAttachmentProvenance(source: "draw", sourceID: id, title: title, revision: "revision " + String(revision)),
            pixelWidth: encoded.width, pixelHeight: encoded.height, pageCount: nil)
    }
}

/// Streaming strict UTF-8 check (no NUL), for text attachments.
struct UTF8Validator {
    private var pending: [UInt8] = []
    mutating func feed(_ data: Data) -> Bool {
        var bytes = pending + data
        guard !bytes.contains(0) else { return false }
        // Keep an incomplete trailing sequence for the next chunk.
        var cut = bytes.count
        var back = 0
        while back < 3, cut - back - 1 >= 0 {
            let byte = bytes[cut - back - 1]
            if byte & 0xC0 == 0x80 { back += 1; continue }
            let need = byte >= 0xF0 ? 4 : byte >= 0xE0 ? 3 : byte >= 0xC0 ? 2 : 1
            if need > back + 1 { cut -= back + 1 }
            break
        }
        pending = Array(bytes[cut...])
        bytes.removeSubrange(cut...)
        return bytes.isEmpty || String(data: Data(bytes), encoding: .utf8) != nil
    }
    mutating func finish() -> Bool { pending.isEmpty }
}
