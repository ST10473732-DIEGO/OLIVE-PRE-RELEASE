import Foundation
import CryptoKit

/// OLIVE Draw document model on the phone: a replicated set of immutable records.
///
/// This is a native Swift port of `olive/draw/document.py` (and the renderer's
/// `model.ts`). The limits below mirror the shared `drawing_schema.json`; a unit
/// test compares every value with the canonical desktop file, so the phone can
/// never silently drift from the desktop contract. Everything a peer or the
/// store hands us is untrusted: each field is validated, nothing is coerced.
enum DrawSpec {
    static let schemaVersion = 2
    static let operationsBySchema: [Int: [String]] = [
        1: ["stroke", "erase", "clear", "background"],
        2: ["stroke", "erase", "clear", "background", "image"],
    ]
    static let operations = Set(operationsBySchema[schemaVersion]!)
    static let recordKinds = ["create", "op", "visibility", "meta"]
    static let metaFields = ["title", "trashed"]
    static let tools = ["pen"]
    static let backgrounds = ["#ffffff", "transparent"]
    static let imageTypes = ["image/png", "image/jpeg"]
    enum Limit {
        static let minCanvas = 16
        static let maxCanvas = 8192
        static let maxCanvasPixels = 33_554_432
        static let maxOperations = 20_000
        static let maxRecords = 100_000
        static let maxPoints = 10_000
        static let maxOperationBytes = 400_000
        static let maxDocumentBytes = 48_000_000
        static let minWidth = 0.5
        static let maxWidth = 256.0
        static let maxTitleChars = 200
        static let maxDrawings = 5_000
        static let maxUndo = 1_000
        static let thumbnailMaxSide = 320
        static let thumbnailMaxBytes = 96_000
        static let maxImportBytes = 40_000_000
        static let maxImportSide = 16_384
        static let maxImportPixels = 50_000_000
        static let maxAssetBytes = 48_000_000
        static let maxAssetSide = 8192
        static let maxAssetPixels = 33_554_432
        static let assetChunkBytes = 600_000
    }
    /// Every limit by its name in drawing_schema.json (checked by a test).
    static let limitTable: [String: Double] = [
        "min_canvas": Double(Limit.minCanvas), "max_canvas": Double(Limit.maxCanvas),
        "max_canvas_pixels": Double(Limit.maxCanvasPixels), "max_operations": Double(Limit.maxOperations),
        "max_records": Double(Limit.maxRecords), "max_points": Double(Limit.maxPoints),
        "max_operation_bytes": Double(Limit.maxOperationBytes), "max_document_bytes": Double(Limit.maxDocumentBytes),
        "min_width": Limit.minWidth, "max_width": Limit.maxWidth, "max_title_chars": Double(Limit.maxTitleChars),
        "max_drawings": Double(Limit.maxDrawings), "max_undo": Double(Limit.maxUndo),
        "thumbnail_max_side": Double(Limit.thumbnailMaxSide), "thumbnail_max_bytes": Double(Limit.thumbnailMaxBytes),
        "max_import_bytes": Double(Limit.maxImportBytes), "max_import_side": Double(Limit.maxImportSide),
        "max_import_pixels": Double(Limit.maxImportPixels), "max_asset_bytes": Double(Limit.maxAssetBytes),
        "max_asset_side": Double(Limit.maxAssetSide), "max_asset_pixels": Double(Limit.maxAssetPixels),
        "asset_chunk_bytes": Double(Limit.assetChunkBytes),
    ]
    static let maxLamport: Int64 = 1 << 53
}

/// A fixed, content-free format error code (same codes as document.py).
struct DrawFormatError: Error, Equatable, CustomStringConvertible {
    let code: String
    init(_ code: String) { self.code = code }
    var description: String { code }
}

// MARK: - Text and patterns

enum DrawText {
    private static func matches(_ value: String, _ allowed: (UInt8) -> Bool, count: ClosedRange<Int>) -> Bool {
        let bytes = Array(value.utf8)
        return count.contains(bytes.count) && bytes.allSatisfy(allowed)
    }
    private static func hex(_ b: UInt8) -> Bool { (48...57).contains(b) || (97...102).contains(b) }
    private static func digit(_ b: UInt8) -> Bool { (48...57).contains(b) }

