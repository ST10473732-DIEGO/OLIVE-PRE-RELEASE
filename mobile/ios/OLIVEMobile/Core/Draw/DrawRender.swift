import Foundation
import CoreGraphics

/// CoreGraphics renderer for OLIVE Draw operations: a port of the desktop
/// `render.ts`. The record set is the source of truth; pixels are a cache.
/// Every function takes an explicit document → device mapping
/// (device = doc × k + (ox, oy), top-left origin), so the same code renders the
/// on-screen cache, the live stroke, thumbnails and full-resolution exports.
///
/// Smoothing (identical to the desktop): a stroke passes through its first and
/// last points and follows quadratic curves through the midpoints of the points
/// between. It depends only on the stored points, never on frame rate or zoom.
enum DrawRender {
    /// Decoded imported images by asset id (nil while one is still arriving).
    typealias Images = (String) -> CGImage?

    struct Target {
        let context: CGContext
        let k: Double
        let ox: Double
        let oy: Double
        let width: Int
        let height: Int
        var docTransform: CGAffineTransform { CGAffineTransform(a: k, b: 0, c: 0, d: k, tx: ox, ty: oy) }
    }

    static let sRGB = CGColorSpace(name: CGColorSpace.sRGB)!

    /// A transparent RGBA bitmap with a top-left origin (like a canvas).
    static func makeContext(width: Int, height: Int, opaque: Bool = false) -> CGContext? {
        guard width > 0, height > 0, let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
                space: sRGB, bitmapInfo: (opaque ? CGImageAlphaInfo.noneSkipLast : CGImageAlphaInfo.premultipliedLast).rawValue) else { return nil }
        context.translateBy(x: 0, y: CGFloat(height))
        context.scaleBy(x: 1, y: -1)
        context.interpolationQuality = .high
        context.setShouldAntialias(true)
        return context
    }

    /// Trace a smoothed polyline (points in document px) as a path.
    static func path(_ points: [Double], stride: Int) -> CGPath {
        let path = CGMutablePath()
        let n = points.count / stride
        guard n > 0 else { return path }
        path.move(to: CGPoint(x: points[0], y: points[1]))
        if n == 1 {
            path.addLine(to: CGPoint(x: points[0] + 0.001, y: points[1]))   // Zero-length path: the round cap draws a dot.
            return path
        }
        if n > 2 {
            var current = CGPoint(x: points[0], y: points[1])
            for i in 1..<(n - 1) {
                let x = points[i * stride], y = points[i * stride + 1]
                let nx = points[(i + 1) * stride], ny = points[(i + 1) * stride + 1]
                let end = CGPoint(x: (x + nx) / 2, y: (y + ny) / 2)
                addQuad(path, from: current, control: CGPoint(x: x, y: y), to: end)
                current = end
            }
        }
        path.addLine(to: CGPoint(x: points[(n - 1) * stride], y: points[(n - 1) * stride + 1]))
        return path
    }

    /// A quadratic segment as short lines (round joins): CoreGraphics offsets a
    /// very tight quad curve with a squared outer corner, while the desktop's
    /// canvas draws it round; flattening makes both match. The curve itself is
    /// unchanged (sagitta well below a pixel at these steps).
    static func addQuad(_ path: CGMutablePath, from start: CGPoint, control: CGPoint, to end: CGPoint) {
        let length = hypot(control.x - start.x, control.y - start.y) + hypot(end.x - control.x, end.y - control.y)
        let steps = max(2, min(64, Int((length / 1.5).rounded(.up))))
        for step in 1...steps {
            let t = Double(step) / Double(steps), u = 1 - t
            path.addLine(to: CGPoint(x: u * u * start.x + 2 * u * t * control.x + t * t * end.x,
                                     y: u * u * start.y + 2 * u * t * control.y + t * t * end.y))
        }
    }

    /// Device-pixel bounds of a stroke inside the target (nil when fully outside).
    static func strokeBounds(_ target: Target, _ points: [Double], stride: Int, width: Double) -> CGRect? {
        var minX = Double.infinity, minY = Double.infinity, maxX = -Double.infinity, maxY = -Double.infinity
        var i = 0
        while i + 1 < points.count {
            minX = min(minX, points[i]); maxX = max(maxX, points[i])
            minY = min(minY, points[i + 1]); maxY = max(maxY, points[i + 1])
            i += stride
        }
        let pad = width / 2 + 2 / target.k
        let x0 = max(0, ((minX - pad) * target.k + target.ox).rounded(.down))
        let y0 = max(0, ((minY - pad) * target.k + target.oy).rounded(.down))
        let x1 = min(Double(target.width), ((maxX + pad) * target.k + target.ox).rounded(.up))
        let y1 = min(Double(target.height), ((maxY + pad) * target.k + target.oy).rounded(.up))
        guard x1 > x0, y1 > y0 else { return nil }
        return CGRect(x: x0, y: y0, width: x1 - x0, height: y1 - y0)
    }

    private static func ink(_ context: CGContext, color: DrawColor, width: Double, pressure: Bool, points: [Double]) {
        let cg = CGColor(colorSpace: sRGB, components: [color.red, color.green, color.blue, 1])!
        context.setStrokeColor(cg)
        context.setFillColor(cg)
        context.setLineCap(.round)
        context.setLineJoin(.round)
        if !pressure {
            context.setLineWidth(width)
            context.addPath(path(points, stride: 2))
            context.strokePath()
            return
        }
        // Pressure: each smoothed piece gets the width of the point that shapes it.
        let p = points, n = p.count / 3
        if n == 1 {
            let r = width * drawPressureWidth(p[2]) / 2
            context.fillEllipse(in: CGRect(x: p[0] - r, y: p[1] - r, width: 2 * r, height: 2 * r))
            return
        }
        var sx = p[0], sy = p[1]
        for i in 1..<n {
            let x = p[i * 3], y = p[i * 3 + 1]
            context.beginPath()
            context.move(to: CGPoint(x: sx, y: sy))
            context.setLineWidth(width * drawPressureWidth(p[i * 3 + 2]))
            if i < n - 1 {
                let mx = (x + p[(i + 1) * 3]) / 2, my = (y + p[(i + 1) * 3 + 1]) / 2
                let piece = CGMutablePath()
                piece.move(to: CGPoint(x: sx, y: sy))
                addQuad(piece, from: CGPoint(x: sx, y: sy), control: CGPoint(x: x, y: y), to: CGPoint(x: mx, y: my))
                context.addPath(piece)
                sx = mx; sy = my
            } else {
                context.addLine(to: CGPoint(x: x, y: y))
            }
            context.strokePath()
        }
    }

    static func drawStroke(_ target: Target, color: DrawColor, width: Double, opacity: Double, pressure: Bool, points: [Double]) {
        let context = target.context
        if opacity >= 1 {
            context.saveGState()
            context.concatenate(target.docTransform)
            ink(context, color: color, width: width, pressure: pressure, points: points)
            context.restoreGState()
            return
        }
        // Translucent strokes are drawn opaque in a transparency layer and
        // composited once, so overlapping segments and caps never darken.
        guard let box = strokeBounds(target, points, stride: pressure ? 3 : 2, width: width) else { return }
        context.saveGState()
        context.setAlpha(opacity)
        context.beginTransparencyLayer(in: box, auxiliaryInfo: nil)
        context.concatenate(target.docTransform)
        ink(context, color: color, width: width, pressure: pressure, points: points)
        context.endTransparencyLayer()
        context.restoreGState()
    }

    /// The eraser removes ink from the drawing layer, revealing the background.
    static func drawErase(_ target: Target, width: Double, points: [Double]) {
        let context = target.context
        context.saveGState()
        context.concatenate(target.docTransform)
        context.setBlendMode(.destinationOut)
        context.setStrokeColor(CGColor(colorSpace: sRGB, components: [0, 0, 0, 1])!)
        context.setLineCap(.round)
        context.setLineJoin(.round)
        context.setLineWidth(width)
        context.addPath(path(points, stride: 2))
        context.strokePath()
        context.restoreGState()
    }

    static func clearTarget(_ target: Target) {
        target.context.clear(CGRect(x: 0, y: 0, width: target.width, height: target.height))
    }

    /// An imported image sits on the drawing layer at its document rectangle, in
    /// operation order. A missing asset draws nothing here (the view shows a
    /// placeholder; export refuses until it arrives).
    static func drawImage(_ target: Target, assetID: String, x: Double, y: Double, width: Double, height: Double, opacity: Double, images: Images?) {
        guard let image = images?(assetID) else { return }
        let context = target.context
        context.saveGState()
        context.concatenate(target.docTransform)
        context.setAlpha(opacity)
        context.interpolationQuality = .high
        // Canvas drawImage is top-left; CGContext.draw is bottom-left: flip locally.
        context.translateBy(x: x, y: y + height)
        context.scaleBy(x: 1, y: -1)
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        context.restoreGState()
    }

    static func draw(_ target: Target, _ op: DrawOp, images: Images?) {
        switch op {
        case .stroke(_, let color, let width, let opacity, let pressure, let points):
            drawStroke(target, color: color, width: width, opacity: opacity, pressure: pressure, points: points)
        case .erase(_, let width, let points): drawErase(target, width: width, points: points)
        case .clear: clearTarget(target)
        case .image(_, let asset, let x, let y, let width, let height, let opacity):
            drawImage(target, assetID: asset, x: x, y: y, width: width, height: height, opacity: opacity, images: images)
        case .background: break   // Applied by the compositor, not the drawing layer.
        }
    }

    /// Replay ops[from..<to] onto a drawing layer (transparent where nothing was drawn).
    static func replay(_ target: Target, _ ops: [DrawOp], from: Int, to: Int, images: Images?) {
        guard from < to else { return }
        for index in from..<to { draw(target, ops[index], images: images) }
    }

    /// Paint the page background beneath an already-rendered drawing layer.
    static func underlay(_ context: CGContext, background: String, width: Int, height: Int) {
        guard background != "transparent" else { return }
        context.saveGState()
        context.setBlendMode(.destinationOver)
        context.setFillColor(CGColor(colorSpace: sRGB, components: [1, 1, 1, 1])!)   // Only "#ffffff" is a valid background.
        context.fill(CGRect(x: 0, y: 0, width: width, height: height))
        context.restoreGState()
    }

    /// Flatten a drawing at DOCUMENT resolution (or `scale` for thumbnails),
    /// independent of zoom and screen scale. JPEG always gets a white matte
    /// under transparency, never black.
    static func rasterize(_ ops: [DrawOp], width: Int, height: Int, background: String, jpeg: Bool, scale: Double = 1, images: Images?) -> CGImage? {
        let w = max(1, Int((Double(width) * scale).rounded(.toNearestOrAwayFromZero)))
        let h = max(1, Int((Double(height) * scale).rounded(.toNearestOrAwayFromZero)))
        guard let context = makeContext(width: w, height: h) else { return nil }
        let target = Target(context: context, k: scale, ox: 0, oy: 0, width: w, height: h)
        replay(target, ops, from: ops.replayStart, to: ops.count, images: images)
        underlay(context, background: jpeg && background == "transparent" ? "#ffffff" : background, width: w, height: h)
        guard let image = context.makeImage() else { return nil }
        guard jpeg, let opaque = makeContext(width: w, height: h, opaque: true) else { return image }
        opaque.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))  // Already white-matted; drop alpha.
        return opaque.makeImage()
    }

    static func encode(_ image: CGImage, jpeg: Bool, quality: Double = 0.92) -> Data? {
        try? DrawAssets.encodeImage(image, png: !jpeg, quality: quality)
    }

    /// RGBA (straight alpha, 0–255) of one pixel of an image (tests and diagnostics).
    static func pixel(_ image: CGImage, x: Int, y: Int) -> [Int] {
        guard let context = CGContext(data: nil, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 4, space: sRGB,
                                      bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return [] }
        context.interpolationQuality = .none
        context.draw(image, in: CGRect(x: -x, y: -(image.height - 1 - y), width: image.width, height: image.height))
        guard let data = context.data else { return [] }
        let p = data.bindMemory(to: UInt8.self, capacity: 4)
        let a = Int(p[3])
        guard a > 0 else { return [0, 0, 0, 0] }
        return [Int(p[0]), Int(p[1]), Int(p[2])].map { min(255, Int((Double($0) * 255 / Double(a)).rounded())) } + [a]
    }
}
