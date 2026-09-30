import Foundation
import Observation
import UIKit

/// OLIVE Draw on the phone: the drawing library, local-first. Every action is
/// committed to the on-device store before it returns; sync is secondary.
@MainActor @Observable
final class DrawModel {
    private(set) var drawings: [DrawSummary] = []
    private(set) var trash: [DrawSummary] = []
    private(set) var available = true
    private(set) var unavailableReason = ""
    private(set) var started = false
    var notice: String?
    /// Thumbnail images by drawing id (a local cache; never synced).
    private(set) var thumbnails: [String: UIImage] = [:]
    let sync: DrawSync
    @ObservationIgnored private(set) var engine: DrawEngine?
    @ObservationIgnored weak var editor: DrawEditorModel?
    @ObservationIgnored private let directory: URL
    /// Per-profile preferences (the brush, the phone's Draw sync switch); isolated in UI tests.
    @ObservationIgnored let defaults: UserDefaults
    @ObservationIgnored private var thumbnailRevisions: [String: Int] = [:]
    @ObservationIgnored private var thumbnailQueue: [String] = []
    @ObservationIgnored private var thumbnailWorker: Task<Void, Never>?
    @ObservationIgnored private var refreshTask: Task<Void, Never>?

    init(directory: URL, defaults: UserDefaults = .standard) {
        self.directory = directory.appendingPathComponent("Draw", isDirectory: true)
        self.defaults = defaults
        sync = DrawSync(defaults: defaults)
    }

    /// Starts once; a later Connect identity only changes the device id of new records.
    func start(deviceID: String) {
        if let engine { Task { await engine.setDevice(deviceID) }; return }
        let engine = DrawEngine(directory: directory, deviceID: deviceID)
        self.engine = engine
        started = true
        Task { [weak self] in
            guard await engine.available else {
                self?.available = false
                self?.unavailableReason = DrawError(engine.unavailable?.code ?? "draw_unavailable").errorDescription ?? ""
                return
            }
            await engine.setListener { [weak self] event in Task { @MainActor in self?.handle(event) } }
            self?.sync.attach(engine: engine)
            await self?.refresh()
        }
    }

    func refresh() async {
        guard let engine, available else { return }
        do {
            drawings = try await engine.list(trash: false)
            trash = try await engine.list(trash: true)
        } catch {
            notice = (error as? DrawError)?.errorDescription ?? "Drawing storage unavailable."
        }
    }