    static func isRecordID(_ value: String) -> Bool { matches(value, hex, count: 32...32) }
    static func isAssetID(_ value: String) -> Bool { matches(value, hex, count: 64...64) }
    /// document.py OP_ID: ^[a-z0-9]{8,32}$
    static func isOperationID(_ value: String) -> Bool {
        matches(value, { digit($0) || (97...122).contains($0) }, count: 8...32)
    }
    static func isUUID(_ value: String) -> Bool {
        let bytes = Array(value.utf8)
        guard bytes.count == 36 else { return false }
        for (index, byte) in bytes.enumerated() {
            if [8, 13, 18, 23].contains(index) { if byte != 45 { return false } } else if !hex(byte) { return false }
        }
        return true
    }
    static func isColor(_ value: String) -> Bool {
        let bytes = Array(value.utf8)
        return bytes.count == 7 && bytes[0] == 35 && bytes.dropFirst().allSatisfy(hex)
    }
    /// ^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$  (ASCII digits)
    static func isTimestamp(_ value: String) -> Bool {
        let b = Array(value.utf8)
        guard b.count >= 20, b.count <= 27, b.last == 90 else { return false }
        let shape: [UInt8?] = [nil, nil, nil, nil, 45, nil, nil, 45, nil, nil, 84, nil, nil, 58, nil, nil, 58, nil, nil]
        for (index, expected) in shape.enumerated() {
            if let expected { if b[index] != expected { return false } } else if !digit(b[index]) { return false }
        }
        if b.count == 20 { return true }
        guard b[19] == 46, b.count >= 22 else { return false }
        return b[20..<(b.count - 1)].allSatisfy(digit)
    }

    /// Python `str.isprintable()` semantics: Other (Cc, Cf, Cs, Co, Cn) and
    /// Separator (Zl, Zp, Zs) are not printable, except the ASCII space.
    private static func printable(_ scalar: Unicode.Scalar) -> Bool {
        if scalar == " " { return true }
        switch scalar.properties.generalCategory {
        case .control, .format, .surrogate, .privateUse, .unassigned, .lineSeparator, .paragraphSeparator, .spaceSeparator:
            return false
        default:
            return true
        }
    }

    /// document.py clean_title: control characters dropped (as spaces),
    /// whitespace collapsed, at most 200 code points.
    static func cleanTitle(_ value: String) -> String {
        var scalars = String.UnicodeScalarView()
        for scalar in value.unicodeScalars { scalars.append(printable(scalar) ? scalar : " ") }
        let collapsed = String(scalars).split(separator: " ", omittingEmptySubsequences: true).joined(separator: " ")
        return String(String.UnicodeScalarView(collapsed.unicodeScalars.prefix(DrawSpec.Limit.maxTitleChars)))
    }

    static func now() -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        formatter.timeZone = TimeZone(identifier: "UTC")
        return formatter.string(from: Date())
    }

    /// 128 random bits as 32 lowercase hex characters (record and operation id).
    static func randomID() -> String {
        var generator = SystemRandomNumberGenerator()
        return (0..<16).map { _ in String(format: "%02x", UInt8.random(in: 0...255, using: &generator)) }.joined()
    }

    static func sha256(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }

    /// Sanitized export file name (no path separators or control characters).
    static func exportName(_ title: String, ext: String) -> String {
        let forbidden = CharacterSet(charactersIn: "/\\:?%*|\"<>").union(.controlCharacters).union(.newlines)
        let cleaned = String(String.UnicodeScalarView(title.unicodeScalars.map { forbidden.contains($0) ? " " : $0 }))
            .split(separator: " ").joined(separator: " ")
            .trimmingCharacters(in: CharacterSet(charactersIn: ". "))
        let base = cleaned.isEmpty ? "Drawing" : String(cleaned.prefix(80))
        return base + "." + ext
    }
}

// MARK: - Numbers in JSON

extension ConnectJSON {
    /// A JSON number (never a boolean) as a Double.
    var drawNumber: Double? {
        switch self {
        case .int(let value): return Double(value)
        case .decimal(let token): return Double(token)
        default: return nil
        }
    }
    /// Shortest round-trip form; whole numbers are written without a fraction.
    static func drawNumber(_ value: Double) -> ConnectJSON {
        if value == value.rounded(), abs(value) < 1e15 { return .int(Int64(value)) }
        return .decimal("\(value)")
    }
}

/// Document coordinates are stored to 1/100 px and pressure to 1/1000.
enum DrawQuantize {
    static func coordinate(_ value: Double) -> Double { (value * 100).rounded(.toNearestOrAwayFromZero) / 100 }
    static func pressure(_ value: Double) -> Double { min(1, max(0, (value * 1000).rounded(.toNearestOrAwayFromZero) / 1000)) }
}

/// Width multiplier for a pen pressure sample (desktop render.ts pressureWidth):
/// renderedWidth = selectedWidth × (0.2 + 0.8 × pressure).
@inline(__always) func drawPressureWidth(_ pressure: Double) -> Double { 0.2 + 0.8 * pressure }

