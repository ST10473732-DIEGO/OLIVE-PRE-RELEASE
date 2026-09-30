import SwiftUI
import UIKit

@MainActor
protocol DrawCanvasDelegate: AnyObject {
    /// One completed gesture: exactly one canonical operation.
    func canvasCommit(_ op: DrawOp)
    /// Zoom/pan changed (for the zoom label).
    func canvasViewportChanged(zoom: Double)
    /// A stroke hit the per-stroke point limit.
    func canvasLimited()
}

/// Owns one rendered raster and its bitmap context. Ownership moves from the
/// render task to the main actor exactly once and is never shared concurrently.
private final class RasterBox: @unchecked Sendable {
    let context: CGContext
    let image: CGImage
    init(context: CGContext, image: CGImage) { self.context = context; self.image = image }
}

/// The native drawing surface. Document coordinates are the only stored
/// coordinates; the view maps them with `DrawViewport` (zoom × doc + offset).
///
/// * One finger (or Apple Pencil) draws: one gesture → one operation, committed
///   on touch-up. Points are never streamed or persisted per touch.
/// * Two fingers pinch-zoom (10 %–1600 %, around the focal point) and pan;
///   navigation never draws (a pinch cancels a stroke that just started).
/// * The committed picture is a raster cache of the visible viewport, rendered
///   off the main thread from the operations; it is never authoritative.
final class DrawCanvasUIView: UIView, UIGestureRecognizerDelegate {
    enum Tool: Equatable { case pen, erase }
    weak var delegate: DrawCanvasDelegate?
    var tool: Tool = .pen
    var color = DrawColor(hex: "#000000")
    var brushWidth: Double = 8
    var brushOpacity: Double = 1
    /// Decoded images by asset id (main-thread cache owned by the editor).
    var imageSnapshot: () -> [String: CGImage] = { [:] }

    private(set) var documentSize = CGSize(width: 1920, height: 1080)
    private var background = "#ffffff"
    private var ops: [DrawOp] = []
    private var missing: Set<String> = []
    private(set) var viewport = DrawViewport()
    private var fitted = false
    private var lastBounds = CGSize.zero

    private let pageLayer = CALayer()
    private let inkLayer = CALayer()
    private let liveShape = CAShapeLayer()
    private let liveBitmap = CALayer()
    private let eraseMask = CAShapeLayer()
    private let liveClip = CALayer()
    private var placeholderLayers: [CALayer] = []

    private var cache: RasterBox?
    private var cacheViewport: DrawViewport?
    private var generation = 0
    private var renderTask: Task<Void, Never>?
    private var gestureRender: Task<Void, Never>?

    private var capture = DrawStrokeCapture()
    private var activeTouch: UITouch?
    private var pinchStart: (zoom: Double, viewport: DrawViewport)?
    private var panLast: CGPoint?
    private var pencilEraser = false

