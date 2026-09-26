import Foundation

struct ConnectFrame: Equatable, Sendable {
    let kind: UInt8
    let payload: Data
    static func limit(_ kind: UInt8) throws -> Int {
        switch kind {
        case 1...4, 8: 16_384
        case 5, 6: 256_000
        case 9, 10: 72_000
        // C9.2 never receives files or Studio; fail closed without allocating them.
        default: throw ConnectFailure.capabilityUnavailable
        }
    }
    static func header(_ data: Data) throws -> (Int, UInt8) {
        let b = Array(data)
        guard b.count == 6 else { throw ConnectFailure.responseMalformed }
        guard b[4] == 1 else { throw ConnectFailure.protocolVersionUnsupported }
        let size = b[0..<4].reduce(0) { ($0 << 8) | Int($1) }
        guard size <= (try limit(b[5])), ![3,4].contains(b[5]) || size == 0 else { throw ConnectFailure.responseMalformed }
        return (size, b[5])
    }
    func encode() throws -> Data {
        guard payload.count <= (try Self.limit(kind)) else { throw ConnectFailure.responseMalformed }
        let h = Self.length(payload.count) + Data([1, kind])
        _ = try Self.header(h)
        return h + payload
    }
    static func length(_ n: Int) -> Data { Data([UInt8((n >> 24) & 255), UInt8((n >> 16) & 255), UInt8((n >> 8) & 255), UInt8(n & 255)]) }
}
