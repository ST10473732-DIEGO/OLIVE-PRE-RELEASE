import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import spec from "../src/features/draw/drawing_schema.json";
import conformance from "../src/features/draw/conformance_v1.json";
import protocolSpec from "../src/features/draw/protocol_v1.json";
import {
  DrawingFormatError, LIMITS, checkOperation, effectiveBackground, operationBytes, operationId, quantize, replayStart,
  validateCanvas, validateOperation, validateRecord, type DrawRecord, type Operation, type StrokeOp,
} from "../src/features/draw/model";
import { DrawReplica, compareKeys } from "../src/features/draw/replica";
import {
  MAX_ZOOM, MIN_ZOOM, centre, clampPan, cssToDoc, docToCss, docToDevice, fit, panBy, rescale, stepZoom, wheelZoomFactor, zoomAt,
  type View,
} from "../src/features/draw/viewport";
import { StrokeCapture } from "../src/features/draw/capture";
import { DrawSession, type DrawBridge, type Page } from "../src/features/draw/session";
import { Scratch, drawOperation, rasterize, replay, tracePath, type Surface, type Target } from "../src/features/draw/render";
import { brushSize, saveLine, sizeFromSlider, sliderFromSize } from "../src/features/draw/drawModel";
import { base64, fromBase64, imageOperation, placement, sha256 } from "../src/features/draw/assets";
import { drawSchemas, exportFileName, imageInfo, operationSchema } from "../electron/draw-contracts";
import { fileActionSchema } from "../electron/file-actions";
import { drawNoteRoute, featureById, features, spaceOf, spaces } from "../src/navigation/features";

const stroke = (points: number[], extra: Partial<StrokeOp> = {}): StrokeOp =>
  ({ type: "stroke", id: operationId(), tool: "pen", color: "#000000", width: 4, opacity: 1, pressure: false, points, ...extra });

const DID = "11111111-1111-4111-8111-111111111111";
const ME = "aaaaaaaa-0000-4000-8000-000000000001";
const PEER = "bbbbbbbb-0000-4000-8000-000000000002";
const AT = "2026-09-30T10:00:00.000Z";
const record = (device: string, lamport: number, kind: DrawRecord["kind"], body: object, id = operationId()): DrawRecord =>
  ({ record_id: id, drawing_id: DID, device, lamport, kind, at: AT, body: (kind === "op" ? { ...body, id } : body) as Record<string, unknown> });
const create = record(ME, 1, "create", { width: 400, height: 300, background: "#ffffff", title: "Shared", created_at: AT });

describe("OLIVE DrawNote navigation", () => {
  it("is one space with Notes and Draw views; Notes routes are unchanged", () => {
    const drawnote = spaces.find((s) => s.id === "drawnote")!;
    expect(drawnote.label).toBe("OLIVE DrawNote");
    expect(drawnote.routes).toEqual(["notes", "draw"]);
    expect(spaces.some((s) => s.label === "OLIVE Notes")).toBe(false);
    expect(spaceOf("notes").id).toBe("drawnote");
    expect(spaceOf("draw").id).toBe("drawnote");
    expect(featureById("notes")!.view).toBe("Notes");
    expect(featureById("draw")!.view).toBe("Draw");
    expect(featureById("draw")!.label).toBe("OLIVE Draw");
    expect(new Set(features.map((f) => f.label)).size).toBe(features.length);
  });
  it("routes Chat requests: explicit sections win, otherwise the remembered one", () => {
    expect(drawNoteRoute("draw", "notes")).toBe("draw");
    expect(drawNoteRoute("notes", "draw")).toBe("notes");
    expect(drawNoteRoute("", "draw")).toBe("draw");
    expect(drawNoteRoute(undefined, undefined)).toBe("notes");
    expect(drawNoteRoute("studio", "calendar")).toBe("notes");   // Never an unrelated route.
  });
});

