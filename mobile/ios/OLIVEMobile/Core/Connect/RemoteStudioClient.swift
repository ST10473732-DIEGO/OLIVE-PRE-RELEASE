import Foundation

extension StudioWire {
    static func exchange(_ request: ConnectJSON, channel: ConnectTransport, cancelled: @Sendable () async -> Bool = { false }) async throws -> ConnectJSON {
        let deadline = ContinuousClock.now.advanced(by: .seconds(120))
        repeat {
            try Task.checkCancellation()
            if await cancelled() { throw ConnectFailure.requestCancelled }
            let value = try response(await channel.exchangeFrame(kind: 11, id: request["request_id"].uuid(), payload: request.canonical), request: request)
            if value["error"] == .string("confirmation_required") {
                if await cancelled() { throw ConnectFailure.requestCancelled }
                try await Task.sleep(for: .seconds(1)); continue
            }
            if let error = value["error"].string { throw failure(error) }
            return value["result"]
        } while ContinuousClock.now < deadline
        throw ConnectFailure.requestTimeout
    }
}