// MARK: - Operations

struct DrawColor: Equatable, Hashable, Sendable {
    let hex: String   // "#rrggbb", lowercase
    var red: Double { component(1) }
    var green: Double { component(3) }
    var blue: Double { component(5) }
    private func component(_ offset: Int) -> Double {
        let bytes = Array(hex.utf8)
        return Double(Int(String(decoding: bytes[offset..<(offset + 2)], as: UTF8.self), radix: 16) ?? 0) / 255
    }
}

enum DrawOp: Equatable, Sendable {
    case stroke(id: String, color: DrawColor, width: Double, opacity: Double, pressure: Bool, points: [Double])
    case erase(id: String, width: Double, points: [Double])
    case clear(id: String)
    case background(id: String, value: String)
    case image(id: String, assetID: String, x: Double, y: Double, width: Double, height: Double, opacity: Double)

    var id: String {
        switch self {
        case .stroke(let id, _, _, _, _, _), .erase(let id, _, _), .clear(let id), .background(let id, _),
             .image(let id, _, _, _, _, _, _): id
        }
    }
    var type: String {
        switch self {
        case .stroke: "stroke"
        case .erase: "erase"
        case .clear: "clear"
        case .background: "background"
        case .image: "image"
        }
    }
    var assetID: String? { if case .image(_, let asset, _, _, _, _, _) = self { asset } else { nil } }

    /// The lowest document schema that contains this operation type.
    var schema: Int { DrawSpec.operationsBySchema.keys.sorted().first { DrawSpec.operationsBySchema[$0]!.contains(type) } ?? 1 }

    func with(id newID: String) -> DrawOp {
        switch self {
        case .stroke(_, let c, let w, let o, let p, let pts): .stroke(id: newID, color: c, width: w, opacity: o, pressure: p, points: pts)
        case .erase(_, let w, let pts): .erase(id: newID, width: w, points: pts)
        case .clear: .clear(id: newID)
        case .background(_, let v): .background(id: newID, value: v)
        case .image(_, let a, let x, let y, let w, let h, let o): .image(id: newID, assetID: a, x: x, y: y, width: w, height: h, opacity: o)
        }
    }

    /// The canonical JSON body of this operation (validated shape).
    var json: ConnectJSON {
        let numbers: ([Double]) -> ConnectJSON = { .array($0.map(ConnectJSON.drawNumber)) }
        switch self {
        case .stroke(let id, let color, let width, let opacity, let pressure, let points):
            return .object(["type": .string("stroke"), "id": .string(id), "tool": .string("pen"), "color": .string(color.hex),
                            "width": .drawNumber(width), "opacity": .drawNumber(opacity), "pressure": .bool(pressure),
                            "points": numbers(points)])
        case .erase(let id, let width, let points):
            return .object(["type": .string("erase"), "id": .string(id), "width": .drawNumber(width), "points": numbers(points)])
        case .clear(let id):
            return .object(["type": .string("clear"), "id": .string(id)])
        case .background(let id, let value):
            return .object(["type": .string("background"), "id": .string(id), "value": .string(value)])
        case .image(let id, let asset, let x, let y, let width, let height, let opacity):
            return .object(["type": .string("image"), "id": .string(id), "asset_id": .string(asset), "x": .drawNumber(x),
                            "y": .drawNumber(y), "width": .drawNumber(width), "height": .drawNumber(height),
                            "opacity": .drawNumber(opacity)])
        }
    }