describe("Draw document model", () => {
  it("shares its definitions with the backend", () => {
    for (const name of ["drawing_schema.json", "protocol_v1.json", "conformance_v1.json"]) {
      const python = JSON.parse(readFileSync(new URL(`../../olive/draw/${name}`, import.meta.url), "utf8"));
      const renderer = JSON.parse(readFileSync(new URL(`../src/features/draw/${name}`, import.meta.url), "utf8"));
      expect(python, name).toEqual(renderer);
    }
    expect(spec.schema_version).toBe(2);
    expect(protocolSpec.protocol).toBe("olive-draw/1");
    expect(protocolSpec.capability).toBe("sync.draw");
    expect(protocolSpec.frames).toEqual({ request: 15, response: 16 });
  });
  it("accepts valid operations (including images) and rejects anything else", () => {
    expect(validateOperation(stroke([1, 2, 3, 4]))).toBeTruthy();
    expect(validateOperation({ type: "erase", id: "abcdefgh", width: 20, points: [0, 0] })).toBeTruthy();
    expect(validateOperation({ type: "clear", id: "abcdefgh" })).toBeTruthy();
    expect(validateOperation({ type: "background", id: "abcdefgh", value: "transparent" })).toBeTruthy();
    expect(validateOperation({ type: "image", id: "abcdefgh", asset_id: "ab".repeat(32), x: 1, y: 2, width: 3, height: 4, opacity: 1 })).toBeTruthy();
    const bad: unknown[] = [
      null, "stroke", [], { type: "stroke" }, { type: "script", id: "abcdefgh" },
      { ...stroke([1, 1]), color: "red" }, { ...stroke([1, 1]), width: 0 }, { ...stroke([1, 1]), width: "4" },
      { ...stroke([1, 1]), opacity: 2 }, { ...stroke([1, 1]), onload: "x" }, { ...stroke([1, 1, 1]) },
      { ...stroke([1, 1, 2], { pressure: true }) }, { ...stroke([NaN, 1]) }, { ...stroke([1e9, 1]) }, { ...stroke([]) },
      { ...stroke([1, 1]), id: "<img>" }, { type: "background", id: "abcdefgh", value: "#000000" },
      { type: "image", id: "abcdefgh", asset_id: "/home/me/p.png", x: 1, y: 2, width: 3, height: 4, opacity: 1 },
      { type: "image", id: "abcdefgh", asset_id: "ab".repeat(32), x: 1, y: 2, width: 0, height: 4, opacity: 1 },
      { type: "image", id: "abcdefgh", asset_id: "ab".repeat(32), x: 1, y: 2, width: 3, height: 4, opacity: 1, src: "https://x" },
    ];
    for (const value of bad) expect(() => validateOperation(value), JSON.stringify(value)).toThrow(DrawingFormatError);
  });
  it("validates replicated records strictly", () => {
    expect(validateRecord(create)).toBeTruthy();
    const op = record(ME, 2, "op", stroke([1, 1]));
    expect(validateRecord(op)).toBeTruthy();
    for (const value of [
      { ...op, extra: 1 }, { ...op, record_id: "short" }, { ...op, lamport: 0 }, { ...op, lamport: 1.5 },
      { ...op, device: "not-a-uuid" }, { ...op, at: "yesterday" }, { ...op, kind: "script" },
      { ...op, body: { ...op.body, id: operationId() } },
      record(ME, 3, "visibility", { target: "x", hidden: true }), record(ME, 3, "meta", { field: "owner", value: "me" }),
      record(ME, 3, "meta", { field: "title", value: "a\u0007b" }), record(ME, 3, "meta", { field: "trashed", value: "yes" }),
      record(ME, 1, "create", { width: 100000, height: 10, background: "#ffffff", title: "x", created_at: AT }),
    ]) expect(() => validateRecord(value), JSON.stringify(value).slice(0, 80)).toThrow(DrawingFormatError);
  });
  it("validates canvas sizes against the memory limits", () => {
    expect(validateCanvas(1920, 1080)).toBeNull();
    expect(validateCanvas(8192, 4096)).toBeNull();
    expect(validateCanvas(8192, 8192)).toMatch(/Canvas too large/);
    expect(validateCanvas(100000, 100000)).toMatch(/Canvas too large/);
    expect(validateCanvas(10, 10)).toMatch(/at least 16/);
    expect(validateCanvas(100.5, 100)).toMatch(/whole pixels/);
  });
  it("refuses edits past the limits instead of truncating", () => {
    const big = stroke(Array.from({ length: LIMITS.max_points * 3 }, (_, i) => i % 3 === 2 ? 0.123456789 : (i * 1234.56789123) % 1900), { pressure: true });
    expect(operationBytes(big)).toBeGreaterThan(LIMITS.max_operation_bytes);
    expect(checkOperation(big, 0)).toMatch(/too long/);
    expect(checkOperation(stroke([1, 1]), LIMITS.max_operations)).toMatch(/20,000 edits/);
    expect(checkOperation(stroke([1, 1]), 0)).toBeNull();
  });
  it("replays after the last Clear and takes the latest background", () => {
    const ops: Operation[] = [stroke([1, 1]), { type: "clear", id: "clear0001" }, stroke([2, 2]), { type: "background", id: "back00001", value: "transparent" }];
    expect(replayStart(ops)).toBe(2);
    expect(effectiveBackground(ops, "#ffffff")).toBe("transparent");
    expect(effectiveBackground(ops.slice(0, 3), "#ffffff")).toBe("#ffffff");
    expect(quantize(10.123456)).toBe(10.12);
    expect(operationId()).toMatch(/^[0-9a-f]{32}$/);
  });
});

