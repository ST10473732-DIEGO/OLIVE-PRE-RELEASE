import Foundation
import CryptoKit

/// olive-chat/1 (Remote Chat v2) on frames 17/18: every OLIVE Chat mode, attachments
/// and media artifacts over the existing authenticated Connect channel.
///
/// One packet per frame: a 4-byte big-endian JSON length, strict canonical JSON,
/// then an optional raw binary tail (an attachment or artifact chunk). The phone
/// only sends frame 17 after the computer listed `olive-chat/1` in its protocol
/// probe; an older computer keeps the olive-inference/1 FAST/NORMAL/MAX path.
/// Bounds are shared with olive/connect/chat_protocol.py.
enum ChatWire {
    static let name = "olive-chat/1"
    static let maximumJSON = 96_000
    static let chunkBytes = 131_072
    static let maximumFrame = 4 + maximumJSON + chunkBytes
    static let maximumOutput = 64_000
    static let maximumAttachments = 4
    static let modes = ["fast", "normal", "max", "uncensored", "now", "deep", "reimagine", "audio", "video"]
    static let attachmentKinds: Set<String> = ["image", "document", "note"]
    static let states: Set<String> = ["not_received", "awaiting_approval", "queued", "running", "completed", "cancelled", "failed", "outcome_unknown"]
    static let terminal: Set<String> = ["completed", "cancelled", "failed", "outcome_unknown"]
    static let phases: Set<String> = ["", "approval", "queued", "thinking", "retrieving", "reading_documents", "indexing", "synthesizing",
        "releasing_gpu", "preparing_image_engine", "generating_image", "preparing_audio_engine", "generating_speech",
        "preparing_video_engine", "generating_video", "saving"]
    static let operations: Set<String> = ["capabilities", "attachment_offer", "attachment_chunk", "start", "poll", "cancel", "artifact_chunk"]
    /// Additive extensions this build parses. Asked for in `capabilities`; an older
    /// computer refuses the argument (invalid_request) and is asked again without it.
    static let extensions = ["mode_options/1"]
    static func capabilitiesArguments(extended: Bool) -> ConnectJSON {
        extended ? .object(["accept": .array(extensions.map(ConnectJSON.string))]) : .object([:])
    }

    // MARK: Packets

    static func packet(_ value: ConnectJSON, binary: Data = Data()) throws -> Data {
        let json = value.canonical
        guard json.count <= maximumJSON, binary.count <= chunkBytes else { throw ConnectFailure.inputTooLarge }
        return ConnectFrame.length(json.count) + json + binary
    }
    static func unpack(_ data: Data) throws -> (ConnectJSON, Data) {
        guard (4...maximumFrame).contains(data.count) else { throw ConnectFailure.responseMalformed }
        let size = data.prefix(4).reduce(0) { ($0 << 8) | Int($1) }
        guard (2...maximumJSON).contains(size), size + 4 <= data.count else { throw ConnectFailure.responseMalformed }
        let value = try ConnectJSON.decode(Data(data.dropFirst(4).prefix(size)), limit: maximumJSON)
        return (value, Data(data.dropFirst(4 + size)))
    }
    /// The request id of a response packet, for transport correlation only.
    static func correlation(_ data: Data) throws -> String {
        let (value, _) = try unpack(data)
        guard value["protocol_version"] == .string(name) else { throw ConnectFailure.responseMalformed }
        return try value["request_id"].uuid()
    }

    // MARK: Requests

    static func request(source: String, target: String, operation: String, arguments: ConnectJSON,
                        id: String = UUID().uuidString.lowercased(), now: Int64 = Int64(Date().timeIntervalSince1970)) throws -> ConnectJSON {
        guard operations.contains(operation) else { throw ConnectFailure.capabilityUnavailable }
        for value in [source, target, id] { _ = try ConnectJSON.string(value).uuid() }
        return .object(["protocol_version": .string(name), "request_id": .string(id), "source_device_id": .string(source),
                        "target_device_id": .string(target), "operation": .string(operation), "arguments": arguments,
                        "timestamp": .int(now), "expires_at": .int(now + 120)])
    }

