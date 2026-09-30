import { z } from "zod";
import spec from "../src/features/draw/drawing_schema.json";
// OLIVE Draw renderer contracts. Typed operations only: no SQL, paths or eval.
// Mirrors olive/draw/contracts.py; operations are validated again in Python.
const L = spec.limits;
const id = z.string().uuid();
const text = (max: number) => z.string().max(max).refine((v) => !v.includes("\0"));
const count = z.number().int().min(0).max(2 ** 31 - 1);
const empty = z.object({}).strict();
const reach = L.max_canvas * 3;
const coordinate = z.number().finite().min(-reach).max(reach);
const opId = z.string().regex(/^[a-z0-9]{8,32}$/);
const width = z.number().finite().min(L.min_width).max(L.max_width);
const points = z.array(z.number().finite().min(-reach).max(reach)).min(2).max(L.max_points * 3);

export const operationSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("stroke"), id: opId, tool: z.enum(spec.tools as ["pen"]),
    color: z.string().regex(/^#[0-9a-f]{6}$/), width, opacity: z.number().finite().min(0.01).max(1),
    pressure: z.boolean(), points,
  }).strict(),
  z.object({ type: z.literal("erase"), id: opId, width, points: z.array(coordinate).min(2).max(L.max_points * 2) }).strict(),
  z.object({ type: z.literal("clear"), id: opId }).strict(),
  z.object({ type: z.literal("background"), id: opId, value: z.enum(spec.backgrounds as ["#ffffff", "transparent"]) }).strict(),
  z.object({
    type: z.literal("image"), id: opId, asset_id: z.string().regex(/^[0-9a-f]{64}$/),
    x: coordinate, y: coordinate, width: z.number().finite().min(1).max(reach), height: z.number().finite().min(1).max(reach),
    opacity: z.number().finite().min(0.01).max(1),
  }).strict(),
]);
const recordOpId = z.string().regex(/^[0-9a-f]{32}$/);
const asset = z.string().regex(/^[0-9a-f]{64}$/);

export const drawSchemas = {
  "draw.status": empty,
  "draw.list": z.object({ view: z.enum(["drawings", "trash"]).optional() }).strict(),
  "draw.get": z.object({ drawing_id: id }).strict(),
  "draw.create": z.object({
    title: text(400).optional(),
    width: z.number().int().min(L.min_canvas).max(L.max_canvas).optional(),
    height: z.number().int().min(L.min_canvas).max(L.max_canvas).optional(),
    background: z.enum(spec.backgrounds as ["#ffffff", "transparent"]).optional(),
  }).strict(),
  "draw.open": z.object({ drawing_id: id }).strict(),
  "draw.since": z.object({ drawing_id: id, after: count }).strict(),
  // A completed edit; its id (128 random bits) is also its record id, so a retry is recognised.
  "draw.append": z.object({ drawing_id: id, op: operationSchema.refine((op) => recordOpId.safeParse(op.id).success) }).strict(),
  "draw.undo": z.object({ drawing_id: id }).strict(),
  "draw.redo": z.object({ drawing_id: id }).strict(),
  "draw.rename": z.object({ drawing_id: id, title: text(400) }).strict(),
  "draw.duplicate": z.object({ drawing_id: id }).strict(),
  "draw.trash": z.object({ drawing_id: id }).strict(),
  "draw.restore": z.object({ drawing_id: id }).strict(),
  "draw.purge": z.object({ drawing_id: id, confirmed: z.boolean() }).strict(),
  "draw.thumbnail_put": z.object({ drawing_id: id, revision: count, image: z.string().max(130_000).regex(/^[A-Za-z0-9+/]*={0,2}$/) }).strict(),
  "draw.thumbnail_get": z.object({ drawing_id: id }).strict(),
  "draw.asset_info": z.object({ asset_id: asset }).strict(),
  "draw.asset_upload": z.object({
    asset_id: asset, index: z.number().int().min(0).max(1000), count: z.number().int().min(1).max(1000),
    data: z.string().max(600_004).regex(/^[A-Za-z0-9+/]*={0,2}$/),
  }).strict(),
  "draw.asset_chunk": z.object({ asset_id: asset, index: z.number().int().min(0).max(1000) }).strict(),
};

/** What the main process accepts from a chosen image file before any decoder runs. */
export const IMPORT_LIMITS = { bytes: L.max_import_bytes, side: L.max_import_side, pixels: L.max_import_pixels };

/** Export bytes are produced by the renderer at document resolution; the main
 *  process chooses the destination and checks the bytes before writing. */
export const MAX_EXPORT_BYTES = 256 * 1024 * 1024;

/** Every JPEG start-of-frame marker (C4/C8/CC are other segment types). */
const JPEG_SOF = new Set([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf]);

/** Image type and pixel size from PNG/JPEG headers (no decoding). */
export function imageInfo(data: Uint8Array): { mime: "image/png" | "image/jpeg"; width: number; height: number } | null {
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const png = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  if (data.length >= 24 && png.every((b, i) => data[i] === b) && String.fromCharCode(...data.subarray(12, 16)) === "IHDR")
    return { mime: "image/png", width: view.getUint32(16), height: view.getUint32(20) };
  if (data.length >= 4 && data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff) {
    let index = 2;
    while (index + 9 < data.length) {
      if (data[index] !== 0xff) return null;
      const marker = data[index + 1];
      if (marker === 0xff) { index += 1; continue; }   // Fill byte.
      if (marker === 0xd8 || marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) { index += 2; continue; }
      const length = view.getUint16(index + 2);
      if (JPEG_SOF.has(marker))
        return { mime: "image/jpeg", height: view.getUint16(index + 5), width: view.getUint16(index + 7) };
      if (length < 2) return null;
      index += 2 + length;
    }
  }
  return null;
}

/** A safe default file name from a drawing title: no separators or control characters. */
export function exportFileName(title: string | undefined, format: "png" | "jpeg"): string {
  const base = Array.from(title || "")
    .filter((c) => c.charCodeAt(0) >= 32 && !'\\/:*?"<>|'.includes(c))
    .join("")
    .replace(/^[.\s]+/, "")
    .trim()
    .slice(0, 80) || "OLIVE drawing";
  return `${base}.${format === "png" ? "png" : "jpg"}`;
}
