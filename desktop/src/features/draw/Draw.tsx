import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArchiveRestore, ChevronDown, ChevronLeft, Copy, Download, Eraser, ImagePlus, Maximize, Minus, MoreHorizontal, Palette,
  PenLine, Plus, Redo2, Trash2, Undo2, X,
} from "lucide-react";
import * as Dialog from "@radix-ui/react-dialog";
import { call, type WireEvent } from "../../services/api";
import type { RecordTarget } from "../../services/handoff";
import { whenLabel } from "../../services/when";
import { EmptyState, Main, Rail, Seg, WorkspacePage } from "../../components/WorkspacePage";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { MenuButton } from "../../components/MenuButton";
import { CanvasView, type Brush, type CanvasHandle, type Tool } from "./CanvasView";
import {
  CANVAS_PRESETS, DrawingFormatError, LIMITS, operationId, validateCanvas,
  type Background, type DrawingSummary,
} from "./model";
import { encode, rasterize, underlayBackground, type Context2D, type Surface } from "./render";
import { DrawSession, type DrawBridge, type SaveState } from "./session";
import { AssetCache, imageOperation, normalizeImage, uploadAsset, type AssetBridge } from "./assets";
import { brushSize, saveLine, sizeFromSlider, sliderFromSize, SIZE_PRESETS, SWATCHES } from "./drawModel";
import "./draw.css";

const SELECTED_KEY = "olive.draw.selected";
const BRUSH_KEY = "olive.draw.brush";

const bridge: DrawBridge = {
  open: (drawing_id) => call("draw.open", { drawing_id }),
  since: (drawing_id, after) => call("draw.since", { drawing_id, after }),
  append: (drawing_id, op) => call("draw.append", { drawing_id, op }),
  undo: (drawing_id) => call("draw.undo", { drawing_id }),
  redo: (drawing_id) => call("draw.redo", { drawing_id }),
  thumbnail: (drawing_id, revision, image) => call("draw.thumbnail_put", { drawing_id, revision, image }),
};
const assetBridge: AssetBridge = {
  info: (asset_id) => call("draw.asset_info", { asset_id }),
  upload: (asset_id, index, count, data) => call("draw.asset_upload", { asset_id, index, count, data }),
  chunk: (asset_id, index) => call("draw.asset_chunk", { asset_id, index }),
};
const plainError = (error: unknown, fallback: string) =>
  error instanceof Error && error.message ? error.message.replace(/^Error invoking remote method '[^']+': Error: /, "") : fallback;

function stored<T>(key: string, fallback: T, check: (value: unknown) => value is T): T {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "null");
    return check(value) ? value : fallback;
  } catch { return fallback; }
}
function remember(key: string, value: unknown) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch { /* per-device convenience only */ }
}
const isBrush = (value: unknown): value is Omit<Brush, "tool"> => {
  const v = value as Brush;
  return !!v && typeof v === "object" && /^#[0-9a-f]{6}$/.test(v.color) && typeof v.size === "number" && typeof v.opacity === "number";
};

function base64(bytes: Uint8Array): string {
  let text = "";
  for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(text);
}

/** A thumbnail surface with the page background composited beneath the ink. */
async function thumbnailData(surface: Surface, background: Background): Promise<string | null> {
  underlayBackground(surface.getContext("2d") as Context2D, background, surface.width, surface.height);
  let bytes = await encode(surface, "png");
  if (bytes.length > LIMITS.thumbnail_max_bytes) {
    underlayBackground(surface.getContext("2d") as Context2D, "#ffffff", surface.width, surface.height);
    bytes = await encode(surface, "jpeg", 0.8);
  }
  return bytes.length <= LIMITS.thumbnail_max_bytes ? base64(bytes) : null;
}

type LoadError = { title: string; message: string };