    /// The exact start arguments. Their fingerprint excludes the job id and time,
    /// so resending the same request after a lost acknowledgement is idempotent.
    static func startArguments(job: String, conversation: String, mode: String, voice: String?,
                               messages: [(String, String)], attachments: [ChatAttachmentDescriptor],
                               options: ConnectJSON? = nil) throws -> ConnectJSON {
        guard modes.contains(mode) else { throw ConnectFailure.capabilityUnavailable }
        _ = try ConnectJSON.string(job).uuid(); _ = try ConnectJSON.string(conversation).uuid()
        guard (1...24).contains(messages.count), messages.last?.0 == "user", attachments.count <= maximumAttachments else { throw ConnectFailure.inputTooLarge }
        var total = 0
        let list = ConnectJSON.array(try messages.map { role, content in
            guard ["user", "assistant"].contains(role), !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw ConnectFailure.responseMalformed }
            guard content.utf8.count <= 16000 else { throw ConnectFailure.inputTooLarge }
            total += content.utf8.count
            return .object(["role": .string(role), "content": .string(content)])
        })
        guard total <= 48000 else { throw ConnectFailure.inputTooLarge }
        var arguments: [String: ConnectJSON] = ["job_id": .string(job), "conversation_id": .string(conversation), "mode": .string(mode),
            "voice": voice.map(ConnectJSON.string) ?? .null, "messages": list, "attachments": .array(attachments.map(\.wire))]
        // Options (VIDEO duration) are part of the request identity: 5 s and 20 s never collide.
        if let options {
            guard mode == "video", options.object != nil else { throw ConnectFailure.capabilityUnavailable }
            arguments["options"] = options
        }
        arguments["input_fingerprint"] = .string(ConnectJSON.object(arguments.filter { $0.key != "job_id" }).digest)
        return .object(arguments)
    }

    // MARK: Responses

    struct Response: Sendable { let result: ConnectJSON; let error: String?; let binary: Data }

    static func response(_ data: Data, request: ConnectJSON) throws -> Response {
        let (v, binary) = try unpack(data)
        try v.fields(["protocol_version", "request_id", "result", "error"])
        guard v["protocol_version"] == .string(name), v["request_id"] == request["request_id"] else { throw ConnectFailure.responseMalformed }
        if v["error"] != .null {
            let code = try v["error"].text()
            // Codes are typed; an unknown future code is still a bounded identifier.
            guard code.range(of: "^[a-z_]{1,64}$", options: .regularExpression) != nil, v["result"] == .null, binary.isEmpty else { throw ConnectFailure.responseMalformed }
            return Response(result: .null, error: code, binary: Data())
        }
        let operation = try request["operation"].text()
        guard operation == "artifact_chunk" || binary.isEmpty else { throw ConnectFailure.responseMalformed }
        return Response(result: v["result"], error: nil, binary: binary)
    }

    static func capabilities(_ r: ConnectJSON) throws -> ChatCapabilities {
        try r.fields(["chat_protocol", "permission", "modes", "limits"], optional: ["extensions"])
        var granted: [String] = []
        if r["extensions"] != .null {
            guard let list = r["extensions"].array, list.count <= 8 else { throw ConnectFailure.responseMalformed }
            granted = try list.map { try StudioWire.bounded($0, 40) }.filter(extensions.contains)
        }
        guard r["chat_protocol"] == .string(name), ["deny", "ask", "allow"].contains(r["permission"].string ?? ""),
              let modes = r["modes"].array, modes.count <= 32 else { throw ConnectFailure.responseMalformed }
        try r["limits"].fields(["chunk_bytes", "max_attachments", "max_output_bytes"])
        let chunk = try r["limits"]["chunk_bytes"].number(1024...Int64(chunkBytes))
        var parsed: [RemoteModeCapability] = []
        for mode in modes {
            let value = try RemoteModeCapability(mode)
            // A newer computer may offer modes this phone does not know: ignore them.
            if Self.modes.contains(value.id), !parsed.contains(where: { $0.id == value.id }) { parsed.append(value) }
        }
        return ChatCapabilities(permission: r["permission"].string!, modes: parsed, chunkBytes: Int(chunk), extensions: granted)
    }

    static func attachmentState(_ r: ConnectJSON, id: String) throws -> (present: Bool, received: Int64) {
        try r.fields(["attachment_id", "state", "received"])
        guard r["attachment_id"] == .string(id), ["present", "partial"].contains(r["state"].string ?? "") else { throw ConnectFailure.responseMalformed }
        return (r["state"] == .string("present"), try r["received"].number(0...Int64(64 * 1024 * 1024)))
    }

    static func view(_ r: ConnectJSON, job: String, after: Int) throws -> ChatJobView {
        try r.fields(["job_id", "state", "phase", "text", "offset", "total", "sources", "artifacts", "attribution", "error"], optional: ["progress"])
        guard r["job_id"] == .string(job), states.contains(r["state"].string ?? ""), phases.contains(r["phase"].string ?? "-") else { throw ConnectFailure.responseMalformed }
        let text = try r["text"].text()
        let offset = try r["offset"].number(0...Int64(maximumOutput)), total = try r["total"].number(0...Int64(maximumOutput))
        guard text.utf8.count <= 16_000, offset + Int64(text.utf8.count) <= total, text.isEmpty || offset == Int64(after) else { throw ConnectFailure.responseMalformed }
        guard let sources = r["sources"].array, sources.count <= 12, let artifacts = r["artifacts"].array, artifacts.count <= 4 else { throw ConnectFailure.responseMalformed }
        var attribution: ChatAttribution?
        if r["attribution"] != .object([:]) { attribution = try ChatAttribution(r["attribution"]) }
        var error: String?
        if r["error"] != .null {
            let code = try r["error"].text()
            guard code.range(of: "^[a-z_]{1,64}$", options: .regularExpression) != nil else { throw ConnectFailure.responseMalformed }
            error = code
        }
        return ChatJobView(jobID: job, state: r["state"].string!, phase: r["phase"].string!, text: text, offset: Int(offset), total: Int(total),
                           sources: try sources.map(ChatSource.init), artifacts: try artifacts.map(ChatArtifact.init), attribution: attribution, error: error,
                           progress: try ChatProgress(r["progress"]))
    }

    static func artifactChunk(_ response: Response, artifact: ChatArtifact, offset: Int64) throws -> Data {
        let r = response.result
        try r.fields(["artifact_id", "offset", "size", "sha256"])
        guard r["artifact_id"] == .string(artifact.artifactID), r["offset"] == .int(offset), r["size"] == .int(artifact.size),
              r["sha256"] == .string(artifact.sha256), !response.binary.isEmpty,
              offset + Int64(response.binary.count) <= artifact.size else { throw ConnectFailure.responseMalformed }
        return response.binary
    }
}

