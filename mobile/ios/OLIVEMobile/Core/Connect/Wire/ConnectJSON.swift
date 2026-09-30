import Foundation
import CryptoKit

/// Strict bounded JSON. Fractional tokens are only consumed by C8 result metrics.
indirect enum ConnectJSON: Equatable, Sendable {
    case decimal(String)
    case object([String: ConnectJSON]), array([ConnectJSON]), string(String), int(Int64), bool(Bool), null
    var object: [String: ConnectJSON]? { if case .object(let x) = self { x } else { nil } }
    var array: [ConnectJSON]? { if case .array(let x) = self { x } else { nil } }
    var string: String? { if case .string(let x) = self { x } else { nil } }
    var integer: Int64? { if case .int(let x) = self { x } else { nil } }
    var boolean: Bool? { if case .bool(let x) = self { x } else { nil } }
    subscript(_ key: String) -> ConnectJSON { object?[key] ?? .null }
    func fields(_ names: Set<String>) throws {
        guard let object, Set(object.keys) == names else { throw ConnectFailure.responseMalformed }
    }
    /// Required keys plus explicitly allowed additive ones; anything else is refused.
    func fields(_ names: Set<String>, optional: Set<String>) throws {
        guard let object else { throw ConnectFailure.responseMalformed }
        let keys = Set(object.keys)
        guard names.isSubset(of: keys), keys.isSubset(of: names.union(optional)) else { throw ConnectFailure.responseMalformed }
    }
    func text() throws -> String {
        guard let string else { throw ConnectFailure.responseMalformed }; return string
    }
    func number(_ range: ClosedRange<Int64>) throws -> Int64 {
        guard let integer, range.contains(integer) else { throw ConnectFailure.responseMalformed }; return integer
    }
    func uuid() throws -> String {
        let s = try text()
        guard UUID(uuidString: s)?.uuidString.lowercased() == s else { throw ConnectFailure.identityMismatch }; return s
    }
    var canonical: Data { Data(serialized.utf8) }
    var digest: String { SHA256.hash(data: canonical).map { String(format: "%02x", $0) }.joined() }
    private var serialized: String {
        switch self {
        case .null: return "null"
        case .bool(let b): return b ? "true" : "false"
        case .int(let n): return String(n)
        case .decimal(let token): return token
        case .string(let s):
            return "\"" + s.unicodeScalars.map { scalar in
                switch scalar.value {
                case 34: return "\\\""
                case 92: return "\\\\"
                case 8: return "\\b"
                case 9: return "\\t"
                case 10: return "\\n"
                case 12: return "\\f"
                case 13: return "\\r"
                case 0..<32: return String(format: "\\u%04x", scalar.value)
                default: return String(scalar)
                }
            }.joined() + "\""
        case .array(let a): return "[" + a.map(\.serialized).joined(separator: ",") + "]"
        case .object(let o):
            // Python sorts Unicode codepoints; UTF-8 lexicographic order agrees.
            return "{" + o.keys.sorted { $0.utf8.lexicographicallyPrecedes($1.utf8) }.map {
                ConnectJSON.string($0).serialized + ":" + o[$0]!.serialized
            }.joined(separator: ",") + "}"
        }
    }
    static func decode(_ data: Data, limit: Int = 72_000, allowDecimals: Bool = false) throws -> Self {
        guard data.count <= limit else { throw ConnectFailure.responseMalformed }
        var parser = Parser(bytes: Array(data), allowDecimals: allowDecimals)
        let result = try parser.value(depth: 0)
        parser.space()
        guard parser.i == parser.bytes.count else { throw ConnectFailure.responseMalformed }
        return result
    }
    private struct Parser {
        let bytes: [UInt8]
        let allowDecimals: Bool
        var i = 0
        mutating func space() { while i < bytes.count && [9,10,13,32].contains(bytes[i]) { i += 1 } }
        mutating func take(_ byte: UInt8) throws {
            space(); guard i < bytes.count && bytes[i] == byte else { throw ConnectFailure.responseMalformed }; i += 1
        }
        mutating func string() throws -> String {
            space(); let start = i; try take(34)
            var escaped = false
            while i < bytes.count {
                let c = bytes[i]; i += 1
                if !escaped && c == 34 {
                    guard let s = try JSONSerialization.jsonObject(with: Data(bytes[start..<i]), options: [.fragmentsAllowed]) as? String
                    else { throw ConnectFailure.responseMalformed }; return s
                }
                if !escaped && c == 92 { escaped = true } else { escaped = false }
            }
            throw ConnectFailure.responseMalformed
        }
        mutating func value(depth: Int) throws -> ConnectJSON {
            space(); guard depth < 16, i < bytes.count else { throw ConnectFailure.responseMalformed }
            switch bytes[i] {
            case 34: return .string(try string())
            case 123:
                i += 1; space(); var o: [String: ConnectJSON] = [:]
                if i < bytes.count && bytes[i] == 125 { i += 1; return .object(o) }
                while true {
                    let k = try string(); guard o[k] == nil else { throw ConnectFailure.responseMalformed }
                    try take(58); o[k] = try value(depth: depth + 1); space()
                    guard i < bytes.count else { throw ConnectFailure.responseMalformed }
                    if bytes[i] == 125 { i += 1; return .object(o) }; try take(44)
                }
            case 91:
                i += 1; space(); var a: [ConnectJSON] = []
                if i < bytes.count && bytes[i] == 93 { i += 1; return .array(a) }
                while true {
                    a.append(try value(depth: depth + 1)); space()
                    guard i < bytes.count else { throw ConnectFailure.responseMalformed }
                    if bytes[i] == 93 { i += 1; return .array(a) }; try take(44)
                }
            case 116, 102, 110:
                let word = bytes[i] == 116 ? "true" : bytes[i] == 102 ? "false" : "null"
                for c in word.utf8 { guard i < bytes.count && bytes[i] == c else { throw ConnectFailure.responseMalformed }; i += 1 }
                return word == "true" ? .bool(true) : word == "false" ? .bool(false) : .null
            default:
                let start = i
                if bytes[i] == 45 { i += 1 }
                let digitStart = i
                while i < bytes.count && (48...57).contains(bytes[i]) { i += 1 }
                guard i > digitStart, i - digitStart == 1 || bytes[digitStart] != 48 else { throw ConnectFailure.responseMalformed }
                if i < bytes.count, [46, 69, 101].contains(bytes[i]) {
                    guard allowDecimals else { throw ConnectFailure.responseMalformed }
                    while i < bytes.count && (48...57).contains(bytes[i]) || i < bytes.count && [46, 69, 101, 43, 45].contains(bytes[i]) { i += 1 }
                    let token = String(decoding: bytes[start..<i], as: UTF8.self)
                    guard token.range(of: #"^-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?$"#, options: .regularExpression) != nil,
                          let number = Double(token), number.isFinite else { throw ConnectFailure.responseMalformed }
                    return .decimal(token)
                }
                guard let n = Int64(String(decoding: bytes[start..<i], as: UTF8.self)) else { throw ConnectFailure.responseMalformed }
                return .int(n)
            }
        }
    }
}
