import Foundation

/// The byte stream beneath Connect's TLS. Direct is a TCP socket on Wi-Fi
/// (ConnectSocket); World is a WebSocket to the relay (WorldSocket). The TLS
/// session, frames and every application protocol above are identical.
protocol ConnectByteStream: Actor {
    func open() async throws
    func send(_ bytes: Data, timeout: Double) async throws
    func receive(max: Int, timeout: Double) async throws -> Data
    func close()
}

extension ConnectSocket: ConnectByteStream {}

/// Which path an authenticated Connect channel uses. Computation never moves: it is
/// always the paired computer. Shown to people as "Connected · Direct" / "Connected · World".
enum ConnectPath: String, Sendable, Equatable {
    case direct = "Direct", world = "World"
}

/// Outbound wss:// to the OLIVE World relay (TCP 443 through NAT, CGNAT and
/// firewalls). After the relay pairs this route with the computer, binary
/// messages carry the phone's own TLS records; the relay cannot read them.
///
/// One pump task receives messages into a bounded buffer (backpressure: it
/// stops receiving while the buffer is full). Keepalive pings run every 25 s;
/// silence beyond 70 s retires the path.
actor WorldSocket: ConnectByteStream {
    private let url: URL
    private let hello: String
    private let session: URLSession
    private var task: URLSessionWebSocketTask?
    private var buffer = Data()
    private var waiters: [UUID: CheckedContinuation<Void, Never>] = [:]
    private var pump: Task<Void, Never>?
    private var keepalive: Task<Void, Never>?
    private var finished = false
    private var lastReceived = ContinuousClock.now
    /// Why the path ended, in World terms (for the status line); nil while healthy.
    private(set) var failure: WorldFailure?
    private(set) var bytesIn = 0
    private(set) var bytesOut = 0
    static let bufferLimit = 1_048_576
    static let keepaliveInterval: Duration = .seconds(25)
    static let deadAfter: Duration = .seconds(70)
    /// A computer that is offline is reported by the relay after 20 s.
    static let rendezvousTimeout: Double = 25

    init(credential: WorldCredential, allowTestPlaintext: Bool = WorldTestFlags.allowTestPlaintext) throws {
        url = try WorldWire.relayURL(credential.relayURL, allowTestPlaintext: allowTestPlaintext)
        hello = try credential.hello()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.waitsForConnectivity = false
        configuration.timeoutIntervalForRequest = 15
        configuration.httpCookieStorage = nil
        configuration.urlCache = nil
        session = URLSession(configuration: configuration)   // System trust; TLS verification is never disabled.
    }

    func open() async throws {
        let task = session.webSocketTask(with: url, protocols: [WorldWire.subprotocol])
        task.maximumMessageSize = WorldWire.maxMessage + 1024
        self.task = task
        task.resume()
        let hello = hello
        do {
            try await withDeadline(seconds: 15) { try await task.send(.string(hello)) }
            let deadline = ContinuousClock.now.advanced(by: .seconds(Self.rendezvousTimeout))
            while true {
                let remaining = ContinuousClock.now.duration(to: deadline)
                guard remaining > .zero else { throw WorldFailure.computerOffline }
                let message = try await withDeadline(seconds: Double(remaining.components.seconds) + 1) { try await WorldSocket.next(task) }
                guard case .text(let text) = message else { throw WorldFailure.relayProtocol }
                if try WorldWire.event(text) == .paired { break }
            }
        } catch {
            failure = classify(error, task: task)
            close()
            throw ConnectFailure.peerOffline
        }
        lastReceived = .now
        pump = Task { await self.run(task) }
        keepalive = Task { await self.ping(task) }
    }

    /// One relay message, converted off-actor into a Sendable value.
    enum Message: Sendable { case text(String), binary(Data) }
    nonisolated static func next(_ task: URLSessionWebSocketTask) async throws -> Message {
        switch try await task.receive() {
        case .string(let text): return .text(text)
        case .data(let data): return .binary(data)
        @unknown default: throw WorldFailure.relayProtocol
        }
    }

    private func classify(_ error: any Error, task: URLSessionWebSocketTask) -> WorldFailure {
        if let failure = error as? WorldFailure { return failure }
        if task.closeCode != .invalid { return WorldFailure.from(closeCode: task.closeCode.rawValue) }
        return .relayUnreachable
    }

    private func run(_ task: URLSessionWebSocketTask) async {
        while !finished {
            while buffer.count >= Self.bufferLimit && !finished { await wait() }
            do {
                let message = try await WorldSocket.next(task)
                guard case .binary(let data) = message, data.count <= WorldWire.maxMessage else {
                    failure = .relayProtocol; break
                }
                lastReceived = .now
                bytesIn += data.count
                buffer.append(data)
                wake()
            } catch {
                if failure == nil { failure = classify(error, task: task) }
                break
            }
        }
        finish()
    }

    private func ping(_ task: URLSessionWebSocketTask) async {
        while !finished {
            try? await Task.sleep(for: Self.keepaliveInterval)
            guard !finished else { return }
            if lastReceived.duration(to: .now) > Self.deadAfter { failure = failure ?? .relayUnreachable; close(); return }
            task.sendPing { [weak self] error in
                guard error == nil, let self else { return }
                Task { await self.markAlive() }
            }
        }
    }
    private func markAlive() { lastReceived = .now }

    /// The pump's backpressure: resumes once the reader drained the buffer (or the path ended).
    private func wait() async {
        let id = UUID()
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            if finished || buffer.count < Self.bufferLimit { continuation.resume() } else { waiters[id] = continuation }
        }
    }
    private func wake() {
        let pending = waiters; waiters.removeAll()
        for continuation in pending.values { continuation.resume() }
    }
    private func finish() {
        finished = true
        wake()
    }

    func send(_ bytes: Data, timeout: Double = 2) async throws {
        guard let task, !finished else { throw ConnectFailure.connectionLost }
        var offset = 0
        while offset < bytes.count {
            let end = min(offset + WorldWire.chunk, bytes.count)
            let part = bytes.subdata(in: offset..<end)
            // Internet paths: a longer bound than the LAN's 2 s, still bounded.
            try await withDeadline(seconds: max(timeout, 10)) { try await task.send(.data(part)) }
            bytesOut += part.count
            offset = end
        }
    }

    func receive(max: Int = 32768, timeout: Double = 3) async throws -> Data {
        let deadline = ContinuousClock.now.advanced(by: .milliseconds(Int(Swift.max(timeout, 1) * 1000)))
        while buffer.isEmpty {
            if finished { throw ConnectFailure.connectionLost }
            guard ContinuousClock.now < deadline else { throw ConnectFailure.requestTimeout }
            let id = UUID()
            let timer = Task { [weak self] in
                try? await Task.sleep(until: deadline, clock: .continuous)
                await self?.expire(id)
            }
            await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
                if finished || !buffer.isEmpty { continuation.resume() } else { waiters[id] = continuation }
            }
            timer.cancel()
        }
        let count = Swift.min(max, buffer.count)
        let out = buffer.prefix(count)
        buffer.removeFirst(count)
        if buffer.count < Self.bufferLimit { wake() }   // Let the pump receive again.
        return Data(out)
    }
    private func expire(_ id: UUID) { waiters.removeValue(forKey: id)?.resume() }

    func close() {
        finished = true
        task?.cancel(with: .normalClosure, reason: nil)
        pump?.cancel(); keepalive?.cancel()
        session.invalidateAndCancel()
        wake()
    }
}

/// Bounds an async operation; on expiry the caller treats the path as failed.
private func withDeadline<T: Sendable>(seconds: Double, _ operation: @escaping @Sendable () async throws -> T) async throws -> T {
    try await withThrowingTaskGroup(of: T.self) { group in
        group.addTask { try await operation() }
        group.addTask {
            try await Task.sleep(for: .milliseconds(Int(seconds * 1000)))
            throw ConnectFailure.requestTimeout
        }
        guard let first = try await group.next() else { throw ConnectFailure.requestTimeout }
        group.cancelAll()
        return first
    }
}
