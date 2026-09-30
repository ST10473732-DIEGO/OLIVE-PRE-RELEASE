// Coordinate model for the Draw canvas. Three spaces are kept separate:
//   document  — drawing pixels (0..width, 0..height); the only space stored.
//   CSS       — layout pixels from pointer events (clientX - canvas left).
//   device    — backing-store pixels: CSS × devicePixelRatio.
// A view maps document → device as  device = doc × zoom × dpr + offset,
// where `offset` is a whole number of device pixels. Keeping the offset
// integral means the cached raster is always blitted on the pixel grid, so
// panning never blurs strokes. Zoom never changes document coordinates: a
// 10 px pen is 10 document pixels at every zoom and display scale.

export const MIN_ZOOM = 0.1;
export const MAX_ZOOM = 16;
/** Zoom steps for the toolbar and Ctrl +/−. */
export const ZOOM_STEPS = [0.1, 0.125, 0.167, 0.25, 0.333, 0.5, 0.667, 0.75, 1, 1.25, 1.5, 2, 3, 4, 6, 8, 12, 16];

export interface View {
  zoom: number;
  /** Device-pixel offset of the document origin inside the canvas element. */
  ox: number;
  oy: number;
  dpr: number;
}
export interface Size { width: number; height: number }
export interface Point { x: number; y: number }

export const clampZoom = (zoom: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
/** Device pixels per document pixel. */
export const scale = (view: View) => view.zoom * view.dpr;

export function cssToDoc(view: View, css: Point): Point {
  const k = scale(view);
  return { x: (css.x * view.dpr - view.ox) / k, y: (css.y * view.dpr - view.oy) / k };
}

export function docToCss(view: View, doc: Point): Point {
  const k = scale(view);
  return { x: (doc.x * k + view.ox) / view.dpr, y: (doc.y * k + view.oy) / view.dpr };
}

export function docToDevice(view: View, doc: Point): Point {
  const k = scale(view);
  return { x: doc.x * k + view.ox, y: doc.y * k + view.oy };
}

/** Keep at least `margin` CSS px of the page inside the viewport so the
 *  drawing cannot be panned out of reach. */
export function clampPan(view: View, doc: Size, viewport: Size, margin = 48): View {
  const k = scale(view);
  const w = doc.width * k, h = doc.height * k;
  const vw = viewport.width * view.dpr, vh = viewport.height * view.dpr;
  const m = Math.min(margin * view.dpr, w / 2, h / 2);
  // At least `m` device px of the page stays inside the viewport on every side.
  const ox = Math.min(Math.max(view.ox, m - w), vw - m);
  const oy = Math.min(Math.max(view.oy, m - h), vh - m);
  return { ...view, ox: Math.round(ox), oy: Math.round(oy) };
}

/** Zoom so that the document point under `anchor` (CSS px) stays under it. */
export function zoomAt(view: View, zoom: number, anchor: Point): View {
  const next = clampZoom(zoom);
  const doc = cssToDoc(view, anchor);
  const k = next * view.dpr;
  return { ...view, zoom: next, ox: Math.round(anchor.x * view.dpr - doc.x * k), oy: Math.round(anchor.y * view.dpr - doc.y * k) };
}

export function panBy(view: View, dxCss: number, dyCss: number): View {
  return { ...view, ox: Math.round(view.ox + dxCss * view.dpr), oy: Math.round(view.oy + dyCss * view.dpr) };
}

/** Fit the whole page inside the viewport (never stretched), centred. */
export function fit(doc: Size, viewport: Size, dpr: number, padding = 24): View {
  const zoom = clampZoom(Math.min(
    Math.max(1, viewport.width - padding * 2) / doc.width,
    Math.max(1, viewport.height - padding * 2) / doc.height,
  ));
  return centre({ zoom, ox: 0, oy: 0, dpr }, doc, viewport);
}

export function centre(view: View, doc: Size, viewport: Size): View {
  const k = scale(view);
  return { ...view, ox: Math.round((viewport.width * view.dpr - doc.width * k) / 2), oy: Math.round((viewport.height * view.dpr - doc.height * k) / 2) };
}

/** The next toolbar zoom step in a direction. */
export function stepZoom(zoom: number, direction: 1 | -1): number {
  if (direction > 0) return ZOOM_STEPS.find((z) => z > zoom + 1e-6) ?? MAX_ZOOM;
  return [...ZOOM_STEPS].reverse().find((z) => z < zoom - 1e-6) ?? MIN_ZOOM;
}

/** When the display scale changes (another monitor, Interface size), keep the
 *  same CSS layout: the view's zoom is unchanged and the offset is rescaled. */
export function rescale(view: View, dpr: number): View {
  if (dpr === view.dpr) return view;
  return { zoom: view.zoom, dpr, ox: Math.round((view.ox / view.dpr) * dpr), oy: Math.round((view.oy / view.dpr) * dpr) };
}

/** Wheel delta in CSS pixels regardless of deltaMode (lines/pages). */
export function wheelPixels(delta: number, mode: number, page: number): number {
  return mode === 1 ? delta * 16 : mode === 2 ? delta * page : delta;
}

/** Ctrl+wheel / pinch zoom factor: smooth and bounded per event. */
export const wheelZoomFactor = (deltaPixels: number) => Math.exp(-Math.max(-120, Math.min(120, deltaPixels)) * 0.0025);