    private func scheduleRefresh() {
        refreshTask?.cancel()
        refreshTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(120))
            guard !Task.isCancelled else { return }
            await self?.refresh()
        }
    }

    private func handle(_ event: DrawEvent) {
        switch event.kind {
        case .records, .changed, .purged:
            scheduleRefresh()
            if let did = event.drawingID, let editor, editor.drawingID == did {
                if event.kind == .purged { editor.purgedElsewhere() } else if event.peer != nil || event.kind == .changed { editor.remoteChanged() }
            }
            if event.peer == nil { sync.kick() } else { sync.refreshState() }
        case .asset:
            if let asset = event.assetID { editor?.assetArrived(asset) }
            sync.refreshState()
            scheduleRefresh()
        }
    }

    // MARK: Actions

    private func perform<T>(_ body: (DrawEngine) async throws -> T) async -> T? {
        guard let engine else { notice = unavailableReason; return nil }
        do { return try await body(engine) }
        catch let error as DrawError { notice = error.errorDescription; return nil }
        catch { notice = "Could not save drawing."; return nil }
    }

    func create(_ preset: DrawCanvas.Preset, title: String = "") async -> DrawSummary? {
        let made = await perform { try await $0.create(title: title, width: preset.width, height: preset.height, background: preset.background) }
        await refresh()
        return made
    }
    func rename(_ id: String, _ title: String) async { _ = await perform { try await $0.rename(id, title: title) }; await refresh() }
    func moveToTrash(_ id: String) async { _ = await perform { try await $0.trash(id) }; await refresh() }
    func restore(_ id: String) async { _ = await perform { try await $0.restore(id) }; await refresh() }
    func duplicate(_ id: String) async -> DrawSummary? {
        let copy = await perform { try await $0.duplicate(id) }
        await refresh()
        return copy
    }
    func purge(_ id: String) async { _ = await perform { try await $0.purge(id) }; thumbnails[id] = nil; await refresh() }
    func summary(_ id: String) -> DrawSummary? { (drawings + trash).first { $0.id == id } }

    /// Local persistence first (every completed edit is already committed);
    /// called when the app backgrounds.
    func flush() async { await editor?.flush() }

    // MARK: Thumbnails (local cache, rendered on the phone, never synced)

    func thumbnail(for summary: DrawSummary) -> UIImage? {
        if thumbnailRevisions[summary.id] != summary.revision { requestThumbnail(summary) }
        return thumbnails[summary.id]
    }

    private func requestThumbnail(_ summary: DrawSummary) {
        thumbnailRevisions[summary.id] = summary.revision
        guard !thumbnailQueue.contains(summary.id) else { return }
        thumbnailQueue.append(summary.id)
        guard thumbnailWorker == nil else { return }
        thumbnailWorker = Task { [weak self] in
            while let self, let id = self.thumbnailQueue.first {
                self.thumbnailQueue.removeFirst()
                await self.loadThumbnail(id)
            }
            self?.thumbnailWorker = nil
        }
    }

    private func loadThumbnail(_ id: String) async {
        guard let engine, let summary = summary(id) else { return }
        if let stored = try? await engine.thumbnail(id), stored.revision >= summary.revision, let image = UIImage(data: stored.image) {
            thumbnails[id] = image
            return
        }
        guard summary.status == "ok", let ops = try? await engine.visibleOperations(id) else { return }
        var images: [String: CGImage] = [:]
        for asset in Set(ops.compactMap(\.assetID)) {
            if let data = try? await engine.assetData(asset) {
                images[asset] = await Task.detached { DrawAssets.decode(data) }.value
            }
        }
        let rendered = await Task.detached(priority: .utility) {
            DrawModel.thumbnailData(ops: ops, width: summary.width, height: summary.height, background: summary.background, images: images)
        }.value
        guard let (mime, data) = rendered else { return }
        try? await engine.putThumbnail(id, revision: summary.revision, mime: mime, image: data)
        thumbnails[id] = UIImage(data: data)
    }

    /// A bounded preview (≤ 320 px, ≤ 96 KB) with the background composited.
    nonisolated static func thumbnailData(ops: [DrawOp], width: Int, height: Int, background: String, images: [String: CGImage]) -> (String, Data)? {
        let scale = min(1, Double(DrawSpec.Limit.thumbnailMaxSide) / Double(max(width, height)))
        let ground = ops.effectiveBackground(background)
        guard let image = DrawRender.rasterize(ops, width: width, height: height, background: ground, jpeg: false, scale: scale,
                                               images: { images[$0] }) else { return nil }
        if let png = DrawRender.encode(image, jpeg: false), png.count <= DrawSpec.Limit.thumbnailMaxBytes { return ("image/png", png) }
        guard let flat = DrawRender.rasterize(ops, width: width, height: height, background: ground, jpeg: true, scale: scale,
                                              images: { images[$0] }),
              let jpeg = DrawRender.encode(flat, jpeg: true, quality: 0.8), jpeg.count <= DrawSpec.Limit.thumbnailMaxBytes else { return nil }
        return ("image/jpeg", jpeg)
    }
}

/// Decoded images for the open drawing. Missing assets (still arriving from
/// another device) are retried when they are stored; they never render
/// partially. Decoded copies are dropped when the editor closes or memory is low.
@MainActor
final class DrawImageCache {
    private var images: [String: CGImage] = [:]
    private var loading = Set<String>()
    private(set) var missing = Set<String>()
    var onChange: (() -> Void)?
    private let engine: DrawEngine
    private var memoryObserver: NSObjectProtocol?

    init(engine: DrawEngine) {
        self.engine = engine
        memoryObserver = NotificationCenter.default.addObserver(forName: UIApplication.didReceiveMemoryWarningNotification, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.images.removeAll(); self?.onChange?() }
        }
    }

    func snapshot() -> [String: CGImage] { images }

    /// Start loading every referenced asset that is not decoded yet.
    func require(_ ids: Set<String>) {
        for id in ids where images[id] == nil && !loading.contains(id) {
            loading.insert(id)
            Task {
                let data = try? await engine.assetData(id)
                let image: CGImage? = if let data { await Task.detached(priority: .userInitiated) { DrawAssets.decode(data) }.value } else { nil }
                loading.remove(id)
                if let image { images[id] = image; missing.remove(id) } else { missing.insert(id) }
                onChange?()
            }
        }
        for id in images.keys where !ids.contains(id) { images[id] = nil }   // Only the open drawing's images stay decoded.
    }

    func arrived(_ id: String) {
        guard missing.contains(id) || images[id] == nil else { return }
        missing.remove(id)
        images[id] = nil
        require(Set(images.keys).union([id]))
    }

    func clear() { images.removeAll(); missing.removeAll(); loading.removeAll() }
}
