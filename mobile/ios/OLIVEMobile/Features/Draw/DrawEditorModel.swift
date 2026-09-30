import Foundation
import Observation
import UIKit

/// One open drawing: its replica (records → visible operations), local view
/// state (tool, colour, size, opacity, zoom — never synced) and the canvas.
///
/// A completed gesture is appended through the engine (one record, one
/// transaction, durable before the call returns) and then applied to the
/// replica. Remote records are pulled by feed position and applied in any
/// order; the canvas redraws incrementally when the only change is a new
/// operation at the end, and replays otherwise. A gesture in progress is never
/// cancelled by a remote change: it is committed on touch-up against the
/// updated Lamport state.
@MainActor @Observable
final class DrawEditorModel: DrawCanvasDelegate {
    enum Tool: String { case pen, erase }
    enum SaveState: Equatable { case saved, saving, failed(String) }

    let drawingID: String
    private(set) var summary: DrawSummary?
    private(set) var visibleCount = 0
    private(set) var background = "#ffffff"
    private(set) var undoCount = 0
    private(set) var redoCount = 0
    private(set) var missingAssets: Set<String> = []
    private(set) var saveState: SaveState = .saved
    private(set) var loadError: String?
    private(set) var zoom = 1.0
    private(set) var busy: String?
    var notice: String?
    var tool: Tool = .pen { didSet { if oldValue != tool { haptic() } } }
    var color: String { didSet { saveBrush() } }
    var width: Double { didSet { saveBrush() } }
    var opacity: Double { didSet { saveBrush() } }

    @ObservationIgnored private let engine: DrawEngine
    @ObservationIgnored private let defaults: UserDefaults
    @ObservationIgnored private var replica: DrawReplica
    @ObservationIgnored private var ops: [DrawOp] = []
    @ObservationIgnored private var cursor: Int64 = 0
    @ObservationIgnored private weak var canvas: DrawCanvasUIView?
    @ObservationIgnored let images: DrawImageCache
    @ObservationIgnored private var pullTask: Task<Void, Never>?
    @ObservationIgnored private var pullAgain = false
    @ObservationIgnored private var commits: [DrawOp] = []
    @ObservationIgnored private var committing = false
    @ObservationIgnored private var thumbnailTask: Task<Void, Never>?
    @ObservationIgnored weak var library: DrawModel?

    static let brushKey = "olive.draw.brush"

    init(drawingID: String, engine: DrawEngine, defaults: UserDefaults = .standard) {
        self.drawingID = drawingID
        self.engine = engine
        self.defaults = defaults
        replica = DrawReplica(drawingID: drawingID)
        images = DrawImageCache(engine: engine)
        let brush = defaults.dictionary(forKey: Self.brushKey) ?? [:]
        let storedColor = brush["color"] as? String ?? "#000000"
        color = DrawText.isColor(storedColor) ? storedColor : "#000000"
        width = DrawBrush.size(brush["size"] as? Double ?? 8)
        opacity = min(1, max(0.01, brush["opacity"] as? Double ?? 1))
        images.onChange = { [weak self] in self?.imagesChanged() }
    }

    private func saveBrush() { defaults.set(["color": color, "size": width, "opacity": opacity], forKey: Self.brushKey) }

    func attach(canvas: DrawCanvasUIView) {
        self.canvas = canvas
        canvas.delegate = self
        canvas.imageSnapshot = { [weak self] in self?.images.snapshot() ?? [:] }
        pushAll()
    }

    // MARK: Loading and remote changes

    func load() async {
        do {
            var page = try await engine.since(drawingID, after: 0)
            summary = page.drawing
            apply(page.records)
            while page.more {
                page = try await engine.since(drawingID, after: page.cursor)
                apply(page.records)
            }
            cursor = page.cursor
            undoCount = page.undo; redoCount = page.redo
            refreshDerived()
            pushAll()
        } catch {
            loadError = (error as? DrawError)?.errorDescription ?? "Could not load drawing. The stored data was kept for recovery."
        }
    }

    @discardableResult
    private func apply(_ records: [DrawRecord]) -> [DrawReplica.Change] {
        records.map { replica.apply($0) }
    }

    private func refreshDerived() {
        ops = replica.visible()
        visibleCount = ops.count
        background = ops.effectiveBackground(replica.create?.background ?? summary?.background ?? "#ffffff")
        let referenced = Set(ops.compactMap(\.assetID))
        images.require(referenced)
        missingAssets = referenced.subtracting(images.snapshot().keys).intersection(referenced)
    }

    private func pushAll() {
        guard let canvas, let create = replica.create else { return }
        canvas.load(size: CGSize(width: create.width, height: create.height), background: background, ops: ops,
                    missing: missingAssets.intersection(images.missing))
    }