// MARK: - Typed values

struct ChatAttachmentDescriptor: Codable, Equatable, Hashable, Sendable {
    /// SHA-256 of the exact bytes: the content address. Integrity only; TLS is authentication.
    let id: String
    let kind: String
    let mime: String
    let size: Int64
    let name: String
    var wire: ConnectJSON {
        .object(["attachment_id": .string(id), "kind": .string(kind), "mime": .string(mime), "size": .int(size), "name": .string(name)])
    }
}

struct ChatVoice: Codable, Equatable, Hashable, Sendable, Identifiable {
    let id: String
    let name: String
}

struct RemoteModeCapability: Equatable, Sendable, Identifiable {
    let id: String
    let available: Bool
    let reason: String
    let imageMax: Int
    let imageMaxBytes: Int64
    let documentMax: Int
    let documentMaxBytes: Int64
    let documentMimes: [String]
    let noteMax: Int
    let noteMaxBytes: Int64
    let outputs: [String]
    let citations: Bool
    let stream: Bool
    let promptRequired: Bool
    let voices: [ChatVoice]
    let limitations: [String]
    /// VIDEO details (mode_options/1). nil from a computer without the extension.
    let video: VideoCapability?

    init(_ v: ConnectJSON) throws {
        try v.fields(["id", "available", "reason", "inputs", "outputs", "citations", "stream", "cancel", "prompt_required", "tiers", "voices", "limitations"],
                     optional: ["options"])
        try v["inputs"].fields(["image", "document", "note"])
        try v["inputs"]["image"].fields(["max", "max_bytes", "mimes"])
        try v["inputs"]["document"].fields(["max", "max_bytes", "mimes"])
        try v["inputs"]["note"].fields(["max", "max_bytes"])
        id = try StudioWire.bounded(v["id"], 32)
        guard let available = v["available"].boolean, let citations = v["citations"].boolean, let stream = v["stream"].boolean,
              let prompt = v["prompt_required"].boolean, v["cancel"].boolean != nil else { throw ConnectFailure.responseMalformed }
        self.available = available; self.citations = citations; self.stream = stream; promptRequired = prompt
        reason = try StudioWire.bounded(v["reason"], 64)
        let limit: ClosedRange<Int64> = 0...(64 * 1024 * 1024)
        imageMax = Int(try v["inputs"]["image"]["max"].number(0...8)); imageMaxBytes = try v["inputs"]["image"]["max_bytes"].number(limit)
        documentMax = Int(try v["inputs"]["document"]["max"].number(0...8)); documentMaxBytes = try v["inputs"]["document"]["max_bytes"].number(limit)
        noteMax = Int(try v["inputs"]["note"]["max"].number(0...8)); noteMaxBytes = try v["inputs"]["note"]["max_bytes"].number(limit)
        guard let mimes = v["inputs"]["document"]["mimes"].array, mimes.count <= 16, let outputs = v["outputs"].array, outputs.count <= 4,
              let voices = v["voices"].array, voices.count <= 32, let limitations = v["limitations"].array, limitations.count <= 16,
              v["tiers"].array != nil else { throw ConnectFailure.responseMalformed }
        documentMimes = try mimes.map { try StudioWire.bounded($0, 100) }
        self.outputs = try outputs.map { try StudioWire.bounded($0, 16) }
        self.voices = try voices.map { voice in
            try voice.fields(["id", "name"])
            return ChatVoice(id: try StudioWire.bounded(voice["id"], 80), name: try StudioWire.bounded(voice["name"], 120))
        }
        self.limitations = try limitations.map { try StudioWire.bounded($0, 40) }
        let options = v["options"]
        guard options == .null || options.object != nil else { throw ConnectFailure.responseMalformed }
        if id == "video", let fields = options.object, !fields.isEmpty {
            video = try VideoCapability(options)
        } else {
            video = nil
        }
    }

