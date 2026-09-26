import Foundation
import Network

private final class SocketCompletion<T: Sendable>: @unchecked Sendable {
    private let lock = NSLock()
    private var continuation: CheckedContinuation<T, Error>?
    init(_ continuation: CheckedContinuation<T, Error>) { self.continuation = continuation }
    func finish(_ result: Result<T, Error>) {
        lock.lock(); let c = continuation; continuation = nil; lock.unlock()
        c?.resume(with: result)
    }
}

actor ConnectSocket {
    private let connection: NWConnection
    private let queue = DispatchQueue(label: "olive.connect.socket")
    init(endpoint: NWEndpoint) {
        let options = NWProtocolTCP.Options(); options.connectionTimeout = 3
        let parameters = NWParameters(tls: nil, tcp: options)
        parameters.requiredInterfaceType = .wifi
        parameters.prohibitedInterfaceTypes = [.cellular]
        parameters.includePeerToPeer = false
        connection = NWConnection(to: endpoint, using: parameters)
    }
    func open() async throws {
        let connection = connection, queue = queue
        try await withCheckedThrowingContinuation { (c: CheckedContinuation<Void, Error>) in
            let once = SocketCompletion(c)
            connection.stateUpdateHandler = { state in
                switch state {
                case .ready: once.finish(.success(()))
                case .failed, .cancelled: once.finish(.failure(ConnectFailure.peerOffline))
                default: break
                }
            }
            connection.start(queue: queue)
            queue.asyncAfter(deadline: .now() + 3) {
                // A completed continuation is inert; don't cancel an established socket.
                if connection.state != .ready { connection.cancel(); once.finish(.failure(ConnectFailure.peerOffline)) }
            }
        }
    }
    func send(_ bytes: Data, timeout: Double = 2) async throws {
        guard bytes.count <= 131072 else { throw ConnectFailure.responseMalformed }
        let connection = connection
        try await withCheckedThrowingContinuation { (c: CheckedContinuation<Void, Error>) in
            let once = SocketCompletion(c)
            connection.send(content: bytes, completion: .contentProcessed { error in
                once.finish(error == nil ? .success(()) : .failure(ConnectFailure.connectionLost))
            })
            queue.asyncAfter(deadline: .now() + timeout) { once.finish(.failure(ConnectFailure.requestTimeout)) }
        }
    }
    func receive(max: Int = 32768, timeout: Double = 3) async throws -> Data {
        let connection = connection
        return try await withCheckedThrowingContinuation { c in
            let once = SocketCompletion(c)
            connection.receive(minimumIncompleteLength: 1, maximumLength: max) { data, _, complete, error in
                if let data, !data.isEmpty, error == nil { once.finish(.success(data)) }
                else { once.finish(.failure(complete ? ConnectFailure.connectionLost : ConnectFailure.requestTimeout)) }
            }
            queue.asyncAfter(deadline: .now() + timeout) { once.finish(.failure(ConnectFailure.requestTimeout)) }
        }
    }
    func exact(_ count: Int, timeout: Double = 2) async throws -> Data {
        guard (0...32768).contains(count) else { throw ConnectFailure.responseMalformed }
        var data = Data(); let deadline = ContinuousClock.now.advanced(by: .seconds(timeout))
        while data.count < count {
            guard ContinuousClock.now < deadline else { throw ConnectFailure.requestTimeout }
            let remaining = ContinuousClock.now.duration(to: deadline).components
            let seconds = Double(remaining.seconds) + Double(remaining.attoseconds) / 1e18
            data.append(try await receive(max: count - data.count, timeout: max(0.001, seconds)))
        }
        return data
    }
    func close() { connection.cancel() }
}