    /// Another device committed records: pull them by feed position.
    func remoteChanged() { Task { await requestPull() } }

    /// Pulls are serialized (the feed cursor only moves forward); a request made
    /// while one runs is folded into it.
    private func requestPull() async {
        pullAgain = true
        if let running = pullTask { await running.value; return }
        let task = Task { @MainActor in
            while pullAgain { pullAgain = false; await pull() }
            pullTask = nil
        }
        pullTask = task
        await task.value
    }

    private func pull() async {
        trace("pull after \(cursor)")
        defer { trace("pull done at \(cursor)") }
        do {
            var page: DrawPage
            var changes: [DrawReplica.Change] = []
            repeat {
                page = try await engine.since(drawingID, after: cursor)
                changes += apply(page.records)
                cursor = page.cursor
            } while page.more
            summary = page.drawing
            undoCount = page.undo; redoCount = page.redo
            let before = ops
            refreshDerived()
            let visible = changes.filter(\.changed)
            if visible.count == 1, visible[0].appended, ops.count == before.count + 1, Array(ops.dropLast()) == before, let last = ops.last {
                canvas?.append(last, background: background, missing: missingAssets.intersection(images.missing))
            } else if ops != before || changes.contains(where: \.meta) {
                pushAll()
            }
        } catch let error as DrawError where error.code == "drawing_purged" {
            purgedElsewhere()
        } catch {
            notice = (error as? DrawError)?.errorDescription
        }
    }

    func purgedElsewhere() {
        loadError = "This drawing was permanently deleted."
        canvas?.load(size: canvas?.documentSize ?? .zero, background: "#ffffff", ops: [], missing: [])
    }

    func assetArrived(_ id: String) { images.arrived(id) }

    private func imagesChanged() {
        let referenced = Set(ops.compactMap(\.assetID))
        missingAssets = referenced.subtracting(images.snapshot().keys)
        pushAll()   // An arriving image replaces its placeholder without reopening.
    }

    // MARK: Local edits

    func canvasCommit(_ op: DrawOp) {
        commits.append(op)
        saveState = .saving
        drainCommits()
    }

    private func drainCommits() {
        guard !committing, !commits.isEmpty else { return }
        committing = true
        Task {
            defer { committing = false; if !commits.isEmpty { drainCommits() } }
            while !commits.isEmpty {
                let op = commits.removeFirst()
                if let refusal = check(op) { notice = refusal; canvas?.discardLive(); continue }
                do {
                    trace("commit append")
                    let edit = try await engine.append(drawingID, op)
                    try await applyLocal(edit)
                    saveState = .saved
                    scheduleThumbnail()
                } catch let error as DrawError {
                    // Refused for good (size limit, trashed drawing): drop it and say so.
                    saveState = .failed(error.errorDescription ?? "Could not save drawing.")
                    notice = error.errorDescription
                    canvas?.discardLive()
                } catch {
                    saveState = .failed("Could not save drawing.")
                    canvas?.discardLive()
                }
            }
        }
    }

    /// Refuse (never truncate) an edit past the per-operation limits.
    private func check(_ op: DrawOp) -> String? {
        if op.json.canonical.count > DrawSpec.Limit.maxOperationBytes { return "That stroke is too long to save. Draw it in shorter strokes." }
        if visibleCount + 1 > DrawSpec.Limit.maxOperations { return "This drawing reached 20,000 edits. Start a new drawing or clear this one." }
        return nil
    }

    /// Apply our own committed record(s) and any remote records that arrived meanwhile.
    /// Our own committed record is applied at once (records are idempotent), so
    /// a local edit never waits for a remote pull; the pull then catches up with
    /// anything that arrived meanwhile, in the background.
    private func applyLocal(_ edit: DrawEdit) async throws {
        undoCount = edit.undo; redoCount = edit.redo
        if let record = edit.record {
            let before = ops
            let change = replica.apply(record)
            refreshDerived()
            trace("local \(record.kind) applied")
            if change.appended, ops.count == before.count + 1, let last = ops.last {
                canvas?.append(last, background: background, missing: missingAssets.intersection(images.missing))
            } else if ops != before {
                pushAll()
            }
        }
        remoteChanged()
    }

    func canvasViewportChanged(zoom: Double) { self.zoom = zoom }
    func canvasLimited() { notice = "This stroke reached 10,000 points. Lift your finger and continue with a new stroke." }

    func undo() { step(redo: false) }
    func redo() { step(redo: true) }

    private func step(redo: Bool) {
        Task {
            do {
                let edit = redo ? try await engine.redo(drawingID) : try await engine.undo(drawingID)
                haptic()
                try await applyLocal(edit)
                scheduleThumbnail()
            } catch { notice = (error as? DrawError)?.errorDescription }
        }
    }