export default function Draw({ report, target, visible }: { report: (error: unknown) => void; target?: RecordTarget; visible: boolean }) {
  const [view, setView] = useState<"drawings" | "trash">("drawings");
  const [drawings, setDrawings] = useState<DrawingSummary[]>([]);
  const [counts, setCounts] = useState({ drawings: 0, trash: 0 });
  const [loaded, setLoaded] = useState(false);
  const [unavailable, setUnavailable] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(() => stored(SELECTED_KEY, null, (v): v is string | null => typeof v === "string"));
  const [session, setSession] = useState<DrawSession | null>(null);
  const [loadError, setLoadError] = useState<LoadError | null>(null);
  const [, setTick] = useState(0);
  const [tool, setTool] = useState<Tool>("pen");
  const [brush, setBrush] = useState(() => stored(BRUSH_KEY, { color: "#000000", size: 8, opacity: 1 }, isBrush));
  const [zoom, setZoom] = useState(1);
  const [notice, setNotice] = useState("");
  const [thumbs, setThumbs] = useState<Record<string, { revision: number; url: string }>>({});
  const [purge, setPurge] = useState<DrawingSummary | null>(null);
  const [custom, setCustom] = useState(false);
  const [narrowList, setNarrowList] = useState(true);
  const [title, setTitle] = useState("");
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const canvasRef = useRef<CanvasHandle>(null);
  const pointerOut = useRef<HTMLSpanElement>(null);
  const sessionRef = useRef<DrawSession | null>(null);
  const thumbTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const thumbDone = useRef<Record<string, number>>({});

  const refresh = useCallback(async () => {
    try {
      const status = await call<{ available: boolean; message: string }>("draw.status", {});
      if (!status.available) { setUnavailable(status.message || "Drawing storage unavailable."); setLoaded(true); return; }
      setUnavailable("");
      const list = await call<{ drawings: DrawingSummary[]; counts: { drawings: number; trash: number } }>("draw.list", { view });
      setDrawings(list.drawings);
      setCounts(list.counts);
      setLoaded(true);
    } catch (error) {
      setLoaded(true);
      report(error);
    }
  }, [view, report]);

  useEffect(() => { void refresh(); }, [refresh]);

  // Imported images, decoded once per window and shared by every drawing here.
  const [cache] = useState(() => new AssetCache(assetBridge));
  useEffect(() => cache.subscribe(() => sessionRef.current?.invalidate()), [cache]);
  useEffect(() => () => cache.close(), [cache]);

  // Records from another window or another device, and list changes.
  useEffect(() => window.olive.subscribe((event: WireEvent) => {
    const data = (event.data || {}) as Record<string, unknown>;
    const open = sessionRef.current;
    if (event.topic === "draw.records" && open && data.drawing_id === open.id) void open.pull().catch(report);
    if (event.topic === "draw.asset" && typeof data.asset_id === "string") cache.announce(data.asset_id);
    if (event.topic === "draw.changed") {
      void refresh();
      if (open && data.drawing_id === open.id) {
        if (data.reason === "purged") {
          setSelectedId(null);
          remember(SELECTED_KEY, null);
          setNotice("This drawing was permanently deleted.");
        } else {
          void open.pull().then(() => setTitle(open.drawing.title)).catch(report);
        }
      }
    }
  }), [refresh, report, cache]);

  // Open the selected drawing; flush the previous one first.
  useEffect(() => {
    let live = true;
    const previous = sessionRef.current;
    sessionRef.current = null;
    setSession(null);
    setLoadError(null);
    void (async () => {
      if (previous) await previous.close().catch((error) => report(error));
      if (!selectedId) return;
      try {
        const next = await DrawSession.load(selectedId, bridge);
        if (!live) { await next.close(); return; }
        sessionRef.current = next;
        setSession(next);
        setTitle(next.drawing.title);
      } catch (error) {
        if (!live) return;
        const message = error instanceof Error ? error.message : "";
        if (/no longer exists/.test(message)) { setSelectedId(null); remember(SELECTED_KEY, null); return; }
        setLoadError(error instanceof DrawingFormatError && error.message === "unsupported" || /format unsupported/i.test(message)
          ? { title: "Drawing format unsupported", message: "This drawing was made by a newer OLIVE. It was left untouched." }
          : { title: "Could not load drawing", message: /Could not load/.test(message) ? message : "The stored drawing could not be read. It was left untouched for recovery." });
      }
    })();
    return () => { live = false; };
  }, [selectedId, report]);

  useEffect(() => () => { void sessionRef.current?.close(); }, []);

  // Re-render on save-state changes (coalesced by the session; never per pointer move).
  useEffect(() => {
    if (!session) return;
    let last = `${session.saveState}|${session.version}|${session.canUndo}|${session.canRedo}|${session.readOnly}`;
    return session.subscribe(() => {
      const next = `${session.saveState}|${session.version}|${session.canUndo}|${session.canRedo}|${session.readOnly}`;
      if (next !== last) { last = next; setTick((n) => n + 1); }
      if (session.saveState === "saved") scheduleThumbnail(session);
    });
  }, [session]);

  // Chat or another page asked to open a drawing.
  useEffect(() => {
    if (!target?.id) return;
    setView("drawings");
    setSelectedId(target.id);
    remember(SELECTED_KEY, target.id);
    setNarrowList(false);
  }, [target]);

  useEffect(() => { remember(BRUSH_KEY, brush); }, [brush]);

  const scheduleThumbnail = (s: DrawSession) => {
    clearTimeout(thumbTimer.current);
    thumbTimer.current = setTimeout(() => void makeThumbnail(s), 1200);
  };

  const makeThumbnail = async (s: DrawSession) => {
    const revision = s.savedRevision;
    if (revision === null || thumbDone.current[s.id] === revision || sessionRef.current !== s) return;
    try {
      const side = LIMITS.thumbnail_max_side;
      if ((await cache.require(s.imageIds)).length) return;   // Not while an image is still arriving.
      const ops = s.visible;
      const surface = canvasRef.current?.thumbnail(side) ?? rasterize(ops, s.replayStart, ops.length, {
        width: s.drawing.width, height: s.drawing.height, background: "transparent", format: "png",
        scale: Math.min(1, side / Math.max(s.drawing.width, s.drawing.height)), images: (id) => cache.get(id),
      });
      const image = await thumbnailData(surface, s.background);
      if (!image) return;
      await bridge.thumbnail!(s.id, revision, image);
      thumbDone.current[s.id] = revision;
      const mime = image.startsWith("/9j/") ? "image/jpeg" : "image/png";
      setThumbs((current) => ({ ...current, [s.id]: { revision, url: `data:${mime};base64,${image}` } }));
    } catch { /* Thumbnails are a cache; the drawing itself is already saved. */ }
  };

  // Fetch cached thumbnails the list does not have yet (a few at a time).
  useEffect(() => {
    let live = true;
    const missing = drawings.filter((d) => d.thumbnail_revision !== null && thumbs[d.drawing_id]?.revision !== d.thumbnail_revision).slice(0, 24);
    void (async () => {
      for (const d of missing) {
        try {
          const got = await call<{ revision: number | null; mime: string; image: string }>("draw.thumbnail_get", { drawing_id: d.drawing_id });
          if (!live) return;
          if (got.revision !== null && /^image\/(png|jpeg)$/.test(got.mime))
            setThumbs((current) => ({ ...current, [d.drawing_id]: { revision: got.revision!, url: `data:${got.mime};base64,${got.image}` } }));
        } catch { /* The card shows no preview. */ }
      }
    })();
    return () => { live = false; };
  }, [drawings]);

  const select = (id: string) => {
    setSelectedId(id);
    remember(SELECTED_KEY, id);
    setNarrowList(false);
    setNotice("");
  };

  const create = useCallback(async (options: { width?: number; height?: number; background?: Background } = {}) => {
    try {
      await sessionRef.current?.flush();
      const drawing = await call<DrawingSummary>("draw.create", options);
      setView("drawings");
      await refresh();
      select(drawing.drawing_id);
      return drawing;
    } catch (error) {
      report(error);
      return null;
    }
  }, [refresh, report]);

  const act = async (action: () => Promise<unknown>, after?: () => void) => {
    try {
      await sessionRef.current?.flush();
      await action();
      after?.();
      await refresh();
    } catch (error) {
      report(error);
    }
  };

  const edit = (op: Parameters<DrawSession["edit"]>[0], done?: string) => {
    const s = sessionRef.current;
    if (!s) return;
    const refused = s.edit(op);
    setNotice(refused ?? done ?? "");
  };

  const exportImage = async (format: "png" | "jpeg", quality = 0.92) => {
    const s = sessionRef.current;
    if (!s || exporting) return;
    setExporting(true);
    setNotice(format === "png" ? "Exporting PNG…" : "Exporting JPEG…");
    try {
      await new Promise((resolve) => requestAnimationFrame(resolve));
      if ((await cache.require(s.imageIds)).length) {
        setNotice("Could not export image: an imported image has not arrived on this device yet. Try again in a moment.");
        return;
      }
      const ops = s.visible;
      const surface = rasterize(ops, s.replayStart, ops.length, {
        width: s.drawing.width, height: s.drawing.height, background: s.background, format, quality, images: (id) => cache.get(id),
      });
      const data = await encode(surface, format, quality);
      const result = await window.olive.fileAction({ action: "draw-export", drawing_id: s.id, format, name: s.drawing.title, data }) as
        { exported: boolean; name: string } | null;
      setNotice(result ? `Exported ${result.name} (${s.drawing.width} × ${s.drawing.height}).${format === "jpeg" && s.background === "transparent" ? " Transparent areas became white: JPEG has no transparency." : ""}` : "");
    } catch (error) {
      const message = error instanceof Error ? error.message.replace(/^Error invoking remote method '[^']+': Error: /, "") : "";
      setNotice(message.startsWith("Could not export image") ? message : "Could not export image.");
    } finally {
      setExporting(false);
    }
  };

  const importImage = async () => {
    const s = sessionRef.current;
    if (!s || importing) return;
    setImporting(true);
    try {
      const picked = await window.olive.fileAction({ action: "draw-import-image", drawing_id: s.id }) as
        { name: string; mime: "image/png" | "image/jpeg"; width: number; height: number; data: Uint8Array<ArrayBuffer> } | null;
      if (!picked) return;
      setNotice("Importing image…");
      const { bytes, place } = await normalizeImage(picked.data, picked.mime, s.drawing.width, s.drawing.height);
      const assetId = await uploadAsset(assetBridge, bytes);
      await cache.load(assetId);
      const refused = s.edit(imageOperation(assetId, place));
      setNotice(refused ?? `Imported ${picked.name} (${place.width} × ${place.height}). The drawing keeps its own copy; the original file is not needed any more.`);
    } catch (error) {
      const message = plainError(error, "");
      setNotice(message.startsWith("Could not import image") ? message : "Could not import image.");
    } finally {
      setImporting(false);
    }
  };

  const setSize = (size: number) => setBrush((b) => ({ ...b, size: brushSize(size) }));

  // Draw shortcuts, only while Draw is showing and never while typing in a field.
  useEffect(() => {
    if (!visible) return;
    const listener = (event: KeyboardEvent) => {
      const t = event.target;
      if (t instanceof HTMLElement && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName) || t.closest('[role="dialog"], [role="alertdialog"], [role="menu"]'))) return;
      const s = sessionRef.current;
      const mod = event.ctrlKey || event.metaKey;
      const key = event.key.toLowerCase();
      if (mod && !event.altKey) {
        if (key === "n" && !event.shiftKey) { event.preventDefault(); void create(); return; }
        if (!s) return;
        if (key === "z" && !event.shiftKey) { event.preventDefault(); s.undo(); return; }
        if ((key === "z" && event.shiftKey) || key === "y") { event.preventDefault(); s.redo(); return; }
        if (key === "=" || key === "+") { event.preventDefault(); canvasRef.current?.zoomIn(); return; }
        if (key === "-" || key === "_") { event.preventDefault(); canvasRef.current?.zoomOut(); return; }
        if (key === "0") { event.preventDefault(); canvasRef.current?.fit(); return; }
        if (key === "1") { event.preventDefault(); canvasRef.current?.actualSize(); return; }
        return;
      }
      if (event.altKey || !s) return;
      if (key === "p" || key === "b") { setTool("pen"); event.preventDefault(); }
      else if (key === "e") { setTool("erase"); event.preventDefault(); }
      else if (key === "[") { setSize(brush.size / 1.25); event.preventDefault(); }
      else if (key === "]") { setSize(brush.size * 1.25); event.preventDefault(); }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [visible, create, brush.size]);

  const s = session;
  const selected = s ? drawings.find((d) => d.drawing_id === s.id) ?? s.drawing : null;
  const trashed = Boolean(s?.drawing.trashed);
  const line = saveLine(s?.saveState ?? ("saved" as SaveState), s?.error ?? "", Boolean(s));

  const rename = (value: string) => {
    if (!s) return;
    const next = value.trim() || "Untitled drawing";
    if (next === s.drawing.title) { setTitle(next); return; }
    void call<DrawingSummary>("draw.rename", { drawing_id: s.id, title: next })
      .then((renamed) => { setTitle(renamed.title); void s.pull(); void refresh(); })
      .catch(report);
  };

  const list = (
    <Rail className="draw-rail" label="Drawings list" wide
      title={view === "trash" ? "Recently Deleted" : "Drawings"}
      actions={view === "drawings" ? (
        <button className="icon-button quiet" aria-label="New drawing" title="New drawing (Ctrl+N)" onClick={() => void create()}>
          <Plus size={16} aria-hidden="true" />
        </button>
      ) : undefined}
      foot={
        <Seg label="Drawings view" value={view} onChange={(value) => setView(value)}
          options={[
            { value: "drawings", label: "Drawings", count: counts.drawings },
            { value: "trash", label: "Recently Deleted", count: counts.trash, icon: <Trash2 size={14} aria-hidden="true" /> },
          ]} />
      }>
      <ul className="draw-list" aria-label={view === "trash" ? "Recently deleted drawings" : "Drawings"}>
        {drawings.map((d) => (
          <li key={d.drawing_id}>
            <button className={`draw-card ${d.drawing_id === selectedId ? "selected" : ""}`}
              aria-current={d.drawing_id === selectedId ? "true" : undefined} onClick={() => select(d.drawing_id)}>
              <span className={`draw-thumb ${d.background === "transparent" ? "transparent" : ""}`} aria-hidden="true">
                {thumbs[d.drawing_id] ? <img src={thumbs[d.drawing_id].url} alt="" draggable={false} /> : <Palette size={18} />}
              </span>
              <span className="draw-card-text">
                <span className="draw-card-title">{d.title}</span>
                <span className="draw-card-meta">
                  {d.width} × {d.height} · {view === "trash" ? `Deleted ${whenLabel(d.trashed_at)}` : whenLabel(d.updated_at)}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
      {loaded && !drawings.length && view === "trash" && <p className="muted small draw-empty-line">Nothing recently deleted.</p>}
    </Rail>
  );

  const toolbar = s && selected ? (
    <>
      <div className="draw-titlebar" role="toolbar" aria-label="Drawing actions">
        <button className="icon-button quiet draw-back" aria-label="Back to drawings list" onClick={() => setNarrowList(true)}>
          <ChevronLeft size={16} aria-hidden="true" />
        </button>
        <input className="draw-title-input" aria-label="Drawing title" value={title} maxLength={LIMITS.max_title_chars}
          disabled={trashed} onChange={(event) => setTitle(event.target.value)}
          onBlur={(event) => rename(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") { event.preventDefault(); (event.target as HTMLInputElement).blur(); }
            if (event.key === "Escape") { setTitle(s.drawing.title); (event.target as HTMLInputElement).blur(); }
          }} />
        <span className="draw-titlebar-spacer" />
        {trashed ? (
          <>
            <button onClick={() => void act(async () => { await call<DrawingSummary>("draw.restore", { drawing_id: s.id }); await s.pull(); })}>
              <ArchiveRestore size={15} aria-hidden="true" /> Restore
            </button>
            <button className="danger" onClick={() => setPurge(s.drawing)}>
              <Trash2 size={15} aria-hidden="true" /> Delete permanently
            </button>
          </>
        ) : (
          <>
            <button className="draw-import" title="Import a PNG or JPEG into this drawing (OLIVE keeps its own copy)"
              disabled={importing} onClick={() => void importImage()}>
              <ImagePlus size={15} aria-hidden="true" /> {importing ? "Importing…" : "Import image"}
            </button>
            <MenuButton label="Export" title="Export a flattened image (the editable drawing stays in OLIVE)" className="draw-export" align="end"
              items={[
                { id: "png", label: "Export PNG…", detail: "Lossless; keeps transparency", icon: <Download size={14} />, disabled: exporting, onSelect: () => void exportImage("png") },
                { id: "jpeg", label: "Export JPEG…", detail: "High quality (92%)", icon: <Download size={14} />, disabled: exporting, onSelect: () => void exportImage("jpeg", 0.92) },
                { id: "jpeg-small", label: "Export smaller JPEG…", detail: "Quality 80%", icon: <Download size={14} />, disabled: exporting, onSelect: () => void exportImage("jpeg", 0.8) },
              ]}>
              <Download size={15} aria-hidden="true" /> Export <ChevronDown size={13} aria-hidden="true" />
            </MenuButton>
            <MenuButton label="More drawing actions" title="More" className="icon-button quiet" align="end"
              items={[
                { id: "white", label: "White background", current: s.background === "#ffffff", onSelect: () => s.background !== "#ffffff" && edit({ type: "background", id: operationId(), value: "#ffffff" }, "Background is white. Undo brings back the previous one.") },
                { id: "transparent", label: "Transparent background", current: s.background === "transparent", onSelect: () => s.background !== "transparent" && edit({ type: "background", id: operationId(), value: "transparent" }, "Background is transparent. PNG exports keep it; JPEG exports use white.") },
                { id: "clear", label: "Clear canvas", detail: "Undo brings it back", disabled: !s.visible.length, onSelect: () => edit({ type: "clear", id: operationId() }, "Canvas cleared. Undo (Ctrl+Z) brings it back.") },
                { id: "duplicate", label: "Duplicate drawing", icon: <Copy size={14} />, onSelect: () => void act(async () => { const copy = await call<DrawingSummary>("draw.duplicate", { drawing_id: s.id }); select(copy.drawing_id); }) },
                { id: "trash", label: "Move to Recently Deleted", icon: <Trash2 size={14} />, onSelect: () => void act(() => call("draw.trash", { drawing_id: s.id }), () => { setSelectedId(null); remember(SELECTED_KEY, null); setNotice("Moved to Recently Deleted. You can restore it from there."); }) },
              ]}>
              <MoreHorizontal size={16} aria-hidden="true" />
            </MenuButton>
          </>
        )}
      </div>
      {!trashed && (
        <div className="draw-toolbar" role="toolbar" aria-label="Drawing tools">
          <div className="draw-group" role="group" aria-label="Tool">
            <button className="icon-button" aria-label="Pen" title="Pen (P)" aria-pressed={tool === "pen"} onClick={() => setTool("pen")}>
              <PenLine size={16} aria-hidden="true" />
            </button>
            <button className="icon-button" aria-label="Eraser" title="Eraser (E)" aria-pressed={tool === "erase"} onClick={() => setTool("erase")}>
              <Eraser size={16} aria-hidden="true" />
            </button>
          </div>
          <div className="draw-group" role="group" aria-label="Colour">
            <label className="draw-color" title="Pen colour">
              <input type="color" aria-label="Pen colour" value={brush.color}
                onChange={(event) => { setBrush((b) => ({ ...b, color: event.target.value.toLowerCase() })); setTool("pen"); }} />
            </label>
            <div className="draw-swatches">
              {SWATCHES.map((swatch) => (
                <button key={swatch.color} className="draw-swatch" style={{ background: swatch.color }}
                  aria-label={swatch.name} title={swatch.name} aria-pressed={brush.color === swatch.color}
                  onClick={() => { setBrush((b) => ({ ...b, color: swatch.color })); setTool("pen"); }} />
              ))}
            </div>
          </div>
          <div className="draw-group draw-size" role="group" aria-label="Size">
            <span className="draw-label" aria-hidden="true">Size</span>
            <input type="range" min={0} max={1000} step={1} aria-label="Pen size" aria-valuetext={`${brush.size} pixels`}
              value={sliderFromSize(brush.size)} onChange={(event) => setSize(sizeFromSlider(Number(event.target.value)))} />
            <input className="draw-number" type="number" min={LIMITS.min_width} max={LIMITS.max_width} step={1} aria-label="Pen size in pixels"
              value={brush.size} onChange={(event) => { const v = Number(event.target.value); if (Number.isFinite(v) && v > 0) setSize(v); }} />
            <MenuButton label="Pen size presets" title="Size presets" className="icon-button quiet"
              items={SIZE_PRESETS.map((size) => ({ id: String(size), label: `${size} px`, current: brush.size === size, onSelect: () => setSize(size) }))}>
              <ChevronDown size={14} aria-hidden="true" />
            </MenuButton>
          </div>
          <div className="draw-group draw-opacity" role="group" aria-label="Opacity">
            <span className="draw-label" aria-hidden="true">Opacity</span>
            <input type="range" min={5} max={100} step={1} aria-label="Pen opacity" aria-valuetext={`${Math.round(brush.opacity * 100)} percent`}
              value={Math.round(brush.opacity * 100)} onChange={(event) => setBrush((b) => ({ ...b, opacity: Number(event.target.value) / 100 }))} />
            <span className="draw-value">{Math.round(brush.opacity * 100)}%</span>
          </div>
          <span className="draw-toolbar-spacer" />
          <div className="draw-group" role="group" aria-label="History">
            <button className="icon-button" aria-label="Undo" title="Undo your last edit on this device (Ctrl+Z)" disabled={!s.canUndo} onClick={() => s.undo()}>
              <Undo2 size={16} aria-hidden="true" />
            </button>
            <button className="icon-button" aria-label="Redo" title="Redo (Ctrl+Shift+Z)" disabled={!s.canRedo} onClick={() => s.redo()}>
              <Redo2 size={16} aria-hidden="true" />
            </button>
          </div>
          <div className="draw-group" role="group" aria-label="Zoom">
            <button className="icon-button" aria-label="Zoom out" title="Zoom out (Ctrl+−)" onClick={() => canvasRef.current?.zoomOut()}>
              <Minus size={16} aria-hidden="true" />
            </button>
            <button className="draw-zoom" aria-label={`Zoom ${Math.round(zoom * 100)}%. Show at 100%`} title="Actual size (Ctrl+1)" onClick={() => canvasRef.current?.actualSize()}>
              {Math.round(zoom * 100)}%
            </button>
            <button className="icon-button" aria-label="Zoom in" title="Zoom in (Ctrl+=)" onClick={() => canvasRef.current?.zoomIn()}>
              <Plus size={16} aria-hidden="true" />
            </button>
            <button className="icon-button" aria-label="Fit to window" title="Fit (Ctrl+0)" onClick={() => canvasRef.current?.fit()}>
              <Maximize size={15} aria-hidden="true" />
            </button>
          </div>
        </div>
      )}
      <CanvasView ref={canvasRef} session={s} visible={visible}
        brush={{ ...brush, tool }}
        onView={(info) => setZoom(info.zoom)}
        onNotice={setNotice}
        pointerOut={pointerOut}
        images={(id) => cache.get(id)}
        label={`Drawing “${s.drawing.title}”, ${s.drawing.width} by ${s.drawing.height} pixels, ${s.visible.length} edit${s.visible.length === 1 ? "" : "s"}, ${s.background === "transparent" ? "transparent" : "white"} background.${trashed ? " In Recently Deleted; restore it to edit." : ""}`} />
      <div className="draw-statusbar" aria-label="Drawing status">
        <span>{s.drawing.width} × {s.drawing.height} px</span>
        <span>{Math.round(zoom * 100)}%</span>
        <span>{s.background === "transparent" ? "Transparent" : "White"} background</span>
        <span ref={pointerOut} className="draw-pointer" aria-hidden="true" />
        <span className="draw-status-spacer" />
        <span className="draw-save" data-tone={line.tone} role="status">{line.label}</span>
      </div>
    </>
  ) : null;

  return (
    <WorkspacePage
      layout="fill"
      className={`draw-page ${unavailable ? "" : narrowList ? "narrow-list" : "narrow-editor"}`}
      icon={<Palette size={18} />}
      title="OLIVE Draw"
      description="Freehand drawings stored on this device. Export a PNG or JPEG copy whenever you like."
      actions={
        <>
          <button className="primary" onClick={() => void create()} disabled={Boolean(unavailable)} title="New 1920 × 1080 drawing (Ctrl+N)">
            <Plus size={16} aria-hidden="true" /> New drawing
          </button>
          <MenuButton label="New drawing with another canvas size" title="Other canvas sizes" className="icon-button draw-new-sizes" align="end"
            items={[
              ...CANVAS_PRESETS.map((preset) => ({ id: preset.id, label: preset.label, onSelect: () => void create({ width: preset.width, height: preset.height }) })),
              { id: "transparent", label: "1920 × 1080, transparent", onSelect: () => void create({ background: "transparent" }) },
              { id: "custom", label: "Custom size…", onSelect: () => setCustom(true) },
            ]}>
            <ChevronDown size={15} aria-hidden="true" />
          </MenuButton>
        </>
      }
      rail={unavailable ? undefined : list}
    >
      <Main pad={false} scroll={false} className="draw-main" label="Drawing editor">
        {notice && (
          <p className="draw-notice" role="status">
            {notice}
            <button className="icon-button quiet" aria-label="Dismiss" onClick={() => setNotice("")}><X size={14} aria-hidden="true" /></button>
          </p>
        )}
        {unavailable ? (
          <EmptyState icon={<Palette size={20} />} title="Drawing storage unavailable">
            {unavailable} OLIVE Notes is not affected.
          </EmptyState>
        ) : loadError ? (
          <EmptyState icon={<Palette size={20} />} title={loadError.title}>{loadError.message}</EmptyState>
        ) : toolbar ? toolbar : selectedId ? (
          <EmptyState icon={<Palette size={20} />} title="Opening drawing…" />
        ) : loaded && !counts.drawings && view === "drawings" ? (
          <EmptyState icon={<Palette size={20} />} title="No drawings yet"
            actions={<button className="primary" onClick={() => void create()}><Plus size={16} aria-hidden="true" /> New drawing</button>}>
            Draw with a mouse, pen or touch. Drawings save as you draw and stay on this device.
          </EmptyState>
        ) : (
          <EmptyState icon={<Palette size={20} />} title={view === "trash" ? "Select a deleted drawing" : "Select a drawing"}>
            {view === "trash" ? "Restore it, or delete it permanently." : "Or press Ctrl+N for a new one."}
          </EmptyState>
        )}
      </Main>
      <CustomSizeDialog open={custom} onOpenChange={setCustom} create={(width, height, background) => create({ width, height, background })} />
      <ConfirmDialog open={Boolean(purge)} onOpenChange={(open) => { if (!open) setPurge(null); }}
        title="Delete permanently?" confirmLabel="Delete permanently"
        onConfirm={async () => {
          if (!purge) return;
          await call("draw.purge", { drawing_id: purge.drawing_id, confirmed: true });
          if (selectedId === purge.drawing_id) { setSelectedId(null); remember(SELECTED_KEY, null); }
          await refresh();
        }}>
        “{purge?.title}” will be removed from this device. Exported images are not affected. This cannot be undone.
      </ConfirmDialog>
    </WorkspacePage>
  );
}

function CustomSizeDialog({ open, onOpenChange, create }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  create: (width: number, height: number, background: Background) => Promise<unknown>;
}) {
  const [width, setWidth] = useState("1920");
  const [height, setHeight] = useState("1080");
  const [background, setBackground] = useState<Background>("#ffffff");
  const [error, setError] = useState("");
  const submit = async () => {
    const w = Number(width), h = Number(height);
    const problem = validateCanvas(w, h);
    if (problem) { setError(problem); return; }
    setError("");
    await create(w, h, background);
    onOpenChange(false);
  };
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay confirm-overlay" />
        <Dialog.Content className="confirm-dialog draw-size-dialog">
          <Dialog.Title className="confirm-title">New drawing</Dialog.Title>
          <Dialog.Description className="confirm-body">Canvas size in pixels (16 to 8192 on a side).</Dialog.Description>
          <form noValidate onSubmit={(event) => { event.preventDefault(); void submit(); }}>
            <div className="draw-size-fields">
              <label>Width<input type="number" min={LIMITS.min_canvas} max={LIMITS.max_canvas} step={1} value={width} onChange={(e) => setWidth(e.target.value)} /></label>
              <span aria-hidden="true">×</span>
              <label>Height<input type="number" min={LIMITS.min_canvas} max={LIMITS.max_canvas} step={1} value={height} onChange={(e) => setHeight(e.target.value)} /></label>
            </div>
            <Seg label="Background" value={background} onChange={setBackground}
              options={[{ value: "#ffffff", label: "White" }, { value: "transparent", label: "Transparent" }]} />
            {error && <p className="confirm-error" role="alert">{error}</p>}
            <div className="confirm-actions">
              <Dialog.Close asChild><button type="button">Cancel</button></Dialog.Close>
              <button type="submit" className="primary">Create</button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