    /// Strict validation (document.py validate_operation) of the current schema.
    init(json value: ConnectJSON) throws {
        guard let object = value.object, let kind = object["type"]?.string else { throw DrawFormatError("invalid_operation") }
        guard DrawSpec.operations.contains(kind) else { throw DrawFormatError("unsupported_operation") }
        guard let id = object["id"]?.string, DrawText.isOperationID(id) else { throw DrawFormatError("invalid_operation") }
        let keys = Set(object.keys)
        let reach = Double(DrawSpec.Limit.maxCanvas * 3)
        func number(_ key: String, _ low: Double, _ high: Double) throws -> Double {
            guard let item = object[key], let n = item.drawNumber, n.isFinite, n >= low, n <= high else { throw DrawFormatError("invalid_number") }
            return n
        }
        func points(_ key: String, stride: Int) throws -> [Double] {
            guard let items = object[key]?.array, !items.isEmpty, items.count % stride == 0,
                  items.count / stride <= DrawSpec.Limit.maxPoints else { throw DrawFormatError("invalid_points") }
            var out = [Double](); out.reserveCapacity(items.count)
            for (index, item) in items.enumerated() {
                guard let n = item.drawNumber, n.isFinite else { throw DrawFormatError("invalid_number") }
                if stride == 3 && index % 3 == 2 { guard n >= 0, n <= 1 else { throw DrawFormatError("invalid_number") } }
                else { guard n >= -reach, n <= reach else { throw DrawFormatError("invalid_number") } }
                out.append(n)
            }
            return out
        }
        switch kind {
        case "stroke":
            guard keys == ["type", "id", "tool", "color", "width", "opacity", "pressure", "points"],
                  let tool = object["tool"]?.string, DrawSpec.tools.contains(tool),
                  let color = object["color"]?.string, DrawText.isColor(color) else { throw DrawFormatError("invalid_operation") }
            guard let pressure = object["pressure"]?.boolean else { throw DrawFormatError("invalid_operation") }
            let width = try number("width", DrawSpec.Limit.minWidth, DrawSpec.Limit.maxWidth)
            let opacity = try number("opacity", 0.01, 1)
            self = .stroke(id: id, color: DrawColor(hex: color), width: width, opacity: opacity, pressure: pressure,
                           points: try points("points", stride: pressure ? 3 : 2))
        case "erase":
            guard keys == ["type", "id", "width", "points"] else { throw DrawFormatError("invalid_operation") }
            let width = try number("width", DrawSpec.Limit.minWidth, DrawSpec.Limit.maxWidth)
            self = .erase(id: id, width: width, points: try points("points", stride: 2))
        case "clear":
            guard keys == ["type", "id"] else { throw DrawFormatError("invalid_operation") }
            self = .clear(id: id)
        case "background":
            guard keys == ["type", "id", "value"], let background = object["value"]?.string,
                  DrawSpec.backgrounds.contains(background) else { throw DrawFormatError("invalid_operation") }
            self = .background(id: id, value: background)
        default: // image
            guard keys == ["type", "id", "asset_id", "x", "y", "width", "height", "opacity"],
                  let asset = object["asset_id"]?.string, DrawText.isAssetID(asset) else { throw DrawFormatError("invalid_operation") }
            self = .image(id: id, assetID: asset, x: try number("x", -reach, reach), y: try number("y", -reach, reach),
                          width: try number("width", 1, reach), height: try number("height", 1, reach),
                          opacity: try number("opacity", 0.01, 1))
        }
    }

    /// Point count of a stroke/erase (for limits and summaries).
    var pointCount: Int {
        switch self {
        case .stroke(_, _, _, _, let pressure, let points): points.count / (pressure ? 3 : 2)
        case .erase(_, _, let points): points.count / 2
        default: 0
        }
    }
}

// MARK: - Records

/// The one total order every replica uses: (lamport, device, record_id). Never wall-clock time.
struct DrawKey: Comparable, Hashable, Sendable {
    let lamport: Int64
    let device: String
    let recordID: String
    static func < (a: DrawKey, b: DrawKey) -> Bool {
        if a.lamport != b.lamport { return a.lamport < b.lamport }
        if a.device != b.device { return a.device.utf8.lexicographicallyPrecedes(b.device.utf8) }
        return a.recordID.utf8.lexicographicallyPrecedes(b.recordID.utf8)
    }
    /// Text form (store.py sort_key): zero-padded so text order == tuple order.
    var text: String { String(format: "%016lld", lamport) + ":" + device + ":" + recordID }
}

struct DrawRecord: Equatable, Sendable {
    let recordID: String
    let drawingID: String
    let device: String
    let lamport: Int64
    let kind: String
    let at: String
    let body: ConnectJSON
    var key: DrawKey { DrawKey(lamport: lamport, device: device, recordID: recordID) }

    var json: ConnectJSON {
        .object(["record_id": .string(recordID), "drawing_id": .string(drawingID), "device": .string(device),
                 "lamport": .int(lamport), "kind": .string(kind), "at": .string(at), "body": body])
    }

    /// Canonical compact JSON (bounded like document.encode_record).
    func encoded() throws -> Data {
        let data = json.canonical
        guard data.count <= DrawSpec.Limit.maxOperationBytes + 1024 else { throw DrawFormatError("operation_too_large") }
        return data
    }

    /// The decoded operation of an `op` record.
    var operation: DrawOp? { kind == "op" ? try? DrawOp(json: body) : nil }

