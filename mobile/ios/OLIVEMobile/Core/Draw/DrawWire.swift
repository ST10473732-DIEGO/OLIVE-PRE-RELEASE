import Foundation

/// The two ends of an olive-draw/1 exchange, independent of the socket, so the
/// app (Connect frames 15/16) and the interop harness use identical code.
enum DrawWire {
    /// Receiving side: decode strictly, check the authenticated peer, this
    /// phone's own permission and freshness, handle, and answer. Never throws:
    /// every failure is a correlated, fixed-code rejection.
    static func receive(engine: DrawEngine, raw: Data, peer: String, local: String, permitted: Bool, now: Int64) async -> Data {
        let requestID = DrawProtocol.requestID(of: raw)
        do {
            let request = try DrawProtocol.decodeRequest(raw)
            // The authenticated channel supplies the peer; message fields must match it.
            guard request.source == peer else { throw DrawProtocol.Failure("source_mismatch") }
            guard request.target == local else { throw DrawProtocol.Failure("wrong_target") }
            guard permitted else { throw DrawProtocol.Failure("permission_off") }
            try DrawProtocol.checkFresh(request, now: now)
            guard await engine.available else { throw DrawProtocol.Failure("draw_unavailable") }
            let result = try await engine.handle(peer: peer, request: request)
            return try DrawProtocol.encodeResponse(requestID: request.requestID, result: result)
        } catch let failure as DrawProtocol.Failure {
            return DrawProtocol.encodeResponse(requestID: requestID, error: failure.code)
        } catch {
            return DrawProtocol.encodeResponse(requestID: requestID, error: "draw_unavailable")
        }
    }

    /// Sending side: builds `send(operation, arguments)` for `DrawEngine.pump`.
    /// `exchange(requestID, requestBytes)` performs one request and returns the
    /// raw response. A rejection throws its fixed code.
    static func sender(local: String, peer: String, clock: @escaping @Sendable () -> Int64,
                       exchange: @escaping @Sendable (String, Data) async throws -> Data) -> @Sendable (String, ConnectJSON) async throws -> ConnectJSON {
        { operation, arguments in
            let requestID = UUID().uuidString.lowercased()
            let raw = try DrawProtocol.encodeRequest(requestID: requestID, source: local, target: peer, operation: operation,
                                                     arguments: arguments, now: clock())
            let response = try DrawProtocol.decodeResponse(try await exchange(requestID, raw))
            guard response.requestID == requestID else { throw DrawProtocol.Failure("malformed_message") }
            if let error = response.error { throw DrawProtocol.Failure(error) }
            guard let result = response.result else { throw DrawProtocol.Failure("malformed_message") }
            return result
        }
    }

    static func now() -> Int64 { Int64(Date().timeIntervalSince1970) }
}
