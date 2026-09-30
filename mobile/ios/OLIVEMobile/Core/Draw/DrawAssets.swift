import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import zlib

/// OLIVE Draw image assets on the phone: content-addressed (SHA-256) PNG/JPEG bytes.
///
/// Validation mirrors `olive/draw/assets.py`: the type comes from the content
/// (never a file name), dimensions come from the header and are bounded before
/// any decoder runs, then ImageIO checks the structure (a bounded thumbnail
/// decode, so a decompression bomb never allocates its full size).
///
/// Import mirrors the desktop renderer's `normalizeImage`: decode with EXIF
/// orientation applied, convert to sRGB, re-encode at the size it will occupy
/// on the canvas (PNG for PNG sources, JPEG 95 % otherwise) with no metadata
/// (EXIF, GPS, TIFF, IPTC, XMP are never copied). The original photo/file is not
/// kept or referenced; only the canonical bytes are.
enum DrawAssets {
    struct Failure: Error, Equatable, CustomStringConvertible {
        let code: String   // invalid_image, unsupported_image, image_too_large, checksum_mismatch
        init(_ code: String) { self.code = code }
        var description: String { code }
    }

    struct Info: Equatable, Sendable { let assetID: String; let mime: String; let width: Int; let height: Int }

    private static let png: [UInt8] = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]
    /// Every JPEG start-of-frame marker (C4/C8/CC are other segment types).
    private static let sof: Set<UInt8> = [0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF]

    /// (mime, width, height) from a PNG or JPEG header, or nil. Headers only.
    static func headerInfo(_ data: Data) -> (mime: String, width: Int, height: Int)? {
        let b = [UInt8](data.prefix(min(data.count, 1 << 20)))
        func be16(_ i: Int) -> Int { Int(b[i]) << 8 | Int(b[i + 1]) }
        func be32(_ i: Int) -> Int { Int(b[i]) << 24 | Int(b[i + 1]) << 16 | Int(b[i + 2]) << 8 | Int(b[i + 3]) }
        if b.count >= 24, Array(b[0..<8]) == png, Array(b[12..<16]) == Array("IHDR".utf8) {
            return ("image/png", be32(16), be32(20))
        }
        if b.count >= 3, b[0] == 0xFF, b[1] == 0xD8, b[2] == 0xFF {
            var index = 2
            while index + 9 < b.count {
                guard b[index] == 0xFF else { return nil }
                let marker = b[index + 1]
                if marker == 0xFF { index += 1; continue }                      // Fill byte.
                if marker == 0xD8 || marker == 0x01 || (0xD0...0xD7).contains(marker) { index += 2; continue }
                let length = be16(index + 2)
                if sof.contains(marker) { return ("image/jpeg", be16(index + 7), be16(index + 5)) }
                if length < 2 { return nil }
                index += 2 + length
            }
        }
        return nil
    }

    /// Validate asset bytes (from this phone's import or a peer); returns its info.
    static func validate(_ data: Data, expectedID: String? = nil) throws -> Info {
        guard !data.isEmpty else { throw Failure("invalid_image") }
        guard data.count <= DrawSpec.Limit.maxAssetBytes else { throw Failure("image_too_large") }
        guard let (mime, width, height) = headerInfo(data) else { throw Failure("unsupported_image") }
        let side = DrawSpec.Limit.maxAssetSide
        guard (1...side).contains(width), (1...side).contains(height), width * height <= DrawSpec.Limit.maxAssetPixels else {
            throw Failure("image_too_large")
        }
        let id = DrawText.sha256(data)
        if let expectedID, id != expectedID { throw Failure("checksum_mismatch") }
        try checkStructure(data, mime: mime, width: width, height: height)
        return Info(assetID: id, mime: mime, width: width, height: height)
    }

    /// Byte-level structure: every PNG chunk fits and has a correct CRC-32, IHDR
    /// first and IEND last; a JPEG ends with its EOI marker. (ImageIO alone
    /// decodes some truncated files.)
    static func wellFormed(_ data: Data, mime: String) -> Bool {
        let b = [UInt8](data)
        if mime == "image/jpeg" { return b.count > 4 && b[b.count - 2] == 0xFF && b[b.count - 1] == 0xD9 }
        guard b.count >= 8 + 12 * 3, Array(b[0..<8]) == png else { return false }
        var i = 8, first = true
        while i + 12 <= b.count {
            let length = Int(b[i]) << 24 | Int(b[i + 1]) << 16 | Int(b[i + 2]) << 8 | Int(b[i + 3])
            guard length <= b.count - i - 12 else { return false }
            let type = String(decoding: b[(i + 4)..<(i + 8)], as: UTF8.self)
            if first && type != "IHDR" { return false }
            first = false
            let stored = UInt32(b[i + 8 + length]) << 24 | UInt32(b[i + 9 + length]) << 16 | UInt32(b[i + 10 + length]) << 8 | UInt32(b[i + 11 + length])
            let crc = b[(i + 4)..<(i + 8 + length)].withContiguousStorageIfAvailable { crc32(0, $0.baseAddress, uInt($0.count)) }
                ?? Array(b[(i + 4)..<(i + 8 + length)]).withUnsafeBufferPointer { crc32(0, $0.baseAddress, uInt($0.count)) }
            guard UInt32(crc) == stored else { return false }
            i += 12 + length
            if type == "IEND" { return i == b.count }
        }
        return false
    }

    private static func checkStructure(_ data: Data, mime: String, width: Int, height: Int) throws {
        guard wellFormed(data, mime: mime) else { throw Failure("invalid_image") }
        let options = [kCGImageSourceShouldCache: false] as CFDictionary
        guard let source = CGImageSourceCreateWithData(data as CFData, options),
              CGImageSourceGetStatus(source) == .statusComplete, CGImageSourceGetCount(source) >= 1,
              let type = CGImageSourceGetType(source) as String?,
              type == (mime == "image/png" ? UTType.png.identifier : UTType.jpeg.identifier),
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
              properties[kCGImagePropertyPixelWidth] as? Int == width, properties[kCGImagePropertyPixelHeight] as? Int == height,
              CGImageSourceGetStatusAtIndex(source, 0) == .statusComplete else { throw Failure("invalid_image") }
        // A bounded decode of the whole stream proves the data is a decodable image.
        let thumb = [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceThumbnailMaxPixelSize: 64,
                     kCGImageSourceShouldCacheImmediately: true, kCGImageSourceCreateThumbnailWithTransform: false] as CFDictionary
        guard CGImageSourceCreateThumbnailAtIndex(source, 0, thumb) != nil else { throw Failure("invalid_image") }
    }

    /// Where an imported image goes (desktop assets.ts `placement`): natural size
    /// and centred when it fits, else scaled down (aspect kept) to fit within
    /// 90 % of the canvas and centred. Never upscaled.
    static func placement(imageWidth: Int, imageHeight: Int, canvasWidth: Int, canvasHeight: Int)
        -> (x: Double, y: Double, width: Int, height: Int) {
        var width = Double(imageWidth), height = Double(imageHeight)
        if imageWidth > canvasWidth || imageHeight > canvasHeight {
            let scale = min(Double(canvasWidth) * 0.9 / width, Double(canvasHeight) * 0.9 / height)
            width = max(1, (width * scale).rounded(.toNearestOrAwayFromZero))
            height = max(1, (height * scale).rounded(.toNearestOrAwayFromZero))
        }
        let x = ((Double(canvasWidth) - width) / 2 * 100).rounded(.toNearestOrAwayFromZero) / 100
        let y = ((Double(canvasHeight) - height) / 2 * 100).rounded(.toNearestOrAwayFromZero) / 100
        return (x, y, Int(width), Int(height))
    }

    struct Imported: Sendable {
        let data: Data
        let info: Info
        let x: Double, y: Double, width: Int, height: Int
    }

    /// Canonicalize a user-chosen image (Photos, Files or Camera) for a canvas.
    /// PNG, JPEG and HEIC/HEIF sources are read; the stored asset is PNG (for PNG
    /// sources, keeping transparency) or JPEG 95 % (for everything else).
    static func canonicalize(_ source: Data, canvasWidth: Int, canvasHeight: Int) throws -> Imported {
        guard !source.isEmpty else { throw Failure("invalid_image") }
        guard source.count <= DrawSpec.Limit.maxImportBytes else { throw Failure("image_too_large") }
        let options = [kCGImageSourceShouldCache: false] as CFDictionary
        guard let image = CGImageSourceCreateWithData(source as CFData, options), CGImageSourceGetCount(image) >= 1,
              let type = CGImageSourceGetType(image) as String?, let utType = UTType(type) else { throw Failure("unsupported_image") }
        let pngSource = utType.conforms(to: .png)
        guard pngSource || utType.conforms(to: .jpeg) || utType.conforms(to: .heic) || utType.conforms(to: .heif) else {
            throw Failure("unsupported_image")
        }
        if pngSource || utType.conforms(to: .jpeg) {
            // Same pre-decode gate as the desktop main process: header dimensions from the bytes.
            guard let header = headerInfo(source) else { throw Failure("unsupported_image") }
            guard header.width <= DrawSpec.Limit.maxImportSide, header.height <= DrawSpec.Limit.maxImportSide,
                  header.width * header.height <= DrawSpec.Limit.maxImportPixels else { throw Failure("image_too_large") }
        }
        guard let properties = CGImageSourceCopyPropertiesAtIndex(image, 0, nil) as? [CFString: Any],
              let pixelWidth = properties[kCGImagePropertyPixelWidth] as? Int, let pixelHeight = properties[kCGImagePropertyPixelHeight] as? Int,
              pixelWidth >= 1, pixelHeight >= 1 else { throw Failure("invalid_image") }
        guard pixelWidth <= DrawSpec.Limit.maxImportSide, pixelHeight <= DrawSpec.Limit.maxImportSide,
              pixelWidth * pixelHeight <= DrawSpec.Limit.maxImportPixels else { throw Failure("image_too_large") }
        // EXIF orientations 5–8 swap width and height.
        let orientation = (properties[kCGImagePropertyOrientation] as? Int) ?? 1
        let (orientedWidth, orientedHeight) = (5...8).contains(orientation) ? (pixelHeight, pixelWidth) : (pixelWidth, pixelHeight)
        let place = placement(imageWidth: orientedWidth, imageHeight: orientedHeight, canvasWidth: canvasWidth, canvasHeight: canvasHeight)
        guard place.width <= DrawSpec.Limit.maxAssetSide, place.height <= DrawSpec.Limit.maxAssetSide,
              place.width * place.height <= DrawSpec.Limit.maxAssetPixels else { throw Failure("image_too_large") }
        // Decode (downsampled to about the placed size, orientation applied) without
        // ever holding the full-resolution original when it is scaled down.
        let decode = [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true,
                      kCGImageSourceShouldCacheImmediately: true,
                      kCGImageSourceThumbnailMaxPixelSize: max(place.width, place.height)] as CFDictionary
        guard let decoded = CGImageSourceCreateThumbnailAtIndex(image, 0, decode) else { throw Failure("invalid_image") }
        let bytes = try encode(decoded, width: place.width, height: place.height, png: pngSource)
        guard bytes.count <= DrawSpec.Limit.maxAssetBytes else { throw Failure("image_too_large") }
        let info = try validate(bytes)
        return Imported(data: bytes, info: info, x: place.x, y: place.y, width: place.width, height: place.height)
    }

    /// Draw into an sRGB bitmap of exactly `width` × `height` and encode it with
    /// no metadata dictionary at all (nothing from the source is copied).
    static func encode(_ image: CGImage, width: Int, height: Int, png: Bool) throws -> Data {
        guard let space = CGColorSpace(name: CGColorSpace.sRGB),
              let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0, space: space,
                                      bitmapInfo: png ? CGImageAlphaInfo.premultipliedLast.rawValue : CGImageAlphaInfo.noneSkipLast.rawValue) else {
            throw Failure("image_too_large")
        }
        context.interpolationQuality = .high
        if !png { context.setFillColor(CGColor(srgbRed: 1, green: 1, blue: 1, alpha: 1)); context.fill(CGRect(x: 0, y: 0, width: width, height: height)) }
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        guard let flattened = context.makeImage() else { throw Failure("invalid_image") }
        return try encodeImage(flattened, png: png, quality: 0.95)
    }

    static func encodeImage(_ image: CGImage, png: Bool, quality: Double) throws -> Data {
        let output = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(output, (png ? UTType.png : UTType.jpeg).identifier as CFString, 1, nil) else {
            throw Failure("invalid_image")
        }
        let properties: [CFString: Any] = png ? [:] : [kCGImageDestinationLossyCompressionQuality: quality]
        CGImageDestinationAddImage(destination, image, properties as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { throw Failure("invalid_image") }
        return stripMetadata(output as Data, png: png)
    }

    /// ImageIO still writes its own small blocks (an EXIF colour-space/size IFD,
    /// an empty Photoshop IRB). Remove every JPEG APPn (except the JFIF APP0) and
    /// COM segment, and PNG eXIf/tEXt/zTXt/iTXt/tIME chunks, so an OLIVE asset
    /// carries pixels and colour space only (as the desktop's do).
    static func stripMetadata(_ data: Data, png: Bool) -> Data {
        let b = [UInt8](data)
        var out: [UInt8] = []
        out.reserveCapacity(b.count)
        if png {
            guard b.count > 8 else { return data }
            out.append(contentsOf: b[0..<8])
            var i = 8
            while i + 12 <= b.count {
                let length = Int(b[i]) << 24 | Int(b[i + 1]) << 16 | Int(b[i + 2]) << 8 | Int(b[i + 3])
                let end = i + 12 + length
                guard end <= b.count else { return data }
                let type = String(decoding: b[(i + 4)..<(i + 8)], as: UTF8.self)
                if !["eXIf", "tEXt", "zTXt", "iTXt", "tIME"].contains(type) { out.append(contentsOf: b[i..<end]) }
                i = end
            }
            return Data(out)
        }
        guard b.count > 4, b[0] == 0xFF, b[1] == 0xD8 else { return data }
        out.append(contentsOf: [0xFF, 0xD8])
        var i = 2
        while i + 4 <= b.count {
            guard b[i] == 0xFF else { return data }
            let marker = b[i + 1]
            if marker == 0xDA { out.append(contentsOf: b[i...]); return Data(out) }   // Scan data to the end, verbatim.
            let length = Int(b[i + 2]) << 8 | Int(b[i + 3])
            let end = i + 2 + length
            guard length >= 2, end <= b.count else { return data }
            let isJFIF = marker == 0xE0 && end - i >= 9 && Array(b[(i + 4)..<(i + 9)]) == Array("JFIF\0".utf8)
            if !(((0xE0...0xEF).contains(marker) && !isJFIF) || marker == 0xFE) { out.append(contentsOf: b[i..<end]) }
            i = end
        }
        return data
    }

    /// Decode stored canonical asset bytes for rendering. Orientation metadata
    /// is ignored (canonical assets have none; every device shows the same).
    static func decode(_ data: Data) -> CGImage? {
        let options = [kCGImageSourceShouldCache: true] as CFDictionary
        guard let source = CGImageSourceCreateWithData(data as CFData, options) else { return nil }
        return CGImageSourceCreateImageAtIndex(source, 0, [kCGImageSourceShouldCacheImmediately: true] as CFDictionary)
    }
}