    /// Strictly validate one replicated record (document.py validate_record).
    static func validate(_ value: ConnectJSON) throws -> DrawRecord {
        guard let object = value.object,
              Set(object.keys) == ["record_id", "drawing_id", "device", "lamport", "kind", "at", "body"] else {
            throw DrawFormatError("invalid_record")
        }
        guard let recordID = object["record_id"]?.string, DrawText.isRecordID(recordID),
              let drawingID = object["drawing_id"]?.string, DrawText.isUUID(drawingID),
              let device = object["device"]?.string, DrawText.isUUID(device),
              let lamport = object["lamport"]?.integer, lamport >= 1, lamport <= DrawSpec.maxLamport,
              let at = object["at"]?.string, DrawText.isTimestamp(at),
              let kind = object["kind"]?.string, DrawSpec.recordKinds.contains(kind),
              let body = object["body"], let fields = body.object else { throw DrawFormatError("invalid_record") }
        let keys = Set(fields.keys)
        switch kind {
        case "create":
            guard keys == ["width", "height", "background", "title", "created_at"] else { throw DrawFormatError("invalid_record") }
            guard let width = fields["width"]?.integer, let height = fields["height"]?.integer else { throw DrawFormatError("invalid_canvas") }
            try DrawCanvas.validate(width: Int(clamping: width), height: Int(clamping: height))
            guard let background = fields["background"]?.string, DrawSpec.backgrounds.contains(background) else {
                throw DrawFormatError("invalid_background")
            }
            guard let title = fields["title"]?.string, DrawText.cleanTitle(title) == title else { throw DrawFormatError("invalid_title") }
            guard let created = fields["created_at"]?.string, DrawText.isTimestamp(created) else { throw DrawFormatError("invalid_record") }
        case "op":
            let op = try DrawOp(json: body)
            guard op.id == recordID else { throw DrawFormatError("invalid_record") }
        case "visibility":
            guard keys == ["target", "hidden"], fields["hidden"]?.boolean != nil,
                  let target = fields["target"]?.string, DrawText.isRecordID(target) else { throw DrawFormatError("invalid_record") }
        default: // meta
            guard keys == ["field", "value"], let field = fields["field"]?.string, DrawSpec.metaFields.contains(field) else {
                throw DrawFormatError("invalid_record")
            }
            if field == "title" {
                guard let title = fields["value"]?.string, DrawText.cleanTitle(title) == title else { throw DrawFormatError("invalid_title") }
            } else if fields["value"]?.boolean == nil {
                throw DrawFormatError("invalid_record")
            }
        }
        return DrawRecord(recordID: recordID, drawingID: drawingID, device: device, lamport: lamport, kind: kind, at: at, body: body)
    }

    static func decode(_ data: Data) throws -> DrawRecord {
        guard data.count <= DrawSpec.Limit.maxOperationBytes + 1024 else { throw DrawFormatError("invalid_operation") }
        let value: ConnectJSON
        do { value = try ConnectJSON.decode(data, limit: DrawSpec.Limit.maxOperationBytes + 1024, allowDecimals: true) }
        catch { throw DrawFormatError("invalid_operation") }
        return try validate(value)
    }
}

enum DrawCanvas {
    static func validate(width: Int, height: Int) throws {
        let low = DrawSpec.Limit.minCanvas, high = DrawSpec.Limit.maxCanvas
        guard low...high ~= width, low...high ~= height, width * height <= DrawSpec.Limit.maxCanvasPixels else {
            throw DrawFormatError("canvas_too_large")
        }
    }
    struct Preset: Identifiable, Hashable, Sendable {
        let id: String, label: String, width: Int, height: Int, background: String
    }
    /// Same presets as the desktop (model.ts CANVAS_PRESETS, plus transparent HD).
    static let presets: [Preset] = [
        .init(id: "hd", label: "1920 × 1080", width: 1920, height: 1080, background: "#ffffff"),
        .init(id: "square", label: "1080 × 1080", width: 1080, height: 1080, background: "#ffffff"),
        .init(id: "a4", label: "A4 portrait (2480 × 3508)", width: 2480, height: 3508, background: "#ffffff"),
        .init(id: "a4l", label: "A4 landscape (3508 × 2480)", width: 3508, height: 2480, background: "#ffffff"),
        .init(id: "small", label: "800 × 600", width: 800, height: 600, background: "#ffffff"),
        .init(id: "hdt", label: "1920 × 1080 transparent", width: 1920, height: 1080, background: "transparent"),
    ]
}

extension Array where Element == DrawOp {
    /// Index after the last Clear: replay can start there.
    var replayStart: Int {
        for index in indices.reversed() { if case .clear = self[index] { return index + 1 } }
        return 0
    }
    /// Background in effect: the latest visible background operation, else the drawing's own.
    func effectiveBackground(_ initial: String) -> String {
        for op in reversed() { if case .background(_, let value) = op { return value } }
        return initial
    }
}
