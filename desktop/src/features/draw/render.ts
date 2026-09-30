// Canvas 2D renderer for OLIVE Draw operations. The operation log is the
// source of truth; this draws it. Every function takes an explicit
// document → device mapping, so the same code renders the on-screen cache,
// the live stroke, thumbnails and full-resolution exports identically.
//
// Smoothing: a stroke passes through its first and last points and follows
// quadratic curves through the midpoints of the points between. It depends
// only on the stored points, never on frame rate or zoom.
import type { Background, EraseOp, ImageOp, Operation, StrokeOp } from "./model";

/** Decoded imported images by asset id (null while one is still arriving). */
export type Images = (assetId: string) => CanvasImageSource | null;

export type Context2D = CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;
export type Surface = HTMLCanvasElement | OffscreenCanvas;

/** A context plus the mapping device = doc × k + (ox, oy), and its size in device px. */
export interface Target {
  ctx: Context2D;
  k: number;
  ox: number;
  oy: number;
  width: number;
  height: number;
}

/** Width multiplier for a pen pressure sample. The selected size is the width
 *  at full pressure; a light touch draws at one fifth of it. */
export const pressureWidth = (pressure: number) => 0.2 + 0.8 * pressure;

function makeSurface(width: number, height: number): Surface {
  if (typeof OffscreenCanvas !== "undefined") return new OffscreenCanvas(width, height);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

/** A reusable scratch layer for translucent strokes (grown on demand). */
export class Scratch {
  private surface: Surface | null = null;
  constructor(private create: (w: number, h: number) => Surface = makeSurface) {}
  take(width: number, height: number): { surface: Surface; ctx: Context2D } {
    if (!this.surface || this.surface.width < width || this.surface.height < height) {
      const w = Math.max(width, this.surface?.width ?? 0, 256), h = Math.max(height, this.surface?.height ?? 0, 256);
      this.surface = this.create(w, h);
    }
    return { surface: this.surface, ctx: this.surface.getContext("2d") as Context2D };
  }
  release() { this.surface = null; }
}

function setDoc(target: Target, ctx: Context2D = target.ctx, dx = 0, dy = 0) {
  ctx.setTransform(target.k, 0, 0, target.k, target.ox - dx, target.oy - dy);
}

/** Trace a smoothed polyline (points in document px) as the current path. */
export function tracePath(ctx: Context2D, points: number[], stride: number) {
  const n = points.length / stride;
  ctx.beginPath();
  ctx.moveTo(points[0], points[1]);
  if (n === 1) {
    ctx.lineTo(points[0] + 0.001, points[1]);   // Zero-length path: the round cap draws a dot.
    return;
  }
  for (let i = 1; i < n - 1; i++) {
    const x = points[i * stride], y = points[i * stride + 1];
    const nx = points[(i + 1) * stride], ny = points[(i + 1) * stride + 1];
    ctx.quadraticCurveTo(x, y, (x + nx) / 2, (y + ny) / 2);
  }
  ctx.lineTo(points[(n - 1) * stride], points[(n - 1) * stride + 1]);
}

/** Device-pixel bounds of a stroke inside the target (null when fully outside). */
export function strokeBounds(target: Target, points: number[], stride: number, width: number) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (let i = 0; i < points.length; i += stride) {
    const x = points[i], y = points[i + 1];
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
  }
  const pad = width / 2 + 2 / target.k;
  const x0 = Math.max(0, Math.floor((minX - pad) * target.k + target.ox));
  const y0 = Math.max(0, Math.floor((minY - pad) * target.k + target.oy));
  const x1 = Math.min(target.width, Math.ceil((maxX + pad) * target.k + target.ox));
  const y1 = Math.min(target.height, Math.ceil((maxY + pad) * target.k + target.oy));
  if (x1 <= x0 || y1 <= y0) return null;
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}