    init(id: String, available: Bool, reason: String = "", imageMax: Int = 0, documentMax: Int = 0, documentMimes: [String] = [],
         noteMax: Int = 0, outputs: [String] = ["text"], citations: Bool = false, promptRequired: Bool = false,
         voices: [ChatVoice] = [], limitations: [String] = [], video: VideoCapability? = nil) {
        self.id = id; self.available = available; self.reason = reason
        self.imageMax = imageMax; imageMaxBytes = 20 * 1024 * 1024
        self.documentMax = documentMax; documentMaxBytes = 32 * 1024 * 1024; self.documentMimes = documentMimes
        self.noteMax = noteMax; noteMaxBytes = 192 * 1024
        self.outputs = outputs; self.citations = citations; stream = outputs == ["text"]; self.promptRequired = promptRequired
        self.voices = voices; self.limitations = limitations; self.video = video
    }

    func maximum(_ kind: String) -> Int { kind == "image" ? imageMax : kind == "document" ? documentMax : kind == "note" ? noteMax : 0 }
    func maximumBytes(_ kind: String) -> Int64 { kind == "image" ? imageMaxBytes : kind == "document" ? documentMaxBytes : noteMaxBytes }
}

struct ChatCapabilities: Equatable, Sendable {
    let permission: String
    let modes: [RemoteModeCapability]
    let chunkBytes: Int
    var extensions: [String] = []
    func mode(_ id: String) -> RemoteModeCapability? { modes.first { $0.id == id } }
    /// The computer accepts `start.options` and reports structured progress.
    var modeOptions: Bool { extensions.contains("mode_options/1") }
}

struct ChatAttribution: Codable, Equatable, Sendable {
    let mode: String
    let tier: String
    let label: String
    init(mode: String, tier: String = "") {
        self.mode = mode; self.tier = tier
        label = mode.uppercased() + (tier.isEmpty ? "" : " · " + tier)
    }
    init(_ v: ConnectJSON) throws {
        try v.fields(["mode", "tier", "label"])
        mode = try StudioWire.bounded(v["mode"], 32); tier = try StudioWire.bounded(v["tier"], 40); label = try StudioWire.bounded(v["label"], 80)
        guard ChatWire.modes.contains(mode) else { throw ConnectFailure.responseMalformed }
    }
}

/// Structured evidence as the computer supplied it. Never parsed from answer prose.
struct ChatSource: Codable, Equatable, Sendable {
    let id: String
    let kind: String
    let title: String
    let provider: String?
    let url: URL?
    let publishedAt: String?
    let updatedAt: String?
    let retrievedAt: String?
    let page: Int?
    let snapshot: Bool
    let excerpt: String?

