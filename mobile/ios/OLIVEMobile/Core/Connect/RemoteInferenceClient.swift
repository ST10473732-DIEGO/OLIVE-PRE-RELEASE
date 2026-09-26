import Foundation

protocol InferenceTransport: Sendable {
    func exchange(_ request: ConnectJSON) async throws -> ConnectJSON
    func close() async
}

actor RemoteInferenceClient {
    let transport: any InferenceTransport
    let source: String
    let target: String
    private var activeJob: String?
    private var stopping = false
    init(transport: any InferenceTransport, source: String, target: String) {
        self.transport = transport; self.source = source; self.target = target
    }
    private func exchange(_ request: ConnectJSON) async throws -> ConnectJSON {
        let result = try await transport.exchange(request)
        if let error = result["error"].string { throw InferenceWire.failure(error) }
        return result["result"]
    }
    func status() async throws -> ConnectJSON {
        let r = try await exchange(InferenceWire.request(source: source, target: target, operation: "status"))
        try r.fields(["presets", "permission", "busy"]); return r
    }
    func run(preset: String, messages: [(String, String)], update: @escaping @Sendable (String, String, String) async -> Void) async throws {
        try Task.checkCancellation()
        guard activeJob == nil else { throw ConnectFailure.resourceBusy }
        let req = try InferenceWire.request(source: source, target: target, operation: "start",
            arguments: InferenceWire.startArguments(preset: preset, messages: messages))
        let job = try req["job_id"].uuid()
        activeJob = job; stopping = false
        defer { activeJob = nil }
        let deadline = ContinuousClock.now.advanced(by: .seconds(155))
        var accumulator = InferenceAccumulator()
        do {
            var result: ConnectJSON
            repeat {
                guard ContinuousClock.now < deadline else { throw ConnectFailure.requestTimeout }
                result = try await exchange(req)
                if stopping || Task.isCancelled { throw ConnectFailure.requestCancelled }
                try result.fields(["state", "events", "error"])
                await update(job, result["state"].string ?? "", "")
                if result["state"] == .string("awaiting_approval") { try await Task.sleep(for: .milliseconds(250)) }
            } while result["state"] == .string("awaiting_approval")
            guard !InferenceWire.terminal.contains(result["state"].string ?? "") else {
                throw InferenceWire.failure(result["error"].string ?? "request_indeterminate")
            }
            while true {
                guard ContinuousClock.now < deadline else { throw ConnectFailure.requestTimeout }
                if stopping || Task.isCancelled { throw ConnectFailure.requestCancelled }
                result = try await exchange(InferenceWire.request(source: source, target: target, operation: "poll", job: job,
                    arguments: .object(["after": .int(accumulator.sequence)])))
                if stopping || Task.isCancelled { throw ConnectFailure.requestCancelled }
                try accumulator.consume(result)
                await update(job, accumulator.state, accumulator.text)
                if InferenceWire.terminal.contains(accumulator.state) {
                    guard accumulator.state == "completed", !accumulator.text.isEmpty else {
                        throw InferenceWire.failure(result["error"].string ?? "request_indeterminate")
                    }
                    return
                }
                try await Task.sleep(for: .milliseconds(250))
            }
        } catch {
            if !stopping {
                do { _ = try await exchange(InferenceWire.request(source: source, target: target, operation: "cancel", job: job)) }
                catch { await transport.close() }
            }
            throw error
        }
    }
    func stop() async throws -> String {
        guard let job = activeJob else { return "no_active_request" }
        if stopping { return "stopping" }
        stopping = true
        do {
            let result = try await exchange(InferenceWire.request(source: source, target: target, operation: "cancel", job: job))
            guard let state = result["state"].string, InferenceWire.terminal.contains(state) else { throw ConnectFailure.responseMalformed }
            return state // The C7 target sends this only after actual runtime release.
        } catch { await transport.close(); throw error }
    }
}
