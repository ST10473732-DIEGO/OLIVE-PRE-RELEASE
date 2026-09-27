import Foundation
import Network

actor ConnectTransport: InferenceTransport {
    private let socket: ConnectSocket
    private var tls: ConnectTLS?
    private var reader: Task<Void, Never>?
    private var pending: [String: (UInt8, UUID, CheckedContinuation<Data, Error>)] = [:]
    private var sender: Task<Void, Error>?
    private var inbound: (@Sendable (ConnectFrame) async throws -> ConnectFrame)?
    private var inboundDelivered: (@Sendable (ConnectFrame) async -> Void)?
    func setInbound(_ handler: (@Sendable (ConnectFrame) async throws -> ConnectFrame)?, delivered: (@Sendable (ConnectFrame) async -> Void)? = nil) {
        inbound = handler; inboundDelivered = delivered
    }
    private var plaintext = Data()
    private var ready = false
    private var closed = false
    private var authenticatedIDs: (local: String, peer: String)?
    #if DEBUG
    // Explicit acceptance-only diagnostics: bounded typed metadata, never frame
    // contents, endpoint names, identities or credentials. Eight protected slots.
    private struct AcceptanceEvent: Codable { let time: Date; let phase: String; let failure: String? }
    private struct AcceptanceTrace: Codable { let id: UUID; let incomingInferenceReplies: Int; let events: [AcceptanceEvent] }
    private let acceptanceTraceID = UUID()
    private var incomingInferenceReplies = 0
    private var acceptanceEvents: [AcceptanceEvent] = []
    private func acceptanceTrace(_ phase: String, error: (any Error)? = nil, persist: Bool = true) {
        guard ProcessInfo.processInfo.arguments.contains("--c93-transport-trace") ||
            ProcessInfo.processInfo.environment["OLIVE_C93_TRACE_ACCEPTANCE"] == "1" else { return }
        acceptanceEvents = Array(acceptanceEvents.suffix(15)) + [AcceptanceEvent(time: Date(), phase: phase,
            failure: error.map { ($0 as? ConnectFailure ?? .connectionLost).rawValue })]
        // Keep per-frame observations in memory. Diagnostic disk writes for
        // every C6 chunk would unnecessarily compete with background file work.
        guard persist else { return }
        let slot = Int(acceptanceTraceID.uuid.0) % 8
        let store = ProtectedStore<AcceptanceTrace>(url: URL.applicationSupportDirectory.appendingPathComponent("C93Acceptance/Trace/transport-\(slot).json"), maximumBytes: 4096)
        try? store.save(AcceptanceTrace(id: acceptanceTraceID, incomingInferenceReplies: incomingInferenceReplies, events: acceptanceEvents))
    }
    #endif
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
            authenticatedIDs = (identity.publicIdentity.deviceID, peer.deviceID)
            ready = true
            #if DEBUG
            acceptanceTrace("authenticated")
            #endif
            reader = Task { await readLoop() }
        } catch { await close(); throw error }
    }
    private func flush() async throws {
        guard !closed, let tls else { throw ConnectFailure.connectionLost }
        let out = try tls.drain()
        if !out.isEmpty { try await socket.send(out) }
    }
    private func write(_ data: Data) async throws {
        let previous = sender
        let task = Task {
            _ = try await previous?.value
            try await self.writeSerial(data)
        }
        sender = task
        try await task.value
    }
    private func writeSerial(_ data: Data) async throws {
        guard !closed, let tls else { throw ConnectFailure.connectionLost }
        var offset = 0
        while offset < data.count {
            let end = min(offset + 16384, data.count)
            try tls.write(Data(data[offset..<end])); try await flush(); offset = end
        }
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
                guard plaintext.count <= 416390 else { throw ConnectFailure.responseMalformed }
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
                #if DEBUG
                acceptanceTrace("frame-\(frame.kind)-bytes-\(frame.payload.count)", persist: false)
                #endif
                if frame.kind == 9, let ids = authenticatedIDs {
                    let reply = try InferenceWire.clientReply(frame.payload, local: ids.local, peer: ids.peer)
                    try await write(ConnectFrame(kind: 10, payload: reply.canonical).encode())
                    #if DEBUG
                    incomingInferenceReplies = min(incomingInferenceReplies + 1, 1_000_000)
                    acceptanceTrace("incoming-inference-replied")
                    #endif
                    continue
                }
                if [5, 7].contains(frame.kind), let inbound {
                    let reply = try await inbound(frame)
                    guard reply.kind == frame.kind + 1 else { throw ConnectFailure.responseMalformed }
                    try await write(reply.encode())
                    await inboundDelivered?(reply)
                    continue
                }
                guard [2, 6, 8, 10, 12].contains(frame.kind) else { throw ConnectFailure.responseMalformed }
                let v = try ConnectJSON.decode(frame.payload, limit: ConnectFrame.limit(frame.kind), allowDecimals: frame.kind == 12)
                #if DEBUG
                acceptanceTrace("decoded-\(frame.kind)", persist: false)
                #endif
                let id = try v["request_id"].uuid()
                if let (kind, _, continuation) = pending.removeValue(forKey: id) {
                    guard kind == frame.kind else {
                        continuation.resume(throwing: ConnectFailure.responseMalformed)
                        throw ConnectFailure.responseMalformed
                    }
                    continuation.resume(returning: frame.payload)
                }
                // Late responses never create or attach to a new request.
            }
        } catch {
            #if DEBUG
            acceptanceTrace("reader", error: error)
            #endif
            await close()
        }
    }
    func exchange(_ request: ConnectJSON) async throws -> ConnectJSON {
        let raw = try await exchangeFrame(kind: 9, id: request["request_id"].uuid(), payload: request.canonical)
        let value = try InferenceWire.response(raw)
        guard value["job_id"] == request["job_id"] else { await close(); throw ConnectFailure.identityMismatch }
        return value
    }
    func exchangeFrame(kind: UInt8, id: String, payload: Data) async throws -> Data {
        guard ready, !closed else { throw ConnectFailure.peerOffline }
        guard [1, 5, 7, 9, 11].contains(kind) else { throw ConnectFailure.capabilityUnavailable }
        _ = try ConnectJSON.string(id).uuid()
        let encoded = try ConnectFrame(kind: kind, payload: payload).encode()
        guard pending.count < 8, pending[id] == nil else { throw ConnectFailure.resourceBusy }
        return try await withCheckedThrowingContinuation { c in
            let ticket = UUID()
            pending[id] = (kind + 1, ticket, c)
            Task {
                do { try await write(encoded) }
                catch {
                    #if DEBUG
                    acceptanceTrace("writer", error: error)
                    #endif
                    await close()
                }
            }
            Task {
                try? await Task.sleep(for: .seconds(7))
                if let (_, currentTicket, continuation) = pending[id], currentTicket == ticket {
                    pending.removeValue(forKey: id)
                    continuation.resume(throwing: ConnectFailure.requestTimeout)
                    if kind == 9 { await close() }
                }
            }
        }
    }
    func close() async {
        #if DEBUG
        if !closed { acceptanceTrace("close") }
        #endif
        closed = true; ready = false; authenticatedIDs = nil; sender?.cancel(); sender = nil; inbound = nil; inboundDelivered = nil; reader?.cancel(); reader = nil
        let waiting = pending; pending.removeAll()
        for (_, _, c) in waiting.values { c.resume(throwing: ConnectFailure.connectionLost) }
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