describe("Draw replica (same rules as the backend and a future phone engine)", () => {
  const shuffled = (items: readonly unknown[], seed: number): unknown[] => {
    const out = [...items];
    let state = seed;
    for (let i = out.length - 1; i > 0; i--) {
      state = (state * 1103515245 + 12345) % 2147483648;
      const j = state % (i + 1);
      [out[i], out[j]] = [out[j], out[i]];
    }
    return out;
  };
  it("matches the shared conformance fixture in any arrival order", () => {
    for (const scenario of conformance.scenarios) {
      for (let seed = 1; seed <= 12; seed++) {
        const records: readonly unknown[] = scenario.records;
        const replica = new DrawReplica(scenario.records[0].drawing_id);
        for (const r of shuffled(records, seed)) replica.apply(r);
        for (const r of records) expect(replica.apply(r).changed).toBe(false);   // Duplicates do nothing.
        const expectation = scenario.expect;
        expect(replica.order, scenario.name).toEqual(expectation.order);
        expect(replica.visible.map((op) => op.id), scenario.name).toEqual(expectation.visible);
        expect([replica.title, replica.trashed, effectiveBackground(replica.visible, replica.create!.background)], scenario.name)
          .toEqual([expectation.title, expectation.trashed, expectation.background]);
        expect([replica.create!.width, replica.create!.height]).toEqual([expectation.width, expectation.height]);
      }
    }
  });
  it("orders by Lamport clock, then device, then id — never by arrival", () => {
    expect(compareKeys([2, ME, "a"], [3, ME, "a"])).toBeLessThan(0);
    expect(compareKeys([3, PEER, "a"], [3, ME, "z"])).toBeGreaterThan(0);
    expect(compareKeys([3, ME, "b"], [3, ME, "a"])).toBeGreaterThan(0);
    const replica = new DrawReplica(DID);
    replica.apply(create);
    const late = record(PEER, 2, "op", stroke([1, 1]));
    const early = record(ME, 3, "op", stroke([2, 2]));
    expect(replica.apply(early).appended).toBe(true);
    const result = replica.apply(late);
    expect(result.changed && !result.appended).toBe(true);   // Inserted below: the view must replay.
    expect(replica.visible.map((op) => op.id)).toEqual([late.record_id, early.record_id]);
  });
});

function fakeBackend(device = ME) {
  const records: DrawRecord[] = [];
  const undo: string[] = [], redo: string[] = [];
  let clock = 0;
  const add = (r: DrawRecord) => { records.push(r); clock = Math.max(clock, r.lamport); return r; };
  add(create);
  const replica = () => { const x = new DrawReplica(DID); records.forEach((r) => x.apply(r)); return x; };
  const drawing = { drawing_id: DID, title: "Shared", created_at: AT, updated_at: AT, width: 400, height: 300, background: "#ffffff" as const,
    schema_version: 1, revision: 1, op_count: 0, bytes: 0, trashed: false, trashed_at: "", status: "ok", thumbnail_revision: null };
  const page = (after: number, size = 1000): Page => {
    const out = records.slice(after, after + size);
    return { drawing: { ...drawing, revision: records.length }, records: out, cursor: after + out.length, more: after + out.length < records.length,
      history: { undo: undo.length, redo: redo.length }, missing_assets: [], device };
  };
  const step = (from: string[], to: string[], hidden: boolean) => {
    while (from.length) {
      const target = from.pop()!;
      if (replica().isHidden(target) === hidden) continue;
      const r = add(record(device, clock + 1, "visibility", { target, hidden }));
      to.push(target);
      return { record: r, history: { undo: undo.length, redo: redo.length } };
    }
    return { record: null, history: { undo: undo.length, redo: redo.length } };
  };
  const api: DrawBridge = {
    open: async () => page(0, 2),
    since: async (_id, after) => page(after, 2),
    append: vi.fn(async (_id: string, op: Operation) => {
      const existing = records.find((r) => r.record_id === op.id);
      const r = existing ?? add({ record_id: op.id, drawing_id: DID, device, lamport: clock + 1, kind: "op", at: AT, body: { ...op } });
      if (!existing) { undo.push(op.id); redo.length = 0; }
      return { record: r, cursor: records.length, history: { undo: undo.length, redo: redo.length }, drawing: { ...drawing, revision: records.length } };
    }),
    undo: async () => step(undo, redo, true),
    redo: async () => step(redo, undo, false),
  };
  return { api, records, add, remote: (op: Operation) => add(record(PEER, clock + 1, "op", op, op.id)) };
}

