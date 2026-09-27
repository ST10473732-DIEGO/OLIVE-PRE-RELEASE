import Foundation
import Network

actor ConnectTransport: InferenceTransport {
    private let socket: ConnectSocket
    private var tls: ConnectTLS?
    private var reader: Task<Void, Never>?
    private var pending: [String: (String, CheckedContinuation<ConnectJSON, Error>)] = [:]
    private var plaintext = Data()
    private var ready = false
    private var closed = false
    init(endpoint: NWEndpoint) { socket = ConnectSocket(endpoint: endpoint) }
    func connect(identity: ConnectIdentity, peer: ConnectPublicIdentity) async throws {
        do {
            tls = try identity.makeTLS(peer: peer)
            try await socket.open()
            let deadline = ContinuousClock.now.advanced(by: .seconds(3))
            var budget = 0
            while true {
                guard !closed, ContinuousClock.now < deadline, let tls else { throw ConnectFailure.requestTimeout }
                let done = try tls.handshake()
                try await flush()
                if done { break }
                let data = try await socket.receive()
                budget += data.count; guard budget <= 131072 else { throw ConnectFailure.responseMalformed }
                try tls.feed(data)
            }
            try await write(ConnectFrame(kind: 4, payload: Data()).encode())
            let hello = try await readFrame(timeout: 3)
            guard hello.kind == 4, hello.payload.isEmpty, !closed else { throw ConnectFailure.protocolVersionUnsupported }
            ready = true
            reader = Task { await readLoop() }
        } catch { await close(); throw error }
    }
    private func flush() async throws {
        guard !closed, let tls else { throw ConnectFailure.connectionLost }
        let out = try tls.drain()
        if !out.isEmpty { try await socket.send(out) }
    }
    private func write(_ data: Data) async throws {
        guard !closed, let tls else { throw ConnectFailure.connectionLost }
        try tls.write(data); try await flush()
    }
    private func readFrame(timeout: Double) async throws -> ConnectFrame {
        var frameDeadline: ContinuousClock.Instant? = plaintext.isEmpty ? nil : .now.advanced(by: .seconds(3))
        while !closed {
            if plaintext.count >= 6 {
                let (size, kind) = try ConnectFrame.header(Data(plaintext.prefix(6)))
                if plaintext.count >= size + 6 {
                    let payload = Data(plaintext.dropFirst(6).prefix(size))
                    plaintext.removeFirst(size + 6)
                    return ConnectFrame(kind: kind, payload: payload)
                }
            }
            if let frameDeadline, ContinuousClock.now >= frameDeadline { throw ConnectFailure.requestTimeout }
            guard let tls else { throw ConnectFailure.connectionLost }
            let decoded = try tls.read()
            if !decoded.isEmpty {
                if plaintext.isEmpty { frameDeadline = .now.advanced(by: .seconds(3)) }
                plaintext.append(decoded)
                guard plaintext.count <= 88000 else { throw ConnectFailure.responseMalformed }
                continue
            }
            try await flush()
            let data = try await socket.receive(timeout: plaintext.isEmpty ? timeout : 3)
            guard !closed else { throw ConnectFailure.connectionLost }
            try tls.feed(data)
        }
        throw ConnectFailure.connectionLost
    }
    private func readLoop() async {
        do {
            while !closed {
                let frame = try await readFrame(timeout: 30)
                guard frame.kind == 10 else { throw ConnectFailure.responseMalformed }
                let v = try InferenceWire.response(frame.payload)
                let id = try v["request_id"].uuid()
                if let (job, continuation) = pending.removeValue(forKey: id) {
                    guard v["job_id"] == .string(job) else {
                        continuation.resume(throwing: ConnectFailure.identityMismatch)
                        throw ConnectFailure.identityMismatch
                    }
                    continuation.resume(returning: v)
                }
                // Late responses never create or attach to a new request.
            }
        } catch { await close() }
    }
    func exchange(_ request: ConnectJSON) async throws -> ConnectJSON {
        guard ready, !closed else { throw ConnectFailure.peerOffline }
        let id = try request["request_id"].uuid(), job = try request["job_id"].uuid()
        guard pending.count < 8, pending[id] == nil else { throw ConnectFailure.resourceBusy }
        return try await withCheckedThrowingContinuation { c in
            pending[id] = (job, c)
            Task {
                do { try await write(ConnectFrame(kind: 9, payload: request.canonical).encode()) }
                catch { await close() }
            }
            Task {
                try? await Task.sleep(for: .seconds(7))
                if pending[id] != nil { await close() }
            }
        }
    }
    func close() async {
        closed = true; ready = false; reader?.cancel(); reader = nil
        let waiting = pending; pending.removeAll()
        for (_, c) in waiting.values { c.resume(throwing: ConnectFailure.connectionLost) }
        await socket.close(); tls = nil; plaintext.removeAll()
    }
    #if DEBUG
    /// Physical acceptance fault injection: send the real C7 cancel, then lose
    /// its acknowledgement. No trust mutation or alternate wire path.
    func acceptanceDisconnectDuringCancel(_ request: ConnectJSON) async throws {
        guard ready, !closed, request["operation"] == .string("cancel") else { throw ConnectFailure.peerOffline }
        try await write(ConnectFrame(kind: 9, payload: request.canonical).encode())
        await close()
    }
    #endif
}