function inkStroke(ctx: Context2D, op: StrokeOp) {
  ctx.strokeStyle = op.color;
  ctx.fillStyle = op.color;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  if (!op.pressure) {
    ctx.lineWidth = op.width;
    tracePath(ctx, op.points, 2);
    ctx.stroke();
    return;
  }
  // Pressure: each smoothed piece gets the width of the point that shapes it.
  const p = op.points, n = p.length / 3;
  if (n === 1) {
    ctx.beginPath();
    ctx.arc(p[0], p[1], (op.width * pressureWidth(p[2])) / 2, 0, Math.PI * 2);
    ctx.fill();
    return;
  }
  let sx = p[0], sy = p[1];
  for (let i = 1; i < n; i++) {
    const x = p[i * 3], y = p[i * 3 + 1];
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineWidth = op.width * pressureWidth(p[i * 3 + 2]);
    if (i < n - 1) {
      const mx = (x + p[(i + 1) * 3]) / 2, my = (y + p[(i + 1) * 3 + 1]) / 2;
      ctx.quadraticCurveTo(x, y, mx, my);
      sx = mx;
      sy = my;
    } else {
      ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
}

export function drawStroke(target: Target, op: StrokeOp, scratch: Scratch) {
  const { ctx } = target;
  if (op.opacity >= 1) {
    ctx.save();
    setDoc(target);
    inkStroke(ctx, op);
    ctx.restore();
    return;
  }
  // Translucent strokes are drawn opaque on a scratch layer and composited
  // once, so overlapping segments and caps never darken.
  const box = strokeBounds(target, op.points, op.pressure ? 3 : 2, op.width);
  if (!box) return;
  const layer = scratch.take(box.w, box.h);
  layer.ctx.save();
  layer.ctx.setTransform(1, 0, 0, 1, 0, 0);
  layer.ctx.globalCompositeOperation = "source-over";
  layer.ctx.globalAlpha = 1;
  layer.ctx.clearRect(0, 0, box.w, box.h);
  setDoc(target, layer.ctx, box.x, box.y);
  inkStroke(layer.ctx, op);
  layer.ctx.restore();
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = op.opacity;
  ctx.drawImage(layer.surface, 0, 0, box.w, box.h, box.x, box.y, box.w, box.h);
  ctx.restore();
}

/** The eraser removes ink from the strokes layer, revealing the background. */
export function drawErase(target: Target, op: EraseOp) {
  const { ctx } = target;
  ctx.save();
  setDoc(target);
  ctx.globalCompositeOperation = "destination-out";
  ctx.strokeStyle = "#000000";
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.lineWidth = op.width;
  tracePath(ctx, op.points, 2);
  ctx.stroke();
  ctx.restore();
}

export function clearTarget(target: Target) {
  const { ctx } = target;
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalCompositeOperation = "source-over";
  ctx.clearRect(0, 0, target.width, target.height);
  ctx.restore();
}

/** An imported image sits on the drawing layer at its document rectangle, in
 *  operation order: strokes drawn later cover it, a later eraser erases it and
 *  Clear removes it, exactly like ink. A missing asset draws nothing here (the
 *  view shows a placeholder; export waits for it). */
export function drawImageOp(target: Target, op: ImageOp, images?: Images) {
  const source = images?.(op.asset_id);
  if (!source) return;
  const { ctx } = target;
  ctx.save();
  setDoc(target);
  ctx.globalAlpha = op.opacity;
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(source, op.x, op.y, op.width, op.height);
  ctx.restore();
}

export function drawOperation(target: Target, op: Operation, scratch: Scratch, images?: Images) {
  if (op.type === "stroke") drawStroke(target, op, scratch);
  else if (op.type === "erase") drawErase(target, op);
  else if (op.type === "clear") clearTarget(target);
  else if (op.type === "image") drawImageOp(target, op, images);
  // Background changes are applied by the compositor, not the strokes layer.
}

/** Replay ops[from:to] onto a strokes layer (transparent where nothing was drawn). */
export function replay(target: Target, ops: readonly Operation[], from: number, to: number, scratch: Scratch, images?: Images) {
  for (let i = from; i < to; i++) drawOperation(target, ops[i], scratch, images);
}

/** Paint the page background beneath an already-rendered strokes layer. */
export function underlayBackground(ctx: Context2D, background: Background | string, width: number, height: number) {
  if (background === "transparent") return;
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalCompositeOperation = "destination-over";
  ctx.fillStyle = background;
  ctx.fillRect(0, 0, width, height);
  ctx.restore();
}

export interface RasterOptions {
  width: number;
  height: number;
  /** Background in effect; JPEG always gets `matte` under transparency. */
  background: Background;
  format: "png" | "jpeg";
  quality?: number;
  matte?: string;
  scale?: number;
  create?: (w: number, h: number) => Surface;
  images?: Images;
}

/** Flatten a drawing at DOCUMENT resolution (or `scale` for thumbnails),
 *  independent of the current zoom and display scale. */
export function rasterize(ops: readonly Operation[], from: number, to: number, options: RasterOptions): Surface {
  const scale = options.scale ?? 1;
  const width = Math.max(1, Math.round(options.width * scale)), height = Math.max(1, Math.round(options.height * scale));
  const create = options.create ?? makeSurface;
  const surface = create(width, height);
  const ctx = surface.getContext("2d") as Context2D;
  const target: Target = { ctx, k: scale, ox: 0, oy: 0, width, height };
  const scratch = new Scratch(create);
  replay(target, ops, from, to, scratch, options.images);
  scratch.release();
  // JPEG has no alpha: composite onto an explicit matte (white by default)
  // rather than letting transparent pixels turn black.
  const under = options.format === "jpeg" && options.background === "transparent" ? options.matte || "#ffffff" : options.background;
  underlayBackground(ctx, under, width, height);
  return surface;
}

export async function encode(surface: Surface, format: "png" | "jpeg", quality = 0.92): Promise<Uint8Array<ArrayBuffer>> {
  const type = format === "png" ? "image/png" : "image/jpeg";
  let blob: Blob | null;
  if ("convertToBlob" in surface) blob = await surface.convertToBlob(format === "png" ? { type } : { type, quality });
  else blob = await new Promise<Blob | null>((resolve) => (surface as HTMLCanvasElement).toBlob(resolve, type, quality));
  if (!blob) throw new Error("Could not export image");
  return new Uint8Array(await blob.arrayBuffer());
}
