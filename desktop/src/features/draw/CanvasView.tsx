import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, type RefObject } from "react";
import { StrokeCapture, type Captured, type Sample } from "./capture";
import { operationId, type EraseOp, type Operation, type StrokeOp } from "./model";
import { Scratch, drawErase, drawOperation, drawStroke, replay, type Context2D, type Images, type Surface, type Target } from "./render";
import type { DrawSession } from "./session";
import {
  clampPan, cssToDoc, fit, panBy, rescale, scale, stepZoom, wheelPixels, wheelZoomFactor, zoomAt,
  type Point, type View,
} from "./viewport";

// The Draw canvas. Pointer input never goes through React state: strokes are
// captured in refs and painted in the next animation frame.
//
// Layers (device pixels):
//   cache    — the committed strokes (ops[0:head]) rendered once for the
//              current zoom; the whole page when it fits a memory budget,
//              otherwise the visible area plus a margin.
//   display  — the on-screen canvas: page background, the cache blitted at an
//              integer offset, the live stroke, and the brush outline.
// A completed stroke is drawn onto the cache incrementally; undo, redo, load
// and zoom changes replay the operations.

export type Tool = "pen" | "erase";
export interface Brush { tool: Tool; color: string; size: number; opacity: number }
export interface ViewInfo { zoom: number }
export interface CanvasHandle {
  zoomIn: () => void;
  zoomOut: () => void;
  fit: () => void;
  actualSize: () => void;
  /** A downscaled copy of the committed drawing when the cache holds the whole page. */
  thumbnail: (maxSide: number) => Surface | null;
}

const CACHE_BUDGET = 4096 * 4096;     // Device pixels (64 MiB RGBA) for a whole-page cache.
const MARGIN = 384;                    // Device pixels rendered around the viewport otherwise.
const REBUILD_DELAY = 110;             // After zoom gestures settle.

interface Cache {
  surface: Surface;
  ctx: Context2D;
  /** View it was rendered for: scale and device offset of the document origin. */
  k: number;
  ox: number;
  oy: number;
  /** Device rect it covers, in canvas coordinates under that view. */
  rx: number;
  ry: number;
  rw: number;
  rh: number;
  full: boolean;
  version: number;
}