    override init(frame: CGRect) {
        super.init(frame: frame)
        isMultipleTouchEnabled = true
        backgroundColor = UIColor(OliveTheme.ground)
        clipsToBounds = true
        pageLayer.shadowColor = UIColor.black.cgColor
        pageLayer.shadowOpacity = 0.35
        pageLayer.shadowRadius = 8
        pageLayer.shadowOffset = .zero
        layer.addSublayer(pageLayer)
        for sub in [inkLayer, liveBitmap] {
            sub.anchorPoint = .zero
            sub.contentsGravity = .topLeft
            sub.contentsScale = UIScreen.main.scale
            sub.actions = ["contents": NSNull(), "transform": NSNull(), "position": NSNull(), "bounds": NSNull()]
            layer.addSublayer(sub)
        }
        liveShape.fillColor = nil
        liveShape.lineCap = .round
        liveShape.lineJoin = .round
        liveShape.actions = ["path": NSNull(), "lineWidth": NSNull(), "opacity": NSNull(), "strokeColor": NSNull()]
        layer.addSublayer(liveShape)
        liveClip.backgroundColor = UIColor.black.cgColor
        liveClip.actions = ["position": NSNull(), "bounds": NSNull()]
        liveShape.mask = liveClip
        eraseMask.fillRule = .evenOdd
        eraseMask.actions = ["path": NSNull()]
        pageLayer.actions = ["bounds": NSNull(), "position": NSNull(), "backgroundColor": NSNull()]

        let pinch = UIPinchGestureRecognizer(target: self, action: #selector(pinched(_:)))
        let pan = UIPanGestureRecognizer(target: self, action: #selector(panned(_:)))
        pan.minimumNumberOfTouches = 2
        pan.maximumNumberOfTouches = 2
        pinch.delegate = self; pan.delegate = self
        addGestureRecognizer(pinch); addGestureRecognizer(pan)
        let pencil = UIPencilInteraction()
        pencil.delegate = PencilBridge.shared
        PencilBridge.shared.onTap = { [weak self] in self?.pencilEraser.toggle() }
        addInteraction(pencil)

        isAccessibilityElement = true
        accessibilityIdentifier = "draw.canvas"
        accessibilityLabel = "Drawing canvas"
        accessibilityTraits = [.allowsDirectInteraction]
        accessibilityHint = "Draw with one finger. Pinch with two fingers to zoom, drag with two fingers to move."
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    /// The navigation stack's swipe-back gestures (iOS 26 recognizes one from
    /// anywhere on the screen) would claim a left-to-right stroke and cancel it.
    /// While the canvas is on screen they are off; the Back button still works.
    private weak var navigation: UINavigationController?
    override func didMoveToWindow() {
        super.didMoveToWindow()
        if window == nil { setPopGestures(enabled: true); return }
        var responder: UIResponder? = self
        while let current = responder, !(current is UINavigationController) { responder = current.next }
        navigation = responder as? UINavigationController
        setPopGestures(enabled: false)
    }
    private func setPopGestures(enabled: Bool) {
        guard let navigation else { return }
        navigation.interactivePopGestureRecognizer?.isEnabled = enabled
        if #available(iOS 26, *) { navigation.interactiveContentPopGestureRecognizer?.isEnabled = enabled }
    }

    func gestureRecognizer(_ g: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer) -> Bool { true }

    // MARK: Document

    /// Replace the whole picture (open, Undo/Redo, remote records inserted earlier in the order).
    func load(size: CGSize, background: String, ops: [DrawOp], missing: Set<String>) {
        let resized = size != documentSize
        documentSize = size; self.background = background; self.ops = ops; self.missing = missing
        if resized { fitted = false; setNeedsLayout() }
        updatePage()
        render()
        updateAccessibility()
    }

    /// A single new visible operation after every other one: draw it incrementally.
    func append(_ op: DrawOp, background: String, missing: Set<String>) {
        ops.append(op); self.background = background; self.missing = missing
        updatePage()
        if let cache, renderTask == nil, cacheViewport == viewport, op.assetID == nil {
            let target = DrawRender.Target(context: cache.context, k: viewport.zoom * contentScale, ox: viewport.offset.x * contentScale,
                                           oy: viewport.offset.y * contentScale, width: cache.context.width, height: cache.context.height)
            DrawRender.draw(target, op, images: nil)
            if let image = cache.context.makeImage() {
                self.cache = RasterBox(context: cache.context, image: image)
                inkLayer.contents = image
            }
            clearLive()
        } else {
            render()
        }
        updateAccessibility()
    }

    private var contentScale: Double { Double(window?.screen.scale ?? UIScreen.main.scale) }

    func fit() {
        guard bounds.width > 0, bounds.height > 0 else { return }
        viewport = DrawViewport.fit(document: documentSize, viewport: bounds.size)
        fitted = true
        viewportChanged(final: true)
    }

    func setZoom(_ zoom: Double) {
        viewport = viewport.zoomed(to: zoom, around: CGPoint(x: bounds.midX, y: bounds.midY)).clamped(document: documentSize, viewport: bounds.size)
        viewportChanged(final: true)
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        guard bounds.width > 0, bounds.height > 0 else { return }
        if !fitted { fit(); lastBounds = bounds.size; return }
        if bounds.size != lastBounds {
            // Rotation/resize: the viewport moves, the document never does.
            viewport = viewport.resized(from: lastBounds, to: bounds.size).clamped(document: documentSize, viewport: bounds.size)
            lastBounds = bounds.size
            viewportChanged(final: true)
        }
    }

    private func viewportChanged(final: Bool) {
        updatePage()
        if let cacheViewport {
            // Show the cached raster transformed until a fresh one is ready.
            let s = viewport.zoom / cacheViewport.zoom
            let t = CGAffineTransform(a: s, b: 0, c: 0, d: s, tx: viewport.offset.x - cacheViewport.offset.x * s,
                                      ty: viewport.offset.y - cacheViewport.offset.y * s)
            inkLayer.setAffineTransform(t)
        }
        delegate?.canvasViewportChanged(zoom: viewport.zoom)
        if final { render() } else { scheduleGestureRender() }
        updateAccessibility()
    }

    private func scheduleGestureRender() {
        guard gestureRender == nil else { return }
        gestureRender = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(140))
            guard let self else { return }
            self.gestureRender = nil
            self.render()
        }
    }

    private func updatePage() {
        let rect = CGRect(x: viewport.offset.x, y: viewport.offset.y, width: documentSize.width * viewport.zoom, height: documentSize.height * viewport.zoom)
        pageLayer.frame = rect
        pageLayer.backgroundColor = background == "transparent" ? Self.checkerboard.cgColor : UIColor.white.cgColor
        pageLayer.shadowPath = UIBezierPath(rect: pageLayer.bounds).cgPath
        liveClip.frame = rect
        updatePlaceholders()
    }

    /// Transparent pages show an editor-only checkerboard (never exported).
    private static let checkerboard: UIColor = {
        let size = 16.0
        let image = UIGraphicsImageRenderer(size: CGSize(width: size, height: size)).image { context in
            UIColor(white: 0.93, alpha: 1).setFill(); context.fill(CGRect(x: 0, y: 0, width: size, height: size))
            UIColor(white: 0.80, alpha: 1).setFill()
            context.fill(CGRect(x: 0, y: 0, width: size / 2, height: size / 2))
            context.fill(CGRect(x: size / 2, y: size / 2, width: size / 2, height: size / 2))
        }
        return UIColor(patternImage: image)
    }()

    private func updatePlaceholders() {
        placeholderLayers.forEach { $0.removeFromSuperlayer() }
        placeholderLayers = []
        for op in ops {
            guard case .image(_, let asset, let x, let y, let w, let h, _) = op, missing.contains(asset) else { continue }
            let origin = viewport.toView(CGPoint(x: x, y: y))
            let frame = CGRect(x: origin.x, y: origin.y, width: w * viewport.zoom, height: h * viewport.zoom)
            let box = CALayer()
            box.frame = frame
            box.borderColor = UIColor(OliveTheme.information).cgColor
            box.borderWidth = 1.5
            box.backgroundColor = UIColor(OliveTheme.information).withAlphaComponent(0.12).cgColor
            let label = CATextLayer()
            label.string = "Image arriving…"
            label.fontSize = 13
            label.foregroundColor = UIColor(OliveTheme.information).cgColor
            label.alignmentMode = .center
            label.contentsScale = contentScale
            label.frame = CGRect(x: 0, y: max(0, frame.height / 2 - 9), width: frame.width, height: 18)
            box.addSublayer(label)
            layer.insertSublayer(box, above: inkLayer)
            placeholderLayers.append(box)
        }
    }

    // MARK: Rendering (off the main thread)

    func render() {
        guard bounds.width > 0, bounds.height > 0 else { return }
        generation += 1
        let token = generation
        let scale = contentScale
        let width = Int((bounds.width * scale).rounded(.up)), height = Int((bounds.height * scale).rounded(.up))
        let view = viewport, ops = self.ops, images = imageSnapshot(), size = documentSize
        let from = ops.replayStart
        renderTask?.cancel()
        renderTask = Task { [weak self] in
            let box: RasterBox? = await Task.detached(priority: .userInitiated) {
                guard let context = DrawRender.makeContext(width: width, height: height) else { return nil }
                let target = DrawRender.Target(context: context, k: view.zoom * scale, ox: view.offset.x * scale, oy: view.offset.y * scale,
                                               width: width, height: height)
                // Clip to the page (kept for incremental draws): ink outside the
                // document is never shown, exactly as it is never exported.
                context.clip(to: CGRect(x: view.offset.x * scale, y: view.offset.y * scale,
                                        width: size.width * view.zoom * scale, height: size.height * view.zoom * scale))
                DrawRender.replay(target, ops, from: from, to: ops.count, images: { images[$0] })
                guard let image = context.makeImage() else { return nil }
                return RasterBox(context: context, image: image)
            }.value
            guard let self, token == self.generation, let box else { return }
            self.cache = box
            self.cacheViewport = view
            // Reset the transform BEFORE sizing: a frame set under a transform is misplaced.
            self.inkLayer.setAffineTransform(.identity)
            self.inkLayer.bounds = CGRect(x: 0, y: 0, width: Double(width) / scale, height: Double(height) / scale)
            self.inkLayer.position = .zero
            self.inkLayer.contents = box.image
            if view != self.viewport { self.viewportChanged(final: false) }
            self.renderTask = nil
            if !self.capture.active { self.clearLive() }
        }
    }

    // MARK: Touch drawing

    #if DEBUG
    private var lastTrace = ""
    /// The editor's current phase (pull/commit), shown with the touch trace.
    var editorTrace = "" { didSet { if ProcessInfo.processInfo.arguments.contains("--ui-test-draw-fixture") { updateAccessibility() } } }
    private func trace(_ phase: String) {
        guard ProcessInfo.processInfo.arguments.contains("--ui-test-draw-fixture") else { return }
        lastTrace = phase
        updateAccessibility()
    }
    #else
    private func trace(_ phase: String) {}
    #endif

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        trace("began touches=\(touches.count) all=\(event?.allTouches?.count ?? -1) active=\(activeTouch != nil)")
        guard activeTouch == nil, let touch = touches.first, (event?.allTouches?.count ?? 1) == 1 else {
            cancelStroke(); return
        }
        let source: DrawStrokeCapture.Source = touch.type == .pencil ? .pencil : .finger
        let tool: DrawStrokeCapture.Tool = pencilEraser && source == .pencil ? .erase : (self.tool == .erase ? .erase : .pen)
        let doc = viewport.toDocument(touch.location(in: self))
        let sample = DrawStrokeCapture.Sample(x: doc.x, y: doc.y, pressure: pressure(touch))
        guard capture.begin(sample, tool: tool, source: source, minDistance: 0.35 / viewport.zoom) else { return }
        activeTouch = touch
        drawLive()
    }

    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard let touch = activeTouch, touches.contains(touch) else { return }
        let samples = (event?.coalescedTouches(for: touch) ?? [touch]).map { t -> DrawStrokeCapture.Sample in
            let doc = viewport.toDocument(t.location(in: self))
            return DrawStrokeCapture.Sample(x: doc.x, y: doc.y, pressure: pressure(t))
        }
        if capture.move(samples) { drawLive() }
        if capture.limited { delegate?.canvasLimited() }
    }

    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
        trace("ended active=\(activeTouch != nil)")
        guard let touch = activeTouch, touches.contains(touch) else { return }
        let doc = viewport.toDocument(touch.location(in: self))
        let captured = capture.end(DrawStrokeCapture.Sample(x: doc.x, y: doc.y, pressure: pressure(touch)))
        activeTouch = nil
        guard let captured else { clearLive(); return }
        let id = DrawText.randomID()
        let op: DrawOp = captured.tool == .erase
            ? .erase(id: id, width: brushWidth, points: captured.points)
            : .stroke(id: id, color: color, width: brushWidth, opacity: brushOpacity, pressure: captured.pressure, points: captured.points)
        delegate?.canvasCommit(op)   // The live layer stays until the committed op is drawn.
    }

    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
        trace("cancelled active=\(activeTouch != nil)")
        guard let touch = activeTouch, touches.contains(touch) else { return }
        cancelStroke()
    }

    private func cancelStroke() {
        if capture.cancel() { activeTouch = nil; clearLive() }
    }

    /// Apple Pencil force when the hardware reports it; fingers report none.
    private func pressure(_ touch: UITouch) -> Double {
        guard touch.type == .pencil, touch.maximumPossibleForce > 0 else { return 0 }
        return Double(touch.force / touch.maximumPossibleForce)
    }

    private func drawLive() {
        guard let snapshot = capture.snapshot() else { return }
        let stride = snapshot.pressure ? 3 : 2
        if snapshot.tool == .erase {
            // Live eraser: mask the ink layer with "everything except the eraser path".
            let path = DrawRender.path(snapshot.points, stride: 2)
                .copy(strokingWithWidth: brushWidth, lineCap: .round, lineJoin: .round, miterLimit: 10)
            let full = CGMutablePath()
            full.addRect(CGRect(x: -1e5, y: -1e5, width: 2e5, height: 2e5))
            full.addPath(path)
            // The mask lives in the ink layer's own (cached-raster) coordinate space.
            let base = cacheViewport ?? viewport
            var toLayer = CGAffineTransform(a: base.zoom, b: 0, c: 0, d: base.zoom, tx: base.offset.x, ty: base.offset.y)
            eraseMask.path = full.copy(using: &toLayer)
            eraseMask.frame = inkLayer.bounds
            inkLayer.mask = eraseMask
            return
        }
        if snapshot.pressure {
            // Pencil pressure: rendered by the same code as the committed stroke.
            let scale = contentScale
            let width = Int((bounds.width * scale).rounded(.up)), height = Int((bounds.height * scale).rounded(.up))
            guard let context = DrawRender.makeContext(width: width, height: height) else { return }
            let target = DrawRender.Target(context: context, k: viewport.zoom * scale, ox: viewport.offset.x * scale, oy: viewport.offset.y * scale,
                                           width: width, height: height)
            DrawRender.drawStroke(target, color: color, width: brushWidth, opacity: brushOpacity, pressure: true, points: snapshot.points)
            liveBitmap.bounds = CGRect(x: 0, y: 0, width: Double(width) / scale, height: Double(height) / scale)
            liveBitmap.position = .zero
            liveBitmap.contents = context.makeImage()
            liveShape.path = nil
            return
        }
        var transform = CGAffineTransform(a: viewport.zoom, b: 0, c: 0, d: viewport.zoom, tx: viewport.offset.x, ty: viewport.offset.y)
        liveShape.path = DrawRender.path(snapshot.points, stride: stride).copy(using: &transform)
        liveShape.lineWidth = brushWidth * viewport.zoom
        liveShape.strokeColor = UIColor(red: color.red, green: color.green, blue: color.blue, alpha: 1).cgColor
        liveShape.opacity = Float(brushOpacity)   // Group opacity: overlaps never darken (as committed).
        liveShape.frame = bounds
    }

    private func clearLive() {
        liveShape.path = nil
        liveBitmap.contents = nil
        inkLayer.mask = nil
    }

    /// The committed operation was refused: drop the live preview.
    func discardLive() { clearLive() }

    // MARK: Navigation gestures

    @objc private func pinched(_ gesture: UIPinchGestureRecognizer) {
        switch gesture.state {
        case .began:
            cancelStroke()
            pinchStart = (viewport.zoom, viewport)
        case .changed:
            guard let start = pinchStart else { return }
            let anchor = gesture.location(in: self)
            viewport = viewport.zoomed(to: start.zoom * Double(gesture.scale), around: anchor)
            viewportChanged(final: false)
        default:
            pinchStart = nil
            viewport = viewport.clamped(document: documentSize, viewport: bounds.size)
            fitted = true
            viewportChanged(final: true)
        }
    }

    @objc private func panned(_ gesture: UIPanGestureRecognizer) {
        switch gesture.state {
        case .began:
            cancelStroke()
            panLast = gesture.translation(in: self)
        case .changed:
            let now = gesture.translation(in: self)
            let last = panLast ?? now
            viewport = viewport.panned(by: CGPoint(x: now.x - last.x, y: now.y - last.y))
            panLast = now
            viewportChanged(final: false)
        default:
            panLast = nil
            viewport = viewport.clamped(document: documentSize, viewport: bounds.size)
            viewportChanged(final: true)
        }
    }

    private func updateAccessibility() {
        accessibilityValue = "\(ops.count) visible edit\(ops.count == 1 ? "" : "s"), zoom \(Int((viewport.zoom * 100).rounded())) percent"
        #if DEBUG
        if !lastTrace.isEmpty || !editorTrace.isEmpty { accessibilityValue! += " | " + lastTrace + " | " + editorTrace }
        #endif
    }
}

/// Apple Pencil double-tap (where the hardware supports it) toggles the eraser.
@MainActor
private final class PencilBridge: NSObject, UIPencilInteractionDelegate {
    static let shared = PencilBridge()
    var onTap: (() -> Void)?
    func pencilInteractionDidTap(_ interaction: UIPencilInteraction) {
        if UIPencilInteraction.preferredTapAction == .switchEraser { onTap?() }
    }
}

/// SwiftUI host for the canvas.
struct DrawCanvasRepresentable: UIViewRepresentable {
    let editor: DrawEditorModel
    func makeUIView(context: Context) -> DrawCanvasUIView {
        let view = DrawCanvasUIView(frame: .zero)
        editor.attach(canvas: view)
        return view
    }
    func updateUIView(_ view: DrawCanvasUIView, context: Context) {
        view.tool = editor.tool == .erase ? .erase : .pen
        view.color = DrawColor(hex: editor.color)
        view.brushWidth = editor.width
        view.brushOpacity = editor.opacity
    }
}
