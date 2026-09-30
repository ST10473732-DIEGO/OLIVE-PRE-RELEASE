import Foundation
import CoreGraphics

/// Touch/Pencil samples → canonical stroke points (port of the desktop
/// `capture.ts`). Pure logic, so every edge case is unit-tested: one drawing
/// touch at a time, cancellation, pressure only when the hardware really
/// reports it, bounded point counts, quantized document coordinates.
struct DrawStrokeCapture: Sendable {
    enum Tool: String, Sendable { case pen, erase }
    enum Source: Sendable, Equatable { case finger, pencil }
    struct Sample: Sendable { var x: Double; var y: Double; var pressure: Double }
    struct Captured: Sendable, Equatable {
        let tool: Tool
        /// Flat x, y (and pressure when `pressure`) values, already quantized.
        let points: [Double]
        let pressure: Bool
    }

    private struct Current: Sendable {
        var tool: Tool
        var source: Source
        var minDistance: Double
        var xs: [Double] = [], ys: [Double] = [], ps: [Double] = []
        var pressureSeen = false
        var tail: Sample?
    }
    private var current: Current?
    /// True once a stroke hit the per-stroke point limit (the UI says so).
    private(set) var limited = false

    var active: Bool { current != nil }
    var tool: Tool? { current?.tool }

    /// Real pressure is only trusted from Apple Pencil, and only once it varies.
    /// A finger never produces pressure: it draws at exactly the selected width.
    private static func pencilPressure(_ source: Source, _ value: Double) -> Bool { source == .pencil && value > 0 && value <= 1 }

    mutating func begin(_ start: Sample, tool: Tool, source: Source, minDistance: Double) -> Bool {
        guard current == nil else { return false }   // A second finger never starts a second stroke.
        limited = false
        current = Current(tool: tool, source: source, minDistance: max(0, minDistance))
        keep(start)
        return true
    }

    private mutating func keep(_ sample: Sample) {
        guard var c = current else { return }
        if c.xs.count >= DrawSpec.Limit.maxPoints { limited = true; return }
        let x = DrawQuantize.coordinate(sample.x), y = DrawQuantize.coordinate(sample.y)
        let p = Self.pencilPressure(c.source, sample.pressure) ? DrawQuantize.pressure(sample.pressure) : (c.ps.last ?? 0.5)
        if let first = c.ps.first, p != first { c.pressureSeen = true }
        c.xs.append(x); c.ys.append(y); c.ps.append(p); c.tail = nil
        current = c
    }

    /// Coalesced samples for the drawing touch. Returns true when points were kept.
    mutating func move(_ samples: [Sample]) -> Bool {
        guard current != nil else { return false }
        var changed = false
        for sample in samples where sample.x.isFinite && sample.y.isFinite {
            let c = current!
            if hypot(sample.x - c.xs.last!, sample.y - c.ys.last!) < c.minDistance {
                current!.tail = sample   // Kept for the final point if the touch stops here.
                continue
            }
            let before = c.xs.count
            keep(sample)
            changed = changed || current!.xs.count != before
        }
        return changed
    }

    /// Touch up: finish the stroke with what was drawn.
    mutating func end(_ last: Sample? = nil) -> Captured? {
        guard let c = current else { return nil }
        let final = last.flatMap { $0.x.isFinite && $0.y.isFinite ? $0 : nil } ?? c.tail
        if let final, DrawQuantize.coordinate(final.x) != c.xs.last || DrawQuantize.coordinate(final.y) != c.ys.last { keep(final) }
        let result = snapshot()
        current = nil
        return result
    }

    /// The system took the touch (a pinch began, a call arrived): discard the partial stroke.
    mutating func cancel() -> Bool {
        guard current != nil else { return false }
        current = nil
        return true
    }

    /// The in-progress stroke as it will be stored (for live rendering).
    func snapshot() -> Captured? {
        guard let c = current else { return nil }
        let pressure = c.tool == .pen && c.pressureSeen
        var points: [Double] = []
        points.reserveCapacity(c.xs.count * (pressure ? 3 : 2))
        for i in c.xs.indices {
            points.append(c.xs[i]); points.append(c.ys[i])
            if pressure { points.append(c.ps[i]) }
        }
        return Captured(tool: c.tool, points: points, pressure: pressure)
    }
}

