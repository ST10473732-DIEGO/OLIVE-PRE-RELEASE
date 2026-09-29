import Foundation
import JavaScriptCore
import CryptoKit
import Security

/// Runs the shared OLIVE Notes engine (NotesEngine.js, built from
/// desktop/src/features/notes/engine) in JavaScriptCore. Same Yjs documents and
/// olive-notes/1 rules as the desktop. Storage stays in `NotesDatabase`; this
/// class only bridges calls. JSContext is single-threaded: use it on MainActor.
@MainActor
final class NotesEngineHost {
    enum Failure: Error, Equatable { case unavailable(String) }
    private let context: JSContext
    /// Set once the bundle has loaded (declared optional so the host closures
    /// below may capture `self` after every stored property is initialised).
    private var api: JSValue!
    let database: NotesDatabase
    private(set) var deviceID: String
    /// Engine events (delta / changed / reset / purged) as strict JSON.
    var onEvent: ((ConnectJSON) -> Void)?
    private var exception: String?

    init(database: NotesDatabase, deviceID: String, script: String) throws {
        self.database = database
        self.deviceID = deviceID
        guard let context = JSContext() else { throw Failure.unavailable("javascriptcore") }
        self.context = context
        context.name = "OLIVE Notes"
        let host = JSValue(newObjectIn: context)!
        let loadIndex: @convention(block) () -> String = { [unowned database] in (try? database.loadIndex()) ?? "{\"rows\":[],\"purges\":[],\"peers\":[],\"meta\":{\"store_seq\":0,\"epoch\":\"\"},\"unavailable\":true}" }
        let loadDocument: @convention(block) (String) -> String = { [unowned database] id in (try? database.loadDocument(id)) ?? "{\"corrupt\":true}" }
        let commit: @convention(block) (String) -> Bool = { [unowned database] batch in database.commit(batch) }
        let search: @convention(block) (String) -> String = { [unowned database] query in (try? database.search(query)) ?? "[]" }
        let sha256: @convention(block) (String) -> String = { encoded in NotesDatabase.sha256(Data(base64Encoded: encoded) ?? Data()) }
        let uuid: @convention(block) () -> String = { UUID().uuidString.lowercased() }
        let now: @convention(block) () -> String = {
            let formatter = ISO8601DateFormatter(); formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            return formatter.string(from: Date())
        }
        let nowSeconds: @convention(block) () -> Double = { floor(Date().timeIntervalSince1970) }
        let randomBytes: @convention(block) (Int) -> String = { count in
            var bytes = [UInt8](repeating: 0, count: max(0, min(count, 4096)))
            guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else { return "" }
            return Data(bytes).base64EncodedString()
        }
        host.setObject(loadIndex, forKeyedSubscript: "loadIndex" as NSString)
        host.setObject(loadDocument, forKeyedSubscript: "loadDocument" as NSString)
        host.setObject(commit, forKeyedSubscript: "commit" as NSString)
        host.setObject(search, forKeyedSubscript: "search" as NSString)
        host.setObject(sha256, forKeyedSubscript: "sha256" as NSString)
        host.setObject(uuid, forKeyedSubscript: "uuid" as NSString)
        host.setObject(now, forKeyedSubscript: "now" as NSString)
        host.setObject(nowSeconds, forKeyedSubscript: "nowSeconds" as NSString)
        host.setObject(randomBytes, forKeyedSubscript: "randomBytes" as NSString)
        let emit: @convention(block) (String) -> Void = { [weak self] raw in
            // Called synchronously from engine code already running on MainActor.
            MainActor.assumeIsolated {
                guard let self, let event = try? ConnectJSON.decode(Data(raw.utf8), limit: 4_000_000) else { return }
                self.onEvent?(event)
            }
        }
        host.setObject(emit, forKeyedSubscript: "emit" as NSString)
        context.setObject(host, forKeyedSubscript: "OliveNotesHost" as NSString)
        context.exceptionHandler = { [weak self] _, value in
            // Never log note content: record only that an engine exception occurred.
            MainActor.assumeIsolated { self?.exception = value?.objectForKeyedSubscript("name")?.toString() ?? "Error" }
        }
        context.evaluateScript(script)
        guard exception == nil, let api = context.objectForKeyedSubscript("OliveNotes"), !api.isUndefined else {
            throw Failure.unavailable("engine_load")
        }
        self.api = api
        let started = try call("start", deviceID)
        guard started == .bool(true) else { throw Failure.unavailable("engine_start") }
    }

    static func bundledScript(_ bundle: Bundle = .main) throws -> String {
        guard let url = bundle.url(forResource: "NotesEngine", withExtension: "js"),
              let script = try? String(contentsOf: url, encoding: .utf8) else { throw Failure.unavailable("engine_missing") }
        return script
    }

    private func invoke(_ method: String, _ arguments: [Any]) throws -> String {
        exception = nil
        guard let function = api.objectForKeyedSubscript(method), !function.isUndefined,
              let result = function.call(withArguments: arguments), exception == nil, result.isString,
              let text = result.toString() else { throw Failure.unavailable(exception ?? "engine_call") }
        return text
    }

    /// A wrapped call: {"ok": true, "value": ...} or {"ok": false, "error": code}.
    @discardableResult
    func call(_ method: String, _ arguments: Any...) throws -> ConnectJSON { try call(method, arguments: arguments) }

    @discardableResult
    func call(_ method: String, arguments: [Any]) throws -> ConnectJSON {
        let value = try ConnectJSON.decode(Data(try invoke(method, arguments).utf8), limit: 8_000_000)
        guard value["ok"] == .bool(true) else { throw Failure.unavailable(value["error"].string ?? "notes_unavailable") }
        return value["value"]
    }

    /// Raw olive-notes/1 plumbing (handle/next/answer) returns engine JSON text.
    func raw(_ method: String, _ arguments: Any...) throws -> String { try invoke(method, arguments) }
    func raw(_ method: String, arguments: [Any]) throws -> String { try invoke(method, arguments) }
}