    func clear() { canvasCommit(.clear(id: DrawText.randomID())) }

    func setBackground(_ value: String) {
        guard DrawSpec.backgrounds.contains(value), value != background else { return }
        canvasCommit(.background(id: DrawText.randomID(), value: value))
    }

    func fit() { canvas?.fit() }
    func setZoom(_ value: Double) { canvas?.setZoom(value) }

    /// Import a user-chosen image (Photos, Files or Camera). The bytes are
    /// canonicalized off the main thread (orientation, sRGB, metadata stripped)
    /// and stored as an OLIVE-owned asset; the source is never referenced again.
    func importImage(_ data: Data) async {
        guard let summary, busy == nil else { return }
        busy = "Importing…"
        defer { busy = nil }
        do {
            let width = summary.width, height = summary.height
            let imported = try await Task.detached(priority: .userInitiated) {
                try DrawAssets.canonicalize(data, canvasWidth: width, canvasHeight: height)
            }.value
            let edit = try await engine.addImage(drawingID, imported)
            try await applyLocal(edit)
            notice = "Imported (\(imported.width) × \(imported.height)). The drawing keeps its own copy; the original is not needed any more."
            scheduleThumbnail()
        } catch let failure as DrawAssets.Failure {
            notice = DrawError(failure.code).errorDescription
        } catch {
            notice = (error as? DrawError)?.errorDescription ?? "Could not import image."
        }
    }

    /// Flatten at document resolution (independent of zoom) and write a file
    /// with a sanitized name for the share sheet. Refuses while an image is arriving.
    func export(jpeg: Bool) async -> URL? {
        guard let summary else { return nil }
        let referenced = Set(ops.compactMap(\.assetID))
        let decoded = images.snapshot()
        guard referenced.isSubset(of: decoded.keys) else {
            notice = "Could not export image: an imported image has not arrived on this phone yet. Try again in a moment."
            return nil
        }
        busy = "Exporting…"
        defer { busy = nil }
        let ops = self.ops, background = self.background, width = summary.width, height = summary.height
        let name = DrawText.exportName(summary.title, ext: jpeg ? "jpg" : "png")
        let data = await Task.detached(priority: .userInitiated) { () -> Data? in
            guard let image = DrawRender.rasterize(ops, width: width, height: height, background: background, jpeg: jpeg,
                                                   images: { decoded[$0] }) else { return nil }
            return DrawRender.encode(image, jpeg: jpeg, quality: 0.92)
        }.value
        guard let data else { notice = "Could not export image."; return nil }
        do {
            let folder = FileManager.default.temporaryDirectory.appendingPathComponent("DrawExport", isDirectory: true)
            try? FileManager.default.removeItem(at: folder)   // Only the latest export is kept, briefly.
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            let url = folder.appendingPathComponent(name)
            try data.write(to: url, options: [.atomic, .completeFileProtection])
            return url
        } catch {
            notice = "Could not export image."
            return nil
        }
    }

    // MARK: Thumbnails and lifecycle

    private func scheduleThumbnail() {
        thumbnailTask?.cancel()
        thumbnailTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(1))
            guard let self, !Task.isCancelled else { return }
            await self.writeThumbnail()
        }
    }

    private func writeThumbnail() async {
        guard let summary = try? await engine.summary(drawingID), let create = replica.create else { return }
        let ops = self.ops, images = self.images.snapshot()
        guard Set(ops.compactMap(\.assetID)).isSubset(of: images.keys) else { return }   // Thumbnails wait for images too.
        let rendered = await Task.detached(priority: .utility) {
            DrawModel.thumbnailData(ops: ops, width: create.width, height: create.height, background: create.background, images: images)
        }.value
        guard let (mime, data) = rendered else { return }
        try? await engine.putThumbnail(drawingID, revision: summary.revision, mime: mime, image: data)
    }

    /// Everything completed is already in SQLite; wait for in-flight commits.
    func flush() async {
        while committing || !commits.isEmpty { try? await Task.sleep(for: .milliseconds(10)) }
        thumbnailTask?.cancel()
        await writeThumbnail()
    }

    func close() {
        thumbnailTask?.cancel()
        Task { await writeThumbnail() }
        images.clear()
    }

    private func haptic() { UISelectionFeedbackGenerator().selectionChanged() }

    /// DEBUG-only phase trace for isolated UI acceptance (appears in the canvas' test value).
    private func trace(_ phase: String) {
        #if DEBUG
        canvas?.editorTrace = phase
        #endif
    }

    var zoomLabel: String { "\(Int((zoom * 100).rounded())) %" }
}