/// Document ↔ view coordinates (port of the desktop `viewport.ts`, in points):
/// view = doc × zoom + offset. Only document coordinates are ever stored;
/// zoom, pan, rotation and screen scale never change document data.
struct DrawViewport: Equatable, Sendable {
    static let minZoom = 0.1
    static let maxZoom = 16.0
    var zoom: Double = 1
    var offset: CGPoint = .zero

    static func clampZoom(_ zoom: Double) -> Double { min(maxZoom, max(minZoom, zoom)) }

    func toDocument(_ p: CGPoint) -> CGPoint { CGPoint(x: (p.x - offset.x) / zoom, y: (p.y - offset.y) / zoom) }
    func toView(_ p: CGPoint) -> CGPoint { CGPoint(x: p.x * zoom + offset.x, y: p.y * zoom + offset.y) }

    /// Fit the whole page inside the viewport (never stretched), centred.
    static func fit(document: CGSize, viewport: CGSize, padding: Double = 16) -> DrawViewport {
        let zoom = clampZoom(min(max(1, viewport.width - padding * 2) / document.width, max(1, viewport.height - padding * 2) / document.height))
        return DrawViewport(zoom: zoom).centred(document: document, viewport: viewport)
    }

    func centred(document: CGSize, viewport: CGSize) -> DrawViewport {
        DrawViewport(zoom: zoom, offset: CGPoint(x: (viewport.width - document.width * zoom) / 2, y: (viewport.height - document.height * zoom) / 2))
    }

    /// Zoom so that the document point under `anchor` stays under it.
    func zoomed(to value: Double, around anchor: CGPoint) -> DrawViewport {
        let next = Self.clampZoom(value)
        let doc = toDocument(anchor)
        return DrawViewport(zoom: next, offset: CGPoint(x: anchor.x - doc.x * next, y: anchor.y - doc.y * next))
    }

    func panned(by delta: CGPoint) -> DrawViewport { DrawViewport(zoom: zoom, offset: CGPoint(x: offset.x + delta.x, y: offset.y + delta.y)) }

    /// Keep at least `margin` points of the page inside the viewport.
    func clamped(document: CGSize, viewport: CGSize, margin: Double = 48) -> DrawViewport {
        let w = document.width * zoom, h = document.height * zoom
        let m = min(margin, w / 2, h / 2)
        let x = min(max(offset.x, m - w), viewport.width - m)
        let y = min(max(offset.y, m - h), viewport.height - m)
        return DrawViewport(zoom: zoom, offset: CGPoint(x: x, y: y))
    }

    /// Keep the same logical centre when the viewport resizes (rotation).
    func resized(from old: CGSize, to new: CGSize) -> DrawViewport {
        let centre = toDocument(CGPoint(x: old.width / 2, y: old.height / 2))
        return DrawViewport(zoom: zoom, offset: CGPoint(x: new.width / 2 - centre.x * zoom, y: new.height / 2 - centre.y * zoom))
    }
}

/// Pen size in document pixels: whole pixels from 1, half a pixel at the bottom
/// (desktop drawModel.ts). The size slider is logarithmic.
enum DrawBrush {
    static func size(_ value: Double) -> Double {
        guard value.isFinite else { return 8 }
        let clamped = min(DrawSpec.Limit.maxWidth, max(DrawSpec.Limit.minWidth, value))
        return clamped < 1 ? 0.5 : clamped.rounded()
    }
    private static let logMin = log(DrawSpec.Limit.minWidth), logMax = log(DrawSpec.Limit.maxWidth)
    static func size(slider position: Double) -> Double {
        size(exp(logMin + (logMax - logMin) * min(1000, max(0, position)) / 1000))
    }
    static func slider(size value: Double) -> Double { ((log(size(value)) - logMin) / (logMax - logMin) * 1000).rounded() }
    /// A quick palette (same as desktop); any colour is available from the picker.
    static let swatches: [(name: String, hex: String)] = [
        ("Black", "#000000"), ("Dark grey", "#5f6368"), ("White", "#ffffff"), ("Red", "#e53935"), ("Orange", "#fb8c00"),
        ("Yellow", "#fdd835"), ("Green", "#43a047"), ("Blue", "#1e63e9"), ("Purple", "#8e24aa"),
    ]
    /// #rrggbb (lowercase) from sRGB components 0…1; exact values round-trip.
    static func hex(red: Double, green: Double, blue: Double) -> String {
        func c(_ v: Double) -> Int { Int((min(1, max(0, v)) * 255).rounded()) }
        return String(format: "#%02x%02x%02x", c(red), c(green), c(blue))
    }
}
