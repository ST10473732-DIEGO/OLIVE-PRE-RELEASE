import Foundation
import Observation

/// The open editor receives remote/undo edits as UTF-16 deltas (NSString ranges).
@MainActor
protocol NoteEditorBridge: AnyObject {
    var noteID: String { get }
    func apply(delta: [ConnectJSON])
    func reload(text: String)
}

struct NoteRow: Identifiable, Equatable {
    let id: String
    let title: String
    let displayTitle: String
    let preview: String
    let pinned: Bool
    let trashed: Bool
    let trashedAt: String
    let editedAt: String
    let status: String
    var snippet = ""

    init?(_ value: ConnectJSON) {
        guard let id = value["note_id"].string else { return nil }
        self.id = id
        title = value["title"].string ?? ""
        displayTitle = value["display_title"].string ?? "Untitled Note"
        preview = value["preview"].string ?? ""
        pinned = value["pinned"] == .bool(true)
        trashed = value["trashed"] == .bool(true)
        trashedAt = value["trashed_at"].string ?? ""
        editedAt = value["edited_at"].string ?? ""
        status = value["status"].string ?? "ok"
        snippet = value["snippet"].string ?? ""
    }
}

/// OLIVE Notes on the phone: local-first. Every edit is committed to the
/// on-device store before anything is sent. No account, cloud or AI needed.
@MainActor @Observable
final class NotesModel {
    private(set) var notes: [NoteRow] = []
    private(set) var trash: [NoteRow] = []
    private(set) var results: [NoteRow]?
    private(set) var available = true
    private(set) var unavailableReason = ""
    var notice: String?
    var query = "" { didSet { search() } }
    let sync = NotesSync()
    @ObservationIgnored private(set) var engine: NotesEngineHost?
    @ObservationIgnored weak var editor: NoteEditorBridge?
    @ObservationIgnored private let directory: URL
    @ObservationIgnored private var refreshTask: Task<Void, Never>?
    @ObservationIgnored private var tickTask: Task<Void, Never>?

    init(directory: URL) {
        self.directory = directory.appendingPathComponent("Notes", isDirectory: true)
    }

    /// Starts (or restarts, when the Connect identity appears) with this phone's
    /// device ID. Storage problems leave the database untouched and say so.
    func start(deviceID: String) {
        if engine?.deviceID == deviceID { return }
        do {
            let database = try engine?.database ?? NotesDatabase(directory: directory)
            let host = try NotesEngineHost(database: database, deviceID: deviceID, script: try NotesEngineHost.bundledScript())
            host.onEvent = { [weak self] event in self?.handle(event) }
            engine = host
            sync.attach(engine: host)
            available = true
            refresh()
        } catch NotesDatabase.Failure.newer {
            unavailable("Notes storage was created by a newer OLIVE. It was left untouched.")
        } catch NotesDatabase.Failure.unrecognized {
            unavailable("Notes storage migration failed. The original data was left untouched.")
        } catch {
            unavailable("Notes storage unavailable. Your notes on this phone were left untouched.")
        }
    }

    private func unavailable(_ reason: String) {
        engine = nil; available = false; unavailableReason = reason
    }

    private func rows(_ value: ConnectJSON?) -> [NoteRow] { value?.array?.compactMap(NoteRow.init) ?? [] }

    func refresh() {
        guard let engine else { return }
        notes = rows(try? engine.call("list", "notes"))
        trash = rows(try? engine.call("list", "trash"))
        if !query.isEmpty { search() }
    }

    private func scheduleRefresh() {
        refreshTask?.cancel()
        refreshTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(150))
            guard !Task.isCancelled else { return }
            self?.refresh()
        }
    }

    private func scheduleTick() {
        tickTask?.cancel()
        tickTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(1))
            guard !Task.isCancelled else { return }
            _ = try? self?.engine?.call("tick")
        }
    }

    /// Flush deferred local work (search index). Called when the app backgrounds.
    func flush() {
        tickTask?.cancel()
        _ = try? engine?.call("tick")
    }

    private func search() {
        let text = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, let engine else { results = nil; return }
        results = rows(try? engine.call("search", text)).filter { !$0.trashed }
    }

    private func handle(_ event: ConnectJSON) {
        let note = event["note_id"].string
        switch event["type"].string {
        case "delta":
            if let editor, editor.noteID == note, let delta = event["delta"].array { editor.apply(delta: delta) }
        case "reset":
            notice = "Could not save locally. The last change was not kept."
            if let editor, editor.noteID == note, let text = text(of: editor.noteID) { editor.reload(text: text) }
        case "purged":
            scheduleRefresh()
        default:
            scheduleRefresh()
            scheduleTick()
            if event["origin"] != .string("remote") { sync.kick() }
        }
    }

    // MARK: Actions (each one is committed locally before it returns)

    private func perform(_ method: String, _ arguments: Any...) -> ConnectJSON? {
        guard let engine else { notice = unavailableReason; return nil }
        do { return try engine.call(method, arguments: arguments) }
        catch NotesEngineHost.Failure.unavailable(let code) { notice = Self.message(code); return nil }
        catch { notice = "Could not save locally."; return nil }
    }

    static func message(_ code: String) -> String {
        [
            "note_too_large": "Note too large. Notes can hold up to about 1.5 MB of text.",
            "note_data_corrupted": "Note data corrupted. The stored data was kept for recovery.",
            "note_not_found": "That note no longer exists.",
            "note_purged": "That note was permanently deleted.",
            "notes_capacity": "Notes limit reached. Delete notes you no longer need.",
            "not_in_trash": "Move the note to Recently Deleted first.",
        ][code] ?? "Could not save locally."
    }

    func create() -> String? { perform("create", "", "")?["note_id"].string }
    func open(_ id: String) -> String? { perform("open", id)?["text"].string }
    func close(_ id: String) { _ = try? engine?.call("close", id); flush() }
    func text(of id: String) -> String? { (try? engine?.call("text", id))?.string }
    @discardableResult func edit(_ id: String, index: Int, remove: Int, insert: String) -> Bool {
        perform("edit", id, index, remove, insert) != nil
    }
    func rename(_ id: String, _ title: String) { _ = perform("rename", id, title) }
    func pin(_ id: String, _ pinned: Bool) { _ = perform("pin", id, pinned) }
    func moveToTrash(_ id: String) { _ = perform("trash", id) }
    func restore(_ id: String) { _ = perform("restore", id) }
    func purge(_ id: String) { _ = perform("purge", id) }
    func undo(_ id: String, redo: Bool = false) { _ = perform("undo", id, redo) }
    func row(_ id: String) -> NoteRow? { (notes + trash).first { $0.id == id } }
}
