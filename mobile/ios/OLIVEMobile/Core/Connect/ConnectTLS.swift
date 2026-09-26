import Foundation

/// Confined to its owning actor; all cryptography is in the pinned OpenSSL build.
final class ConnectTLS {
    private let handle: OpaquePointer
    init(seed: Data, local: Data, peer: Data) throws {
        let ptr = seed.withUnsafeBytes { s in local.withUnsafeBytes { l in peer.withUnsafeBytes { p in
            olive_tls_create(s.bindMemory(to: UInt8.self).baseAddress,
                l.bindMemory(to: UInt8.self).baseAddress, local.count,
                p.bindMemory(to: UInt8.self).baseAddress, peer.count)
        } } }
        guard let ptr else { throw ConnectFailure.certificateMismatch }; handle = ptr
    }
    deinit { olive_tls_free(handle) }
    func feed(_ bytes: Data) throws {
        let n = bytes.withUnsafeBytes { olive_tls_feed(handle, $0.bindMemory(to: UInt8.self).baseAddress, bytes.count) }
        guard n == bytes.count else { throw ConnectFailure.connectionLost }
    }
    func handshake() throws -> Bool {
        let result = olive_tls_handshake(handle)
        guard result >= 0 else { throw ConnectFailure.certificateMismatch }; return result == 1
    }
    func drain() throws -> Data {
        var out = Data(), buffer = [UInt8](repeating: 0, count: 32768)
        while true {
            let n = olive_tls_drain(handle, &buffer, buffer.count)
            guard n >= 0 else { throw ConnectFailure.connectionLost }
            if n == 0 { return out }
            out.append(contentsOf: buffer.prefix(Int(n)))
            guard out.count <= 131072 else { throw ConnectFailure.responseMalformed }
        }
    }
    func read() throws -> Data {
        var buffer = [UInt8](repeating: 0, count: 16384)
        let n = olive_tls_read(handle, &buffer, buffer.count)
        guard n >= 0 else { throw ConnectFailure.connectionLost }
        return Data(buffer.prefix(Int(n)))
    }
    func write(_ data: Data) throws {
        let n = data.withUnsafeBytes { olive_tls_write(handle, $0.bindMemory(to: UInt8.self).baseAddress, data.count) }
        guard n == data.count else { throw ConnectFailure.connectionLost }
    }
    func comparison(binding: Data) throws -> String {
        guard binding.count == 32 else { throw ConnectFailure.responseMalformed }
        var out = [UInt8](repeating: 0, count: 32)
        let r = binding.withUnsafeBytes { olive_tls_comparison(handle, $0.bindMemory(to: UInt8.self).baseAddress, &out) }
        guard r == 1 else { throw ConnectFailure.certificateMismatch }; return Data(out).comparison
    }
}
