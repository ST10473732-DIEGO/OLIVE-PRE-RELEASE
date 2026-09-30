import Foundation

/// The frame exchange Remote Chat needs; ConnectTransport provides it. Tests and the
/// interop harness substitute an in-process transport over the same wire bytes.
protocol ChatFrameTransport: Sendable {
    func exchangeFrame(kind: UInt8, id: String, payload: Data) async throws -> Data
}

/// A typed refusal from the computer (for example `attachment_missing` or `mode_unavailable`).
struct ChatRemoteError: Error, Equatable, Sendable {
    let code: String
}

/// olive-chat/1 requests over the authenticated channel. Stateless apart from
/// the channel: jobs live on the computer and are addressed by job id, so a new
/// client on a later connection continues the same request.
actor RemoteChatClient {
    let transport: any ChatFrameTransport
    let source: String
    let target: String

    init(transport: any ChatFrameTransport, source: String, target: String) {
        self.transport = transport; self.source = source; self.target = target
    }

    private func call(_ operation: String, _ arguments: ConnectJSON, binary: Data = Data(), id: String? = nil) async throws -> ChatWire.Response {
        let request = try ChatWire.request(source: source, target: target, operation: operation, arguments: arguments,
                                           id: id ?? UUID().uuidString.lowercased())
        let raw = try await transport.exchangeFrame(kind: 17, id: try request["request_id"].uuid(),
                                                    payload: try ChatWire.packet(request, binary: binary))
        let response = try ChatWire.response(raw, request: request)
        if let code = response.error {
            if code == "device_revoked" { throw ConnectFailure.deviceRevoked }
            throw ChatRemoteError(code: code)
        }
        return response
    }

    /// Read-only probe on the ordinary request frame: does this computer speak olive-chat/1?
    static func probe(transport: any ChatFrameTransport, source: String, target: String) async throws -> Bool {
        let now = Int64(Date().timeIntervalSince1970), id = UUID().uuidString.lowercased()
        let request = ConnectJSON.object(["request_id": .string(id), "protocol_version": .string("olive-connect/1"),
            "source_device_id": .string(source), "target_device_id": .string(target), "capability": .string("connect.ping"),
            "operation": .string("protocols"), "arguments": .object([:]), "timestamp": .int(now), "expires_at": .int(now + 60)])
        let value = try ConnectJSON.decode(try await transport.exchangeFrame(kind: 1, id: id, payload: request.canonical), limit: 16_384)
        let protocols = value["state"] == .string("completed") ? value["result"]["protocols"].array ?? [] : []
        return protocols.contains(.string(ChatWire.name))
    }

    /// Asks for this build's additive extensions; a computer that predates them
    /// refuses the argument, and is asked again in the original form.
    func capabilities() async throws -> ChatCapabilities {
        do {
            return try ChatWire.capabilities(try await call("capabilities", ChatWire.capabilitiesArguments(extended: true)).result)
        } catch let refused as ChatRemoteError where refused.code == "invalid_request" {
            return try ChatWire.capabilities(try await call("capabilities", ChatWire.capabilitiesArguments(extended: false)).result)
        }
    }

    /// Offer, then send only what the computer is missing, in bounded chunks read
    /// from the app-owned copy (never the whole file in memory). Resumable: the
    /// computer reports how much it already holds; identical content is never resent.
    func upload(_ descriptor: ChatAttachmentDescriptor, file: URL, chunkBytes: Int = ChatWire.chunkBytes,
                progress: @escaping @Sendable (Int64) async -> Void) async throws {
        var state = try ChatWire.attachmentState(try await call("attachment_offer", descriptor.wire).result, id: descriptor.id)
        await progress(state.received)
        guard !state.present else { return }
        let handle = try FileHandle(forReadingFrom: file)
        defer { try? handle.close() }
        var stalls = 0
        while !state.present {
            try Task.checkCancellation()
            try handle.seek(toOffset: UInt64(state.received))
            guard let data = try handle.read(upToCount: min(chunkBytes, ChatWire.chunkBytes)), !data.isEmpty else {
                throw ChatRemoteError(code: "attachment_corrupt")   // The local copy is shorter than described.
            }
            let before = state.received
            state = try ChatWire.attachmentState(try await call("attachment_chunk", .object(["attachment_id": .string(descriptor.id),
                "offset": .int(state.received)]), binary: data).result, id: descriptor.id)
            await progress(state.received)
            stalls = state.received > before || state.present ? 0 : stalls + 1
            guard stalls < 3 else { throw ChatRemoteError(code: "attachment_corrupt") }
        }
    }

    func start(_ arguments: ConnectJSON) async throws -> ChatJobView {
        let job = try arguments["job_id"].uuid()
        return try ChatWire.view(try await call("start", arguments, id: job).result, job: job, after: 0)
    }

    func poll(job: String, after: Int) async throws -> ChatJobView {
        try ChatWire.view(try await call("poll", .object(["job_id": .string(job), "after": .int(Int64(after))])).result, job: job, after: after)
    }

    func cancel(job: String) async throws -> ChatJobView {
        try ChatWire.view(try await call("cancel", .object(["job_id": .string(job)])).result, job: job, after: 0)
    }

    func artifactChunk(_ artifact: ChatArtifact, offset: Int64, length: Int) async throws -> Data {
        let response = try await call("artifact_chunk", .object(["artifact_id": .string(artifact.artifactID), "offset": .int(offset),
                                                                  "length": .int(Int64(min(length, ChatWire.chunkBytes)))]))
        return try ChatWire.artifactChunk(response, artifact: artifact, offset: offset)
    }
}