describe("draw session: autosave, live merge and local-origin undo", () => {
  it("shows a stroke at once, confirms it, and survives reload", async () => {
    const backend = fakeBackend();
    const session = await DrawSession.load(DID, backend.api);
    const a = stroke([1, 1, 5, 5]);
    expect(session.edit(a)).toBeNull();
    expect(session.visible.map((op) => op.id)).toEqual([a.id]);     // Pending, drawn immediately.
    expect(session.saveState).toBe("saving");
    const version = session.version;
    await session.flush();
    expect(session.saveState).toBe("saved");
    expect(session.version).toBe(version);                            // Confirmed at the end: no replay.
    const reopened = await DrawSession.load(DID, backend.api);
    expect(reopened.visible.map((op) => op.id)).toEqual([a.id]);
  });
  it("merges remote edits live and undoes only this device's edits", async () => {
    const backend = fakeBackend();
    const session = await DrawSession.load(DID, backend.api);
    const red = stroke([1, 1], { color: "#e53935" });
    session.edit(red);
    await session.flush();
    const blue = stroke([2, 2], { color: "#1e63e9" });
    backend.remote(blue);                                            // Arrives from the phone.
    await session.pull();
    const green = stroke([3, 3], { color: "#43a047" });
    session.edit(green);
    await session.flush();
    expect(session.visible.map((op) => op.id)).toEqual([red.id, blue.id, green.id]);
    session.undo();
    await session.flush();
    expect(session.visible.map((op) => op.id)).toEqual([red.id, blue.id]);   // Blue (remote) is untouched.
    expect(session.canRedo).toBe(true);
    const purple = stroke([4, 4], { color: "#8e24aa" });
    backend.remote(purple);
    await session.pull();
    session.redo();
    await session.flush();
    expect(session.visible.map((op) => op.id)).toEqual([red.id, blue.id, green.id, purple.id]);
    session.undo();
    session.undo();
    await session.flush();
    expect(session.visible.map((op) => op.id)).toEqual([blue.id, purple.id]);
    session.undo();
    await session.flush();
    expect(session.canUndo).toBe(false);
  });
  it("keeps a remote edit that arrives while a local stroke is still being saved", async () => {
    const backend = fakeBackend();
    let release!: () => void;
    const append = backend.api.append;
    backend.api.append = vi.fn(async (id: string, op: Operation) => { await new Promise<void>((r) => { release = r; }); return append(id, op); });
    const session = await DrawSession.load(DID, backend.api);
    const mine = stroke([1, 1]);
    session.edit(mine);
    const theirs = stroke([2, 2]);
    backend.remote(theirs);
    await session.pull();
    expect(session.visible.map((op) => op.id)).toEqual([theirs.id, mine.id]);   // Pending local stroke stays on top.
    await new Promise((r) => setTimeout(r, 0));
    release();
    await session.flush();
    expect(session.visible.map((op) => op.id)).toEqual([theirs.id, mine.id]);
    expect(new Set(session.replica.order).size).toBe(2);
  });
  it("retries a failed save with the same operation id and never duplicates it", async () => {
    vi.useFakeTimers();
    try {
      const backend = fakeBackend();
      let fail = 1;
      const append = backend.api.append;
      backend.api.append = vi.fn(async (id: string, op: Operation) => {
        if (fail-- > 0) throw new Error("Runtime busy");
        return append(id, op);
      });
      const session = await DrawSession.load(DID, backend.api);
      const a = stroke([1, 1]);
      session.edit(a);
      await vi.advanceTimersByTimeAsync(1);
      expect(session.saveState).toBe("error");
      expect(saveLine(session.saveState, session.error, true).tone).toBe("error");
      await vi.advanceTimersByTimeAsync(400);
      expect(session.saveState).toBe("saved");
      const ids = (backend.api.append as ReturnType<typeof vi.fn>).mock.calls.map((c) => c[1].id);
      expect(ids).toEqual([a.id, a.id]);
      expect(backend.records.filter((r) => r.record_id === a.id)).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });
  it("drops an edit the backend can never accept and says so", async () => {
    const backend = fakeBackend();
    backend.api.append = vi.fn(async () => { throw new Error("Could not save drawing: it reached its size limit. Start a new drawing or clear this one."); });
    const session = await DrawSession.load(DID, backend.api);
    session.edit(stroke([1, 1]));
    await session.flush().catch(() => undefined);
    expect(session.saveState).toBe("error");
    expect(session.error).toMatch(/size limit/);
    expect(session.visible).toEqual([]);
  });
  it("is read-only when trashed (on any device)", async () => {
    const backend = fakeBackend();
    backend.add(record(PEER, 5, "meta", { field: "trashed", value: true }));
    const session = await DrawSession.load(DID, backend.api);
    expect(session.readOnly).toBe(true);
    expect(session.edit(stroke([1, 1]))).toMatch(/Recently Deleted/);
  });
  it("refuses a drawing made by a newer OLIVE", async () => {
    const backend = fakeBackend();
    const open = backend.api.open;
    backend.api.open = async (id) => { const page = await open(id); return { ...page, drawing: { ...page.drawing, schema_version: 3 } }; };
    await expect(DrawSession.load(DID, backend.api)).rejects.toThrow("unsupported");
  });
});

describe("imported images", () => {
  it("places images at natural size when they fit, else scaled down with margins, never upscaled", () => {
    expect(placement(400, 200, 1920, 1080)).toEqual({ x: 760, y: 440, width: 400, height: 200 });
    const big = placement(4000, 3000, 1920, 1080);
    expect(big.height).toBe(972);
    expect(big.width).toBe(1296);
    expect(big.width / big.height).toBeCloseTo(4 / 3, 2);
    expect(big.x).toBe(312);
    const tall = placement(500, 5000, 1920, 1080);
    expect(tall.height).toBeLessThanOrEqual(1080 * 0.9);
    expect(placement(10, 10, 16, 16)).toEqual({ x: 3, y: 3, width: 10, height: 10 });
  });
  it("identifies assets by the SHA-256 of their bytes", async () => {
    const bytes = new TextEncoder().encode("olive");
    expect(await sha256(bytes)).toBe("fa6598317163f260c9f3bb0959f80974868eb5ff3f6bf80a092f54e042071aa2");
    expect(fromBase64(base64(bytes))).toEqual(bytes);
    const op = imageOperation("ab".repeat(32), { x: 1, y: 2, width: 3, height: 4 });
    expect(validateOperation(op)).toEqual(op);
  });
  it("renders an image in operation order and skips one that has not arrived", () => {
    const surface = fakeSurface(100, 100);
    const target: Target = { ctx: surface.ctx as never, k: 2, ox: 0, oy: 0, width: 100, height: 100 };
    const image = imageOperation("cd".repeat(32), { x: 5, y: 6, width: 20, height: 10 });
    drawOperation(target, image, new Scratch(), () => null);
    expect(surface.ctx.log.some((l) => l.startsWith("drawImage"))).toBe(false);
    drawOperation(target, { ...image, opacity: 0.5 }, new Scratch(), () => ({}) as CanvasImageSource);
    expect(surface.ctx.log).toContain("drawImage(0.5,5,6,20,10)");
  });
});

describe("zoom, pan and display scale", () => {
  const base = (zoom: number, dpr: number): View => ({ zoom, dpr, ox: 37, oy: -12 });
  it("maps the same document point at every zoom and devicePixelRatio", () => {
    for (const zoom of [0.25, 0.5, 1, 2, 8])
      for (const dpr of [1, 1.25, 1.5, 2]) {
        const view = base(zoom, dpr);
        const doc = { x: 812.25, y: 390.5 };
        const css = docToCss(view, doc);
        const back = cssToDoc(view, css);
        expect(back.x).toBeCloseTo(doc.x, 9);
        expect(back.y).toBeCloseTo(doc.y, 9);
        const device = docToDevice(view, doc);
        expect(device.x).toBeCloseTo(css.x * dpr, 9);
      }
  });
  it("zooms around the pointer and keeps offsets on the device-pixel grid", () => {
    for (const dpr of [1, 1.25, 1.5, 2]) {
      const view = { zoom: 1, dpr, ox: 100, oy: 50 };
      const anchor = { x: 333, y: 222 };
      const before = cssToDoc(view, anchor);
      const next = zoomAt(view, 2, anchor);
      const after = cssToDoc(next, anchor);
      expect(Number.isInteger(next.ox) && Number.isInteger(next.oy)).toBe(true);
      expect(Math.abs(after.x - before.x)).toBeLessThan(1 / (2 * dpr) + 1e-9);   // At most half a device pixel of drift.
      expect(Math.abs(after.y - before.y)).toBeLessThan(1 / (2 * dpr) + 1e-9);
    }
    expect(zoomAt({ zoom: 1, dpr: 1, ox: 0, oy: 0 }, 1000, { x: 0, y: 0 }).zoom).toBe(MAX_ZOOM);
    expect(zoomAt({ zoom: 1, dpr: 1, ox: 0, oy: 0 }, 0.0001, { x: 0, y: 0 }).zoom).toBe(MIN_ZOOM);
    expect(stepZoom(1, 1)).toBe(1.25);
    expect(stepZoom(1, -1)).toBe(0.75);
    expect(stepZoom(16, 1)).toBe(16);
    expect(wheelZoomFactor(-100)).toBeGreaterThan(1);
    expect(wheelZoomFactor(100000)).toBeGreaterThan(0.7);   // Bounded per event.
  });
  it("draws at the intended document point after zooming in and panning", () => {
    const view0 = fit({ width: 1920, height: 1080 }, { width: 1000, height: 700 }, 1.25);
    const zoomed = zoomAt(view0, 2, { x: 500, y: 350 });
    const panned = panBy(zoomed, -120, 64);
    const target = { x: 1500, y: 300 };
    const css = docToCss(panned, target);
    const hit = cssToDoc(panned, css);
    expect(hit.x).toBeCloseTo(1500, 6);
    expect(hit.y).toBeCloseTo(300, 6);
    // Panning moved the page by exactly the pointer delta.
    const before = docToCss(zoomed, target);
    expect(css.x - before.x).toBeCloseTo(-120, 6);
    expect(css.y - before.y).toBeCloseTo(64, 6);
  });
  it("fits without stretching and keeps the page reachable", () => {
    const view = fit({ width: 1920, height: 1080 }, { width: 1000, height: 800 }, 1);
    expect(view.zoom).toBeCloseTo(952 / 1920, 6);
    const tall = fit({ width: 1080, height: 1920 }, { width: 1000, height: 800 }, 2);
    expect(tall.zoom).toBeCloseTo(752 / 1920, 6);
    expect(tall.ox).toBe(Math.round((1000 * 2 - 1080 * tall.zoom * 2) / 2));
    const far = clampPan({ zoom: 1, dpr: 1, ox: 100000, oy: -100000 }, { width: 1920, height: 1080 }, { width: 800, height: 600 });
    expect(far.ox).toBe(800 - 48);
    expect(far.oy).toBe(48 - 1080);
    expect(centre({ zoom: 1, dpr: 1, ox: 0, oy: 0 }, { width: 100, height: 100 }, { width: 300, height: 200 })).toMatchObject({ ox: 100, oy: 50 });
  });
  it("keeps the CSS layout when the display scale changes", () => {
    const view = { zoom: 1.5, dpr: 1, ox: 200, oy: 100 };
    const moved = rescale(view, 2);
    expect(moved).toEqual({ zoom: 1.5, dpr: 2, ox: 400, oy: 200 });
    const doc = cssToDoc(view, { x: 350, y: 260 });
    const same = cssToDoc(moved, { x: 350, y: 260 });
    expect(same.x).toBeCloseTo(doc.x, 9);
    expect(same.y).toBeCloseTo(doc.y, 9);
  });
});

describe("pointer capture", () => {
  const start = { pointerId: 1, pointerType: "mouse", tool: "pen" as const, minDistance: 0.5, x: 10, y: 10, pressure: 0.5 };
  it("records down, many moves and up as one stroke", () => {
    const capture = new StrokeCapture();
    expect(capture.begin(start)).toBe(true);
    for (let i = 1; i <= 50; i++) capture.move(1, [{ x: 10 + i, y: 10 + i / 2, pressure: 0.5 }]);
    const done = capture.end(1, { x: 60.004, y: 35.001, pressure: 0 })!;
    expect(done.pressure).toBe(false);          // Mouse: never fake pressure.
    expect(done.points.length).toBe(51 * 2);
    expect(done.points.slice(-2)).toEqual([60, 35]);
    expect(capture.active).toBe(false);
  });
  it("ignores a second pointer and never leaves a stuck stroke", () => {
    const capture = new StrokeCapture();
    capture.begin(start);
    expect(capture.begin({ ...start, pointerId: 2 })).toBe(false);
    expect(capture.move(2, [{ x: 500, y: 500, pressure: 0.5 }])).toBe(false);
    expect(capture.end(2)).toBeNull();
    expect(capture.active).toBe(true);
    expect(capture.cancel(2)).toBe(false);
    expect(capture.cancel(1)).toBe(true);        // pointercancel discards the partial stroke.
    expect(capture.active).toBe(false);
    expect(capture.end(1)).toBeNull();
    // Lost capture finishes with what was drawn.
    capture.begin(start);
    capture.move(1, [{ x: 20, y: 20, pressure: 0.5 }]);
    expect(capture.end(1)!.points).toEqual([10, 10, 20, 20]);
  });
  it("records pen pressure only when the hardware reports varying pressure", () => {
    const capture = new StrokeCapture();
    capture.begin({ ...start, pointerType: "pen", pressure: 0.5 });
    capture.move(1, [{ x: 11, y: 11, pressure: 0.5 }, { x: 12, y: 12, pressure: 0.5 }]);
    expect(capture.end(1)!.pressure).toBe(false);   // Constant 0.5 = no pressure support.
    capture.begin({ ...start, pointerType: "pen", pressure: 0.2 });
    capture.move(1, [{ x: 11, y: 11, pressure: 0.6 }, { x: 12, y: 12, pressure: 0 }]);
    const done = capture.end(1)!;
    expect(done.pressure).toBe(true);
    expect(done.points).toEqual([10, 10, 0.2, 11, 11, 0.6, 12, 12, 0.6]);   // A 0 sample keeps the last real value.
    capture.begin({ ...start, pointerType: "touch", pressure: 1 });
    capture.move(1, [{ x: 20, y: 20, pressure: 0.3 }]);
    expect(capture.end(1)!.pressure).toBe(false);
  });
  it("decimates by document distance and stops at the point limit", () => {
    const capture = new StrokeCapture();
    capture.begin({ ...start, minDistance: 2 });
    capture.move(1, [{ x: 10.5, y: 10, pressure: 0.5 }, { x: 11, y: 10, pressure: 0.5 }, { x: 13, y: 10, pressure: 0.5 }]);
    expect(capture.snapshot()!.points).toEqual([10, 10, 13, 10]);
    capture.move(1, [{ x: 14, y: 10, pressure: 0.5 }]);
    expect(capture.end(1)!.points).toEqual([10, 10, 13, 10, 14, 10]);   // The resting point is kept.
    capture.begin({ ...start, minDistance: 0 });
    const samples = Array.from({ length: LIMITS.max_points + 50 }, (_, i) => ({ x: i, y: 0, pressure: 0.5 }));
    capture.move(1, samples);
    expect(capture.limited).toBe(true);
    expect(capture.end(1)!.points.length).toBe(LIMITS.max_points * 2);
  });
});

class FakeContext {
  log: string[] = [];
  globalCompositeOperation = "source-over";
  globalAlpha = 1;
  lineWidth = 1;
  strokeStyle = "";
  fillStyle = "";
  lineCap = "";
  lineJoin = "";
  private stack: [string, number][] = [];
  constructor(public canvas: { width: number; height: number }) {}
  private rec(name: string, ...args: unknown[]) { this.log.push(`${name}(${args.map((a) => typeof a === "number" ? +a.toFixed(3) : typeof a === "object" ? "surface" : a).join(",")})`); }
  save() { this.stack.push([this.globalCompositeOperation, this.globalAlpha]); }
  restore() { [this.globalCompositeOperation, this.globalAlpha] = this.stack.pop()!; }
  setTransform(...a: number[]) { this.rec("setTransform", ...a); }
  beginPath() { this.rec("beginPath"); }
  moveTo(x: number, y: number) { this.rec("moveTo", x, y); }
  lineTo(x: number, y: number) { this.rec("lineTo", x, y); }
  quadraticCurveTo(...a: number[]) { this.rec("quad", ...a); }
  arc(...a: number[]) { this.rec("arc", ...a.slice(0, 3)); }
  stroke() { this.rec("stroke", this.globalCompositeOperation, this.lineWidth, this.strokeStyle); }
  fill() { this.rec("fill", this.fillStyle); }
  clearRect(...a: number[]) { this.rec("clearRect", ...a); }
  fillRect(...a: number[]) { this.rec("fillRect", this.globalCompositeOperation, this.fillStyle, ...a); }
  drawImage(...a: unknown[]) { this.rec("drawImage", this.globalAlpha, ...a.slice(1)); }
}
const fakeSurface = (width: number, height: number) => {
  const surface = { width, height, ctx: null as unknown as FakeContext, getContext: () => surface.ctx };
  surface.ctx = new FakeContext(surface);
  return surface as unknown as Surface & { ctx: FakeContext };
};

describe("renderer", () => {
  it("smooths deterministically through midpoints, ending on the last point", () => {
    const ctx = new FakeContext({ width: 10, height: 10 });
    tracePath(ctx as never, [0, 0, 10, 0, 10, 10, 0, 10], 2);
    expect(ctx.log).toEqual(["beginPath()", "moveTo(0,0)", "quad(10,0,10,5)", "quad(10,10,5,10)", "lineTo(0,10)"]);
    const again = new FakeContext({ width: 10, height: 10 });
    tracePath(again as never, [0, 0, 10, 0, 10, 10, 0, 10], 2);
    expect(again.log).toEqual(ctx.log);
  });
  it("renders strokes, translucent strokes, erase and clear on the strokes layer", () => {
    const surface = fakeSurface(200, 100);
    const target: Target = { ctx: surface.ctx as never, k: 2, ox: 10, oy: 5, width: 200, height: 100 };
    const scratch = new Scratch((w, h) => fakeSurface(w, h));
    drawOperation(target, stroke([1, 1, 20, 20], { color: "#ff0000", width: 6 }), scratch);
    expect(surface.ctx.log).toContain("setTransform(2,0,0,2,10,5)");
    expect(surface.ctx.log).toContain("stroke(source-over,6,#ff0000)");
    surface.ctx.log = [];
    drawOperation(target, stroke([1, 1, 20, 20], { opacity: 0.5 }), scratch);
    // Drawn opaque on a scratch layer, composited once at 50%.
    expect(surface.ctx.log.some((l) => l.startsWith("drawImage(0.5"))).toBe(true);
    expect(surface.ctx.log.some((l) => l.startsWith("stroke("))).toBe(false);
    surface.ctx.log = [];
    drawOperation(target, { type: "erase", id: "erase0001", width: 20, points: [0, 0, 10, 10] }, scratch);
    expect(surface.ctx.log).toContain("stroke(destination-out,20,#000000)");
    surface.ctx.log = [];
    drawOperation(target, { type: "clear", id: "clear0001" }, scratch);
    expect(surface.ctx.log).toContain("clearRect(0,0,200,100)");
  });
  it("replays pressure strokes with per-point widths", () => {
    const surface = fakeSurface(100, 100);
    const target: Target = { ctx: surface.ctx as never, k: 1, ox: 0, oy: 0, width: 100, height: 100 };
    replay(target, [stroke([0, 0, 1, 10, 0, 0.5, 20, 0, 0], { pressure: true, width: 10 })], 0, 1, new Scratch());
    expect(surface.ctx.log.filter((l) => l.startsWith("stroke(")).map((l) => l.split(",")[1])).toEqual(["6", "2"]);
  });
  it("exports at document size; JPEG composites transparency onto white, PNG keeps it", () => {
    const ops = [stroke([1, 1, 50, 50])];
    const png = rasterize(ops, 0, 1, { width: 1920, height: 1080, background: "transparent", format: "png", create: fakeSurface }) as unknown as { width: number; height: number; ctx: FakeContext };
    expect([png.width, png.height]).toEqual([1920, 1080]);
    expect(png.ctx.log.some((l) => l.startsWith("fillRect"))).toBe(false);
    const jpeg = rasterize(ops, 0, 1, { width: 1920, height: 1080, background: "transparent", format: "jpeg", create: fakeSurface }) as unknown as { ctx: FakeContext };
    expect(jpeg.ctx.log).toContain("fillRect(destination-over,#ffffff,0,0,1920,1080)");
    const white = rasterize(ops, 0, 1, { width: 800, height: 600, background: "#ffffff", format: "png", create: fakeSurface }) as unknown as { ctx: FakeContext };
    expect(white.ctx.log).toContain("fillRect(destination-over,#ffffff,0,0,800,600)");
    const thumb = rasterize(ops, 0, 1, { width: 1920, height: 1080, background: "#ffffff", format: "png", scale: 320 / 1920, create: fakeSurface }) as unknown as { width: number; height: number };
    expect([thumb.width, thumb.height]).toEqual([320, 180]);
  });
});

describe("toolbar rules", () => {
  it("maps the logarithmic size slider within bounds", () => {
    expect(sizeFromSlider(0)).toBe(0.5);
    expect(sizeFromSlider(1000)).toBe(256);
    for (const size of [1, 2, 4, 8, 16, 32, 64, 128]) expect(Math.abs(sizeFromSlider(sliderFromSize(size)) - size)).toBeLessThanOrEqual(1);
    expect(brushSize(9999)).toBe(256);
    expect(brushSize(-3)).toBe(0.5);
    expect(brushSize(Number.NaN)).toBe(8);
  });
  it("describes save state plainly", () => {
    expect(saveLine("saved", "", true).label).toBe("Saved locally");
    expect(saveLine("saving", "", true).label).toBe("Saving…");
    expect(saveLine("error", "Could not save drawing: it reached its size limit.", true).label).toBe("Could not save drawing");
  });
});

describe("Draw contracts", () => {
  it("types every bridge method and rejects malformed operations", () => {
    const id = "11111111-1111-4111-8111-111111111111";
    expect(drawSchemas["draw.open"].safeParse({ drawing_id: id }).success).toBe(true);
    expect(drawSchemas["draw.open"].safeParse({ drawing_id: "My drawing" }).success).toBe(false);
    expect(drawSchemas["draw.list"].safeParse({ view: "drawings", sql: "DROP" }).success).toBe(false);
    expect(drawSchemas["draw.create"].safeParse({ width: 100000 }).success).toBe(false);
    expect(drawSchemas["draw.append"].safeParse({ drawing_id: id, op: stroke([1, 1]) }).success).toBe(true);
    expect(drawSchemas["draw.append"].safeParse({ drawing_id: id, op: { ...stroke([1, 1]), id: "short123" } }).success).toBe(false);
    expect(drawSchemas["draw.since"].safeParse({ drawing_id: id, after: -1 }).success).toBe(false);
    expect(drawSchemas["draw.asset_upload"].safeParse({ asset_id: "x", index: 0, count: 1, data: "AA==" }).success).toBe(false);
    expect(drawSchemas["draw.asset_upload"].safeParse({ asset_id: "a".repeat(64), index: 0, count: 1, data: "<script>" }).success).toBe(false);
    expect("draw.save" in drawSchemas).toBe(false);
    expect(operationSchema.safeParse({ ...stroke([1, 1]), href: "javascript:alert(1)" }).success).toBe(false);
    expect(operationSchema.safeParse({ type: "image", id: "abcdefgh", src: "file:///etc/passwd" }).success).toBe(false);
    expect(operationSchema.safeParse(imageOperation("ef".repeat(32), { x: 1, y: 1, width: 5, height: 5 })).success).toBe(true);
    expect(Object.keys(drawSchemas).some((name) => /sql|exec|eval|path|file|export/.test(name))).toBe(false);
  });
  it("exports only through the main-process dialog with checked bytes", () => {
    const id = "11111111-1111-4111-8111-111111111111";
    const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52, 0, 0, 7, 0x80, 0, 0, 4, 0x38]);
    expect(imageInfo(png)).toEqual({ mime: "image/png", width: 1920, height: 1080 });
    const jpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 4, 0, 0, 0xff, 0xc0, 0, 11, 8, 0x04, 0x38, 0x07, 0x80, 1, 1, 0x11, 0]);
    expect(imageInfo(jpeg)).toEqual({ mime: "image/jpeg", width: 1920, height: 1080 });
    expect(imageInfo(new TextEncoder().encode("<svg onload=alert(1)>"))).toBeNull();
    expect(fileActionSchema.safeParse({ action: "draw-export", drawing_id: id, format: "png", data: png }).success).toBe(true);
    expect(fileActionSchema.safeParse({ action: "draw-export", drawing_id: id, format: "png", data: png, path: "/tmp/x.png" }).success).toBe(false);
    expect(fileActionSchema.safeParse({ action: "draw-export", drawing_id: id, format: "gif", data: png }).success).toBe(false);
    expect(fileActionSchema.safeParse({ action: "draw-export", drawing_id: id, format: "png", data: "iVBOR" }).success).toBe(false);
    expect(fileActionSchema.safeParse({ action: "draw-export", drawing_id: id, format: "png", data: new Uint8Array() }).success).toBe(false);
  });
  it("imports only through the main-process dialog", () => {
    expect(fileActionSchema.safeParse({ action: "draw-import-image", drawing_id: DID }).success).toBe(true);
    expect(fileActionSchema.safeParse({ action: "draw-import-image", drawing_id: DID, path: "/home/me/a.png" }).success).toBe(false);
    const progressive = new Uint8Array([0xff, 0xd8, 0xff, 0xff, 0xc2, 0, 11, 8, 0, 21, 0, 33, 1, 1, 0x11, 0]);
    expect(imageInfo(progressive)).toEqual({ mime: "image/jpeg", width: 33, height: 21 });
  });
  it("suggests safe file names from titles", () => {
    expect(exportFileName("My Drawing", "png")).toBe("My Drawing.png");
    expect(exportFileName("../../etc/passwd", "jpeg")).toBe("etcpasswd.jpg");
    expect(exportFileName("a\\b:c*d?\"e<f>g|h\u0007", "png")).toBe("abcdefgh.png");
    expect(exportFileName("   ", "png")).toBe("OLIVE drawing.png");
    expect(exportFileName(undefined, "jpeg")).toBe("OLIVE drawing.jpg");
  });
});