function surface(width: number, height: number): Surface {
  if (typeof OffscreenCanvas !== "undefined") return new OffscreenCanvas(width, height);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

function liveOp(captured: Captured, brush: Brush): StrokeOp | EraseOp {
  if (captured.tool === "erase") return { type: "erase", id: "live0000", width: brush.size, points: captured.points };
  return { type: "stroke", id: "live0000", tool: "pen", color: brush.color, width: brush.size, opacity: brush.opacity, pressure: captured.pressure, points: captured.points };
}

export const CanvasView = forwardRef<CanvasHandle, {
  session: DrawSession;
  brush: Brush;
  visible: boolean;
  /** Called only when the zoom changes (never per frame). */
  onView: (info: ViewInfo) => void;
  onNotice: (message: string) => void;
  label: string;
  /** The pointer's document coordinate is written here directly, without React. */
  pointerOut?: RefObject<HTMLElement | null>;
  /** Decoded imported images (null while one is still arriving). */
  images?: Images;
}>(function CanvasView({ session, brush, visible, onView, onNotice, label, pointerOut, images }, handle) {
  const host = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const view = useRef<View>({ zoom: 1, ox: 0, oy: 0, dpr: window.devicePixelRatio || 1 });
  const size = useRef({ width: 0, height: 0 });     // CSS px of the stage
  const cache = useRef<Cache | null>(null);
  const scratch = useRef(new Scratch());
  const capture = useRef(new StrokeCapture());
  const live = useRef<StrokeOp | EraseOp | null>(null);
  const eraseBase = useRef<Surface | null>(null);
  const pan = useRef<{ id: number; x: number; y: number } | null>(null);
  const space = useRef(false);
  const hover = useRef<Point | null>(null);
  const frame = useRef(0);
  const rebuildTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const fitted = useRef<string | null>(null);
  /** True until the person zooms or pans: a resize then re-fits the page. */
  const fitMode = useRef(true);
  const checker = useRef<{ dpr: number; pattern: CanvasPattern | null } | null>(null);
  const brushRef = useRef(brush);
  brushRef.current = brush;
  const sessionRef = useRef(session);
  sessionRef.current = session;
  const visibleRef = useRef(visible);
  visibleRef.current = visible;
  const imagesRef = useRef(images);
  imagesRef.current = images;
  const callbacks = useRef({ onView, onNotice });
  callbacks.current = { onView, onNotice };
  const reported = useRef({ zoom: -1, pointer: "" });

  const docSize = () => ({ width: sessionRef.current.drawing.width, height: sessionRef.current.drawing.height });

  const setCursor = useCallback(() => {
    const element = canvas.current;
    if (!element) return;
    element.dataset.cursor = pan.current ? "panning" : space.current ? "pan" : brushRef.current.tool;
  }, []);

  /** Render the committed operations into the cache for the current view. */
  const rebuild = useCallback(() => {
    clearTimeout(rebuildTimer.current);
    rebuildTimer.current = undefined;
    const s = sessionRef.current, v = view.current, element = canvas.current;
    if (!element) return;
    const k = scale(v);
    const pw = Math.ceil(s.drawing.width * k), ph = Math.ceil(s.drawing.height * k);
    const full = pw * ph <= CACHE_BUDGET && pw <= 16384 && ph <= 16384;
    let rx: number, ry: number, rw: number, rh: number;
    if (full) {
      rx = v.ox; ry = v.oy; rw = pw; rh = ph;
    } else {
      const x0 = Math.max(v.ox, -MARGIN), y0 = Math.max(v.oy, -MARGIN);
      const x1 = Math.min(v.ox + pw, element.width + MARGIN), y1 = Math.min(v.oy + ph, element.height + MARGIN);
      rx = Math.floor(x0); ry = Math.floor(y0); rw = Math.ceil(x1 - rx); rh = Math.ceil(y1 - ry);
    }
    if (rw <= 0 || rh <= 0) { cache.current = null; return; }
    let current = cache.current;
    if (!current || current.surface.width !== rw || current.surface.height !== rh) {
      const made = surface(rw, rh);
      current = { surface: made, ctx: made.getContext("2d") as Context2D, k, ox: v.ox, oy: v.oy, rx, ry, rw, rh, full, version: -1 };
    }
    Object.assign(current, { k, ox: v.ox, oy: v.oy, rx, ry, rw, rh, full });
    const target: Target = { ctx: current.ctx, k, ox: v.ox - rx, oy: v.oy - ry, width: rw, height: rh };
    const started = performance.now();
    current.ctx.setTransform(1, 0, 0, 1, 0, 0);
    current.ctx.clearRect(0, 0, rw, rh);
    const ops = s.visible;
    replay(target, ops, s.replayStart, ops.length, scratch.current, imagesRef.current);
    current.version = s.version;
    cache.current = current;
    element.dataset.replayMs = String(Math.round(performance.now() - started));
  }, []);

  const cacheTarget = (c: Cache): Target => ({ ctx: c.ctx, k: c.k, ox: c.ox - c.rx, oy: c.oy - c.ry, width: c.rw, height: c.rh });

  /** Does the cache still cover what is visible at the current zoom? */
  const cacheCovers = (c: Cache, v: View, element: HTMLCanvasElement) => {
    if (Math.abs(c.k - scale(v)) > 1e-9) return false;
    if (c.full) return true;
    const dx = v.ox - c.ox, dy = v.oy - c.oy;
    const k = scale(v), d = docSize();
    const vx0 = Math.max(0, v.ox), vy0 = Math.max(0, v.oy);
    const vx1 = Math.min(element.width, v.ox + d.width * k), vy1 = Math.min(element.height, v.oy + d.height * k);
    return c.rx + dx <= vx0 && c.ry + dy <= vy0 && c.rx + dx + c.rw >= vx1 && c.ry + dy + c.rh >= vy1;
  };

  const present = useCallback(() => {
    frame.current = 0;
    const element = canvas.current, s = sessionRef.current;
    if (!element || !visibleRef.current) return;
    const ctx = element.getContext("2d");
    if (!ctx) return;
    const v = view.current, k = scale(v);
    let c = cache.current;
    if (!c || c.version !== s.version) {
      // Load, undo, redo, resize: replay now so the picture is right this frame.
      if (!capture.current.active) { rebuild(); c = cache.current; }
    } else if (!cacheCovers(c, v, element) && rebuildTimer.current === undefined) {
      // Zoom or pan past the cached area: show the stale cache (scaled or
      // shifted) and replay once the gesture settles (throttled).
      const settle = () => {
        if (capture.current.active) { rebuildTimer.current = setTimeout(settle, REBUILD_DELAY); return; }
        rebuildTimer.current = undefined;
        rebuild();
        request();
      };
      rebuildTimer.current = setTimeout(settle, REBUILD_DELAY);
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, element.width, element.height);
    const w = s.drawing.width * k, h = s.drawing.height * k;
    // Page: a soft shadow, then white or a checkerboard for transparency.
    ctx.save();
    ctx.shadowColor = "rgba(0, 0, 0, 0.28)";
    ctx.shadowBlur = 14 * v.dpr;
    ctx.shadowOffsetY = 2 * v.dpr;
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(v.ox, v.oy, w, h);
    ctx.restore();
    if (s.background === "transparent") {
      if (!checker.current || checker.current.dpr !== v.dpr) {
        const cell = Math.max(4, Math.round(8 * v.dpr));
        const tile = surface(cell * 2, cell * 2);
        const tctx = tile.getContext("2d") as Context2D;
        tctx.fillStyle = "#ffffff";
        tctx.fillRect(0, 0, cell * 2, cell * 2);
        tctx.fillStyle = "#d9d9d9";
        tctx.fillRect(0, 0, cell, cell);
        tctx.fillRect(cell, cell, cell, cell);
        checker.current = { dpr: v.dpr, pattern: ctx.createPattern(tile as CanvasImageSource, "repeat") };
      }
      ctx.fillStyle = checker.current.pattern ?? "#eeeeee";
      ctx.fillRect(v.ox, v.oy, w, h);
    }
    ctx.save();
    ctx.beginPath();
    ctx.rect(v.ox, v.oy, w, h);
    ctx.clip();
    if (c) {
      const ratio = k / c.k;
      const dx = (c.rx - c.ox) * ratio + v.ox, dy = (c.ry - c.oy) * ratio + v.oy;
      ctx.imageSmoothingEnabled = Math.abs(ratio - 1) > 1e-9;
      ctx.drawImage(c.surface as CanvasImageSource, dx, dy, c.rw * ratio, c.rh * ratio);
      ctx.imageSmoothingEnabled = true;
    }
    const stroke = live.current;
    if (stroke && stroke.type === "stroke")
      drawStroke({ ctx, k, ox: v.ox, oy: v.oy, width: element.width, height: element.height }, stroke, scratch.current);
    // Images still arriving (from another device, or loading): a labelled frame,
    // never part of the drawing or an export.
    const lookup = imagesRef.current;
    const ops = s.visible;
    for (let i = s.replayStart; i < ops.length; i++) {
      const op = ops[i];
      if (op.type !== "image" || !lookup || lookup(op.asset_id)) continue;
      const x = op.x * k + v.ox, y = op.y * k + v.oy, w = op.width * k, h = op.height * k;
      ctx.save();
      ctx.fillStyle = "rgba(128, 128, 128, 0.12)";
      ctx.fillRect(x, y, w, h);
      ctx.setLineDash([6 * v.dpr, 4 * v.dpr]);
      ctx.lineWidth = Math.max(1, v.dpr);
      ctx.strokeStyle = "rgba(90, 90, 90, 0.8)";
      ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
      if (w > 90 * v.dpr && h > 24 * v.dpr) {
        ctx.fillStyle = "rgba(60, 60, 60, 0.9)";
        ctx.font = `${12 * v.dpr}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("Image arriving…", x + w / 2, y + h / 2);
      }
      ctx.restore();
    }
    ctx.restore();
    // Brush outline under the pointer (document size at the current zoom).
    const at = hover.current;
    if (at && !pan.current && !space.current && !s.readOnly) {
      const radius = Math.max(1.5, (brushRef.current.size * k) / 2);
      ctx.save();
      ctx.lineWidth = Math.max(1, v.dpr);
      ctx.setLineDash(brushRef.current.tool === "erase" ? [3 * v.dpr, 3 * v.dpr] : []);
      ctx.beginPath();
      ctx.arc(at.x * v.dpr, at.y * v.dpr, radius, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(at.x * v.dpr, at.y * v.dpr, radius + ctx.lineWidth, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(0, 0, 0, 0.55)";
      ctx.stroke();
      ctx.restore();
    }
    element.dataset.zoom = String(v.zoom);
    element.dataset.ox = String(v.ox);
    element.dataset.oy = String(v.oy);
    element.dataset.dpr = String(v.dpr);
    if (reported.current.zoom !== v.zoom) {
      reported.current.zoom = v.zoom;
      callbacks.current.onView({ zoom: v.zoom });
    }
    const out = pointerOut?.current;
    if (out) {
      const doc = at ? cssToDoc(v, at) : null;
      const text = doc && doc.x >= 0 && doc.y >= 0 && doc.x < s.drawing.width && doc.y < s.drawing.height
        ? `${Math.floor(doc.x)}, ${Math.floor(doc.y)} px` : "";
      if (text !== reported.current.pointer) { reported.current.pointer = text; out.textContent = text; }
    }
  }, [rebuild, pointerOut]);

  const request = useCallback(() => {
    if (!frame.current) frame.current = requestAnimationFrame(present);
  }, [present]);

  const setView = useCallback((next: View) => {
    const s = sessionRef.current;
    view.current = clampPan(next, { width: s.drawing.width, height: s.drawing.height }, size.current);
    request();
  }, [request]);

  /** Match the backing store to the stage size and display scale. */
  const measure = useCallback(() => {
    const element = canvas.current, stage = host.current;
    if (!element || !stage) return false;
    const width = stage.clientWidth, height = stage.clientHeight;
    if (!width || !height) return false;
    const dpr = window.devicePixelRatio || 1;
    const changed = width !== size.current.width || height !== size.current.height || dpr !== view.current.dpr;
    size.current = { width, height };
    if (changed) {
      element.style.width = `${width}px`;
      element.style.height = `${height}px`;
      element.width = Math.round(width * dpr);
      element.height = Math.round(height * dpr);
      view.current = rescale(view.current, dpr);
      cache.current = null;
    }
    return true;
  }, []);

  const fitView = useCallback(() => {
    if (!measure()) return;
    fitMode.current = true;
    setView(fit(docSize(), size.current, view.current.dpr));
  }, [measure, setView]);
  /** A zoom or pan chosen by the person (leaves fit mode). */
  const userView = useCallback((next: View) => {
    fitMode.current = false;
    setView(next);
  }, [setView]);

  // First show of each drawing fits it to the window.
  useEffect(() => {
    if (!visible) return;
    if (fitted.current !== session.id && measure()) {
      fitted.current = session.id;
      cache.current = null;
      fitView();
    } else {
      measure();
      request();
    }
  }, [session, visible, measure, fitView, request]);

  useEffect(() => {
    const stage = host.current;
    if (!stage) return;
    const observer = new ResizeObserver(() => {
      if (!visibleRef.current) return;
      // The stage changed size mid-stroke: finish the stroke before the cache is rebuilt.
      if (capture.current.active) finishRef.current(capture.current.end(capture.current.pointerId!));
      if (!measure()) return;
      if (fitMode.current) setView(fit(docSize(), size.current, view.current.dpr));
      else setView(view.current);
    });
    observer.observe(stage);
    // Moving to a monitor with another scale changes devicePixelRatio.
    let media: MediaQueryList | null = null;
    const watch = () => {
      media?.removeEventListener("change", onScale);
      media = window.matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`);
      media.addEventListener("change", onScale);
    };
    const onScale = () => { watch(); if (measure()) setView(view.current); };
    watch();
    return () => { observer.disconnect(); media?.removeEventListener("change", onScale); };
  }, [measure, setView]);

  // Re-render when the session's picture changes (undo, redo, load) or saves.
  useEffect(() => session.subscribe(request), [session, request]);
  useEffect(() => { setCursor(); request(); }, [brush, request, setCursor]);
  useEffect(() => () => {
    cancelAnimationFrame(frame.current);
    clearTimeout(rebuildTimer.current);
  }, []);

  const local = (event: { clientX: number; clientY: number }): Point => {
    const rect = canvas.current!.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };
  const sample = (event: PointerEvent): Sample => {
    const doc = cssToDoc(view.current, local(event));
    return { x: doc.x, y: doc.y, pressure: event.pressure };
  };

  const finishStroke = useCallback((captured: Captured | null) => {
    const s = sessionRef.current;
    const op = live.current;
    live.current = null;
    const base = eraseBase.current;
    eraseBase.current = null;
    if (!captured || !op) { request(); return; }
    const id = operationId();
    const final: Operation = captured.tool === "erase"
      ? { type: "erase", id, width: (op as EraseOp).width, points: captured.points }
      : { ...(op as StrokeOp), id, pressure: captured.pressure, points: captured.points };
    const c = cache.current;
    const current = c && c.version === s.version;
    const refused = s.edit(final);
    if (refused) {
      callbacks.current.onNotice(refused);
      if (base && c) { c.ctx.setTransform(1, 0, 0, 1, 0, 0); c.ctx.clearRect(0, 0, c.rw, c.rh); c.ctx.drawImage(base as CanvasImageSource, 0, 0); }
      request();
      return;
    }
    if (capture.current.limited) callbacks.current.onNotice("That stroke reached 10,000 points and ended there. Lift the pen and continue.");
    if (c && current) {
      // Incremental commit: the cache showed ops[0:head-1]; add the new op.
      if (final.type === "erase" && base) {
        c.ctx.setTransform(1, 0, 0, 1, 0, 0);
        c.ctx.clearRect(0, 0, c.rw, c.rh);
        c.ctx.drawImage(base as CanvasImageSource, 0, 0);
      }
      drawOperation(cacheTarget(c), final, scratch.current, imagesRef.current);
      c.version = s.version;
    }
    request();
  }, [request]);

  const finishRef = useRef(finishStroke);
  finishRef.current = finishStroke;

  const cancelStroke = useCallback(() => {
    const c = cache.current, base = eraseBase.current;
    if (c && base) {
      c.ctx.setTransform(1, 0, 0, 1, 0, 0);
      c.ctx.clearRect(0, 0, c.rw, c.rh);
      c.ctx.drawImage(base as CanvasImageSource, 0, 0);
    }
    eraseBase.current = null;
    live.current = null;
    request();
  }, [request]);

  /** Show the eraser live by re-applying the whole gesture to a pre-gesture copy. */
  const paintErase = useCallback(() => {
    const c = cache.current, base = eraseBase.current, op = live.current;
    if (!c || !base || !op || op.type !== "erase") return;
    c.ctx.setTransform(1, 0, 0, 1, 0, 0);
    c.ctx.clearRect(0, 0, c.rw, c.rh);
    c.ctx.drawImage(base as CanvasImageSource, 0, 0);
    drawErase(cacheTarget(c), op);
  }, []);

  useEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const down = (event: PointerEvent) => {
      element.focus({ preventScroll: true });
      const s = sessionRef.current;
      if (event.button === 1 || (event.button === 0 && space.current)) {
        if (capture.current.active) return;
        event.preventDefault();
        element.setPointerCapture(event.pointerId);
        pan.current = { id: event.pointerId, ...local(event) };
        setCursor();
        return;
      }
      const eraserEnd = event.pointerType === "pen" && (event.button === 5 || (event.buttons & 32) !== 0);
      if (event.button !== 0 && !eraserEnd) return;
      if (capture.current.active || pan.current) return;   // Only one pointer draws at a time.
      if (s.readOnly) { callbacks.current.onNotice("This drawing is in Recently Deleted. Restore it to edit it."); return; }
      event.preventDefault();
      const tool = eraserEnd ? "erase" : brushRef.current.tool;
      // Ensure the cache is current before an incremental commit or erase preview.
      const c = cache.current;
      if (!c || c.version !== s.version || Math.abs(c.k - scale(view.current)) > 1e-9 || !cacheCovers(c, view.current, element)) rebuild();
      const start = sample(event);
      capture.current.begin({ ...start, pointerId: event.pointerId, pointerType: event.pointerType, tool, minDistance: 0.35 / view.current.zoom });
      element.setPointerCapture(event.pointerId);
      if (tool === "erase" && cache.current) {
        const copy = surface(cache.current.rw, cache.current.rh);
        (copy.getContext("2d") as Context2D).drawImage(cache.current.surface as CanvasImageSource, 0, 0);
        eraseBase.current = copy;
      }
      live.current = liveOp(capture.current.snapshot()!, { ...brushRef.current, tool });
      if (tool === "erase") paintErase();
      request();
    };
    const move = (event: PointerEvent) => {
      hover.current = local(event);
      const p = pan.current;
      if (p && event.pointerId === p.id) {
        const at = local(event);
        const next = panBy(view.current, at.x - p.x, at.y - p.y);
        pan.current = { ...p, ...at };
        userView(next);
        return;
      }
      if (capture.current.active && event.pointerId === capture.current.pointerId) {
        const events = typeof event.getCoalescedEvents === "function" ? event.getCoalescedEvents() : [];
        const changed = capture.current.move(event.pointerId, (events.length ? events : [event]).map(sample));
        if (changed) {
          const tool = capture.current.tool!;
          live.current = liveOp(capture.current.snapshot()!, { ...brushRef.current, tool });
          if (tool === "erase") paintErase();
        }
      }
      request();
    };
    const up = (event: PointerEvent) => {
      if (pan.current && event.pointerId === pan.current.id) {
        pan.current = null;
        setCursor();
        request();
        return;
      }
      if (capture.current.active && event.pointerId === capture.current.pointerId) {
        finishStroke(capture.current.end(event.pointerId, sample(event)));
      }
    };
    const cancel = (event: PointerEvent) => {
      if (pan.current && event.pointerId === pan.current.id) { pan.current = null; setCursor(); }
      if (capture.current.cancel(event.pointerId)) cancelStroke();
    };
    // Capture lost without pointerup (window switch, element hidden): keep what was drawn.
    const lost = (event: PointerEvent) => {
      if (pan.current && event.pointerId === pan.current.id) { pan.current = null; setCursor(); }
      if (capture.current.active && event.pointerId === capture.current.pointerId) finishStroke(capture.current.end(event.pointerId));
    };
    const leave = () => { hover.current = null; request(); };
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      if (capture.current.active) return;
      const v = view.current;
      const dy = wheelPixels(event.deltaY, event.deltaMode, size.current.height);
      const dx = wheelPixels(event.deltaX, event.deltaMode, size.current.width);
      if (event.ctrlKey || event.metaKey) {
        // Ctrl+wheel and trackpad pinch zoom around the pointer.
        userView(zoomAt(v, v.zoom * wheelZoomFactor(dy), local(event)));
      } else if (event.shiftKey && !dx) {
        userView(panBy(v, -dy, 0));
      } else {
        userView(panBy(v, -dx, -dy));
      }
    };
    const context = (event: MouseEvent) => event.preventDefault();
    element.addEventListener("pointerdown", down);
    element.addEventListener("pointermove", move);
    element.addEventListener("pointerup", up);
    element.addEventListener("pointercancel", cancel);
    element.addEventListener("lostpointercapture", lost);
    element.addEventListener("pointerleave", leave);
    element.addEventListener("wheel", wheel, { passive: false });
    element.addEventListener("contextmenu", context);
    return () => {
      element.removeEventListener("pointerdown", down);
      element.removeEventListener("pointermove", move);
      element.removeEventListener("pointerup", up);
      element.removeEventListener("pointercancel", cancel);
      element.removeEventListener("lostpointercapture", lost);
      element.removeEventListener("pointerleave", leave);
      element.removeEventListener("wheel", wheel);
      element.removeEventListener("contextmenu", context);
    };
  }, [finishStroke, cancelStroke, paintErase, rebuild, request, userView, setCursor]);

  // Space held = temporary hand tool (never while typing in a field).
  useEffect(() => {
    if (!visible) return;
    const typing = (target: EventTarget | null) =>
      target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));
    const keydown = (event: KeyboardEvent) => {
      if (event.code === "Space" && !typing(event.target) && !event.ctrlKey && !event.metaKey && !event.altKey) {
        if (event.target instanceof HTMLButtonElement) return;   // Space still presses a focused button.
        event.preventDefault();
        if (!space.current) { space.current = true; setCursor(); request(); }
      }
    };
    const keyup = (event: KeyboardEvent) => {
      if (event.code === "Space" && space.current) { space.current = false; setCursor(); request(); }
    };
    const blur = () => {
      space.current = false;
      pan.current = null;
      if (capture.current.active) finishStroke(capture.current.end(capture.current.pointerId!));
      setCursor();
    };
    window.addEventListener("keydown", keydown);
    window.addEventListener("keyup", keyup);
    window.addEventListener("blur", blur);
    return () => {
      window.removeEventListener("keydown", keydown);
      window.removeEventListener("keyup", keyup);
      window.removeEventListener("blur", blur);
    };
  }, [visible, finishStroke, request, setCursor]);

  useImperativeHandle(handle, () => ({
    zoomIn: () => { measure(); userView(zoomAt(view.current, stepZoom(view.current.zoom, 1), { x: size.current.width / 2, y: size.current.height / 2 })); },
    zoomOut: () => { measure(); userView(zoomAt(view.current, stepZoom(view.current.zoom, -1), { x: size.current.width / 2, y: size.current.height / 2 })); },
    fit: fitView,
    actualSize: () => { measure(); userView(zoomAt(view.current, 1, { x: size.current.width / 2, y: size.current.height / 2 })); },
    thumbnail: (maxSide: number) => {
      const c = cache.current, s = sessionRef.current;
      if (!c || !c.full || c.version !== s.version || capture.current.active) return null;
      const ratio = Math.min(1, maxSide / Math.max(s.drawing.width, s.drawing.height));
      const w = Math.max(1, Math.round(s.drawing.width * ratio)), h = Math.max(1, Math.round(s.drawing.height * ratio));
      const out = surface(w, h);
      const octx = out.getContext("2d") as Context2D;
      octx.imageSmoothingQuality = "high";
      octx.drawImage(c.surface as CanvasImageSource, 0, 0, c.rw, c.rh, 0, 0, w, h);
      return out;
    },
  }), [fitView, measure, userView]);

  return (
    <div className="draw-stage" ref={host}>
      <canvas
        ref={canvas}
        className="draw-canvas"
        role="img"
        tabIndex={0}
        aria-label={label}
        aria-describedby="draw-canvas-help"
        data-cursor={brush.tool}
      />
      <p id="draw-canvas-help" className="sr-only">
        Freehand drawing canvas. Draw with a mouse, pen or touch. Hold Space and drag, or drag with the middle
        button, to pan. Ctrl and the mouse wheel zoom. P selects the pen, E the eraser, Ctrl+Z undoes.
      </p>
    </div>
  );
});