    init(_ v: ConnectJSON) throws {
        try v.fields(["id", "kind", "title", "provider", "url", "published_at", "updated_at", "retrieved_at", "page", "snapshot", "excerpt"])
        func optional(_ key: String, _ max: Int) throws -> String? { v[key] == .null ? nil : try StudioWire.bounded(v[key], max) }
        id = try StudioWire.bounded(v["id"], 8)
        kind = try StudioWire.bounded(v["kind"], 16)
        title = try StudioWire.bounded(v["title"], 1200)
        provider = try optional("provider", 800)
        url = try optional("url", 2000).flatMap(Self.safeURL)
        publishedAt = try optional("published_at", 40); updatedAt = try optional("updated_at", 40); retrievedAt = try optional("retrieved_at", 40)
        page = v["page"] == .null ? nil : Int(try v["page"].number(1...999_999))
        guard let snapshot = v["snapshot"].boolean else { throw ConnectFailure.responseMalformed }
        self.snapshot = snapshot
        excerpt = try optional("excerpt", 1600)
    }

    /// Only ordinary web links open, in the system browser. Never javascript:, file: or custom schemes.
    static func safeURL(_ text: String) -> URL? {
        guard let url = URL(string: text), let scheme = url.scheme?.lowercased(), ["https", "http"].contains(scheme),
              let host = url.host, !host.isEmpty, url.user == nil, url.password == nil else { return nil }
        return url
    }
}

/// A media result descriptor. The bytes are transferred separately and verified.
struct ChatArtifact: Codable, Equatable, Sendable, Identifiable {
    var id: String { artifactID }
    let artifactID: String
    let kind: String
    let mime: String
    let size: Int64
    let sha256: String
    let width: Int?
    let height: Int?
    let durationMS: Int?
    let hasAudio: Bool?
    let mode: String
    let label: String

    static let maximumBytes: [String: Int64] = ["image": 64 * 1024 * 1024, "audio": 128 * 1024 * 1024, "video": 1024 * 1024 * 1024]
    static let mimes = ["image": "image/png", "audio": "audio/wav", "video": "video/mp4"]

    init(_ v: ConnectJSON) throws {
        try v.fields(["artifact_id", "kind", "mime", "size", "sha256", "width", "height", "duration_ms", "has_audio", "completion_state", "mode", "label"])
        artifactID = try StudioWire.bounded(v["artifact_id"], 32)
        guard artifactID.range(of: "^[0-9a-f]{32}$", options: .regularExpression) != nil, v["completion_state"] == .string("complete") else { throw ConnectFailure.responseMalformed }
        kind = try StudioWire.bounded(v["kind"], 16)
        mime = try StudioWire.bounded(v["mime"], 40)
        // Absurd metadata is refused before any transfer; declared type must match its kind.
        guard let limit = Self.maximumBytes[kind], Self.mimes[kind] == mime else { throw ConnectFailure.responseMalformed }
        size = try v["size"].number(1...limit)
        sha256 = try StudioWire.hash(v["sha256"])
        width = v["width"] == .null ? nil : Int(try v["width"].number(1...16384))
        height = v["height"] == .null ? nil : Int(try v["height"].number(1...16384))
        durationMS = v["duration_ms"] == .null ? nil : Int(try v["duration_ms"].number(1...86_400_000))
        hasAudio = v["has_audio"] == .null ? nil : v["has_audio"].boolean
        if v["has_audio"] != .null, hasAudio == nil { throw ConnectFailure.responseMalformed }
        mode = try StudioWire.bounded(v["mode"], 32)
        label = try StudioWire.bounded(v["label"], 40)
    }

    init(artifactID: String, kind: String, mime: String, size: Int64, sha256: String, width: Int? = nil, height: Int? = nil,
         durationMS: Int? = nil, hasAudio: Bool? = nil, mode: String, label: String = "") {
        self.artifactID = artifactID; self.kind = kind; self.mime = mime; self.size = size; self.sha256 = sha256
        self.width = width; self.height = height; self.durationMS = durationMS; self.hasAudio = hasAudio; self.mode = mode; self.label = label
    }

    var fileExtension: String { ["image": "png", "audio": "wav", "video": "mp4"][kind] ?? "bin" }
    var known: Bool { Self.mimes[kind] == mime }
}

struct ChatJobView: Sendable {
    let jobID: String
    let state: String
    let phase: String
    let text: String
    let offset: Int
    let total: Int
    let sources: [ChatSource]
    let artifacts: [ChatArtifact]
    let attribution: ChatAttribution?
    let error: String?
    var progress: ChatProgress? = nil
    var terminal: Bool { ChatWire.terminal.contains(state) }
}
