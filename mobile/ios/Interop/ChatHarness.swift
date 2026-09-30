import Foundation
import CryptoKit

// Remote Chat v2 interop: the app's own RemoteChatClient, ChatWire and ChatMediaStore
// against the Python desktop RemoteChatService (tests/test_mobile_chat_interop.py).
// Line protocol on stdin/stdout. Python sends a command; for every frame the Swift
// client emits {"kind","frame"} and Python answers {"reply"} or {"drop": true}
// (a lost connection). The command ends with {"done": result} or {"failed": code}.

/// Frames cross the process boundary; a dropped reply is a connection loss.
actor StdioChatTransport: ChatFrameTransport {
    func exchangeFrame(kind: UInt8, id: String, payload: Data) async throws -> Data {
        emit(.object(["kind": .int(Int64(kind)), "frame": .string(payload.base64EncodedString())]))
        guard let line = readLine() else { throw ConnectFailure.connectionLost }
        let answer = try ConnectJSON.decode(Data(line.utf8), limit: 1 << 20)
        if answer["drop"] == .bool(true) { throw ConnectFailure.connectionLost }
        guard let reply = answer["reply"].string.flatMap({ Data(base64Encoded: $0) }) else { throw ConnectFailure.responseMalformed }
        // Enforce the same frame bound the transport applies before correlation.
        guard reply.count <= (try ConnectFrame.limit(kind + 1)) else { throw ConnectFailure.responseMalformed }
        return reply
    }
}

private func emit(_ value: ConnectJSON) {
    print(String(decoding: value.canonical, as: UTF8.self)); fflush(stdout)
}

private func summary(_ view: ChatJobView, text: String) -> ConnectJSON {
    .object(["state": .string(view.state), "text": .string(text), "error": view.error.map(ConnectJSON.string) ?? .null,
             "label": .string(view.attribution?.label ?? ""),
             "sources": .array(view.sources.map { .object(["id": .string($0.id), "kind": .string($0.kind),
                 "url": $0.url.map { .string($0.absoluteString) } ?? .null, "title": .string($0.title)]) }),
             "artifacts": .array(view.artifacts.map { .object(["artifact_id": .string($0.artifactID), "kind": .string($0.kind),
                 "size": .int($0.size), "sha256": .string($0.sha256)]) })])
}

func runChatHarness(source: String, target: String, directory: URL) async {
    let transport = StdioChatTransport()
    let client = RemoteChatClient(transport: transport, source: source, target: target)
    var artifacts: [String: ChatArtifact] = [:]
    let media = ChatMediaStore(directory: directory.appendingPathComponent("media", isDirectory: true))
    while let line = readLine() {
        do {
            let command = try ConnectJSON.decode(Data(line.utf8), limit: 1 << 20)
            switch command["cmd"].string ?? "" {
            case "probe":
                let speaks = try await RemoteChatClient.probe(transport: transport, source: source, target: target)
                emit(.object(["done": .bool(speaks)]))
            case "capabilities":
                let capabilities = try await client.capabilities()
                emit(.object(["done": .object(["permission": .string(capabilities.permission),
                    "extensions": .array(capabilities.extensions.map(ConnectJSON.string)),
                    "modes": .array(capabilities.modes.map { .object(["id": .string($0.id), "available": .bool($0.available),
                        "image_max": .int(Int64($0.imageMax)), "document_max": .int(Int64($0.documentMax)),
                        "video_i2v": $0.video.map { .bool($0.imageToVideo) } ?? .null,
                        "video_max_ms": $0.video.map { .int($0.maximumMS) } ?? .null]) })])]))
            case "duration":
                let parsed = VideoDuration.parse(try command["text"].text())
                emit(.object(["done": parsed.map { .int(Int64(($0.seconds * 1000).rounded())) } ?? .null]))
            case "upload":
                let file = URL(fileURLWithPath: try command["path"].text())
                let data = try Data(contentsOf: file)
                let descriptor = ChatAttachmentDescriptor(id: Data(SHA256.hash(data: data)).hex, kind: try command["kind"].text(),
                    mime: try command["mime"].text(), size: Int64(data.count), name: try command["name"].text())
                let chunk = Int(command["chunk"].integer ?? Int64(ChatWire.chunkBytes))
                try await client.upload(descriptor, file: file, chunkBytes: chunk) { _ in }
                emit(.object(["done": descriptor.wire]))
            case "start":
                let attachments = try (command["attachments"].array ?? []).map { a in
                    ChatAttachmentDescriptor(id: try a["attachment_id"].text(), kind: try a["kind"].text(), mime: try a["mime"].text(),
                                             size: try a["size"].number(1...Int64.max), name: try a["name"].text())
                }
                let arguments = try ChatWire.startArguments(job: try command["job"].uuid(), conversation: try command["conversation"].uuid(),
                    mode: try command["mode"].text(), voice: command["voice"].string, messages: [("user", try command["text"].text())], attachments: attachments,
                    options: command["options"] == .null ? nil : command["options"])
                let view = try await client.start(arguments)
                emit(.object(["done": .object(["state": .string(view.state)])]))
            case "follow":
                let job = try command["job"].uuid()
                var after = Int(command["after"].integer ?? 0), text = ""
                var progress: [ConnectJSON] = []
                while true {
                    let view = try await client.poll(job: job, after: after)
                    text += view.text; after += view.text.utf8.count
                    if let step = view.progress, progress.last != .string(step.text) { progress.append(.string(step.text)) }
                    if view.state == "not_received" || (view.terminal && after >= view.total) {
                        for artifact in view.artifacts { artifacts[artifact.artifactID] = artifact }
                        var done = summary(view, text: text)
                        if case .object(var fields) = done { fields["progress"] = .array(progress); done = .object(fields) }
                        emit(.object(["done": done])); break
                    }
                    try await Task.sleep(for: .milliseconds(50))
                }
            case "cancel":
                let view = try await client.cancel(job: try command["job"].uuid())
                emit(.object(["done": .object(["state": .string(view.state)])]))
            case "download":
                guard let artifact = artifacts[try command["artifact_id"].text()] else { throw ConnectFailure.responseMalformed }
                let url = try await media.download(artifact, fetch: { offset in
                    try await client.artifactChunk(artifact, offset: offset, length: ChatWire.chunkBytes)
                }, progress: { _ in })
                emit(.object(["done": .object(["path": .string(url.path), "partial": .int(media.received(artifact))])]))
            case "partial":
                guard let artifact = artifacts[try command["artifact_id"].text()] else { throw ConnectFailure.responseMalformed }
                emit(.object(["done": .int(media.received(artifact))]))
            default:
                emit(.object(["failed": .string("unknown_command")]))
            }
        } catch let error as ChatRemoteError {
            emit(.object(["failed": .string(error.code)]))
        } catch let error as ChatMediaFailure {
            emit(.object(["failed": .string("media_" + String(describing: error))]))
        } catch {
            emit(.object(["failed": .string((error as? ConnectFailure)?.rawValue ?? "error")]))
        }
    }
}
