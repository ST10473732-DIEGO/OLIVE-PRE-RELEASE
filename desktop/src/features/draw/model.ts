// OLIVE Draw document model (renderer side). A drawing is a replicated set of
// immutable records; replica.ts turns a set into the picture. Exported PNG/JPEG
// files are flattened copies and never the source of truth.
//
// Mirrors olive/draw/document.py; drawing_schema.json is shared byte-for-byte
// (a test checks both copies).
import spec from "./drawing_schema.json";

export const SCHEMA_VERSION: number = spec.schema_version;
export const LIMITS = spec.limits;
export const BACKGROUNDS = spec.backgrounds as readonly Background[];
const OPERATIONS = new Set<string>(spec.operations[String(spec.schema_version) as "2"]);

export type Background = "#ffffff" | "transparent";
export interface StrokeOp {
  type: "stroke";
  id: string;
  tool: "pen";
  color: string;
  width: number;
  opacity: number;
  /** When true, `points` is x, y, pressure triples; otherwise x, y pairs. */
  pressure: boolean;
  points: number[];
}
export interface EraseOp { type: "erase"; id: string; width: number; points: number[] }
export interface ClearOp { type: "clear"; id: string }
export interface BackgroundOp { type: "background"; id: string; value: Background }
/** An imported picture: only the SHA-256 of an OLIVE-owned asset, never bytes or a path. */
export interface ImageOp { type: "image"; id: string; asset_id: string; x: number; y: number; width: number; height: number; opacity: number }
export type Operation = StrokeOp | EraseOp | ClearOp | BackgroundOp | ImageOp;

export type RecordKind = "create" | "op" | "visibility" | "meta";
export interface DrawRecord {
  record_id: string;
  drawing_id: string;
  device: string;
  lamport: number;
  kind: RecordKind;
  at: string;
  body: Record<string, unknown>;
}

export interface DrawingSummary {
  drawing_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  width: number;
  height: number;
  background: Background;
  schema_version: number;
  revision: number;
  op_count: number;
  bytes: number;
  trashed: boolean;
  trashed_at: string;
  status: "ok" | "unsupported" | string;
  thumbnail_revision: number | null;
}

export class DrawingFormatError extends Error {}

const OP_ID = /^[a-z0-9]{8,32}$/;
const RECORD_ID = /^[0-9a-f]{32}$/;
const ASSET_ID = /^[0-9a-f]{64}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const COLOR = /^#[0-9a-f]{6}$/;
const AT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$/;

function isNumber(value: unknown, low: number, high: number): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= low && value <= high;
}

function validPoints(value: unknown, stride: number): boolean {
  if (!Array.isArray(value) || !value.length || value.length % stride || value.length / stride > LIMITS.max_points) return false;
  const reach = LIMITS.max_canvas * 3;
  for (let i = 0; i < value.length; i++) {
    const ok = stride === 3 && i % 3 === 2 ? isNumber(value[i], 0, 1) : isNumber(value[i], -reach, reach);
    if (!ok) return false;
  }
  return true;
}

const exactKeys = (value: object, keys: string[]) => {
  const own = Object.keys(value);
  return own.length === keys.length && keys.every((k) => Object.prototype.hasOwnProperty.call(value, k));
};

/** Loaded and received data is untrusted: every field is checked, nothing is coerced. */
export function validateOperation(value: unknown): Operation {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new DrawingFormatError("invalid_operation");
  const op = value as Record<string, unknown>;
  if (typeof op.type !== "string" || !OPERATIONS.has(op.type)) throw new DrawingFormatError("unsupported_operation");
  if (typeof op.id !== "string" || !OP_ID.test(op.id)) throw new DrawingFormatError("invalid_operation");
  const reach = LIMITS.max_canvas * 3;
  switch (op.type) {
    case "stroke":
      if (!exactKeys(op, ["type", "id", "tool", "color", "width", "opacity", "pressure", "points"])) break;
      if (op.tool !== "pen" || typeof op.color !== "string" || !COLOR.test(op.color) || typeof op.pressure !== "boolean") break;
      if (!isNumber(op.width, LIMITS.min_width, LIMITS.max_width) || !isNumber(op.opacity, 0.01, 1)) break;
      if (!validPoints(op.points, op.pressure ? 3 : 2)) break;
      return op as unknown as StrokeOp;
    case "erase":
      if (!exactKeys(op, ["type", "id", "width", "points"])) break;
      if (!isNumber(op.width, LIMITS.min_width, LIMITS.max_width) || !validPoints(op.points, 2)) break;
      return op as unknown as EraseOp;
    case "clear":
      if (exactKeys(op, ["type", "id"])) return op as unknown as ClearOp;
      break;
    case "background":
      if (exactKeys(op, ["type", "id", "value"]) && BACKGROUNDS.includes(op.value as Background)) return op as unknown as BackgroundOp;
      break;
    case "image":
      if (!exactKeys(op, ["type", "id", "asset_id", "x", "y", "width", "height", "opacity"])) break;
      if (typeof op.asset_id !== "string" || !ASSET_ID.test(op.asset_id)) break;
      if (!isNumber(op.x, -reach, reach) || !isNumber(op.y, -reach, reach)) break;
      if (!isNumber(op.width, 1, reach) || !isNumber(op.height, 1, reach) || !isNumber(op.opacity, 0.01, 1)) break;
      return op as unknown as ImageOp;
  }
  throw new DrawingFormatError("invalid_operation");
}

const plainTitle = (value: unknown) =>
  typeof value === "string" && value.length <= LIMITS.max_title_chars && value === value.trim()
  && Array.from(value).every((c) => c.charCodeAt(0) >= 32 && c.charCodeAt(0) !== 127);

/** A replicated record, checked the same way the backend checks it. */
export function validateRecord(value: unknown): DrawRecord {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new DrawingFormatError("invalid_record");
  const r = value as Record<string, unknown>;
  if (!exactKeys(r, ["record_id", "drawing_id", "device", "lamport", "kind", "at", "body"])) throw new DrawingFormatError("invalid_record");
  if (typeof r.record_id !== "string" || !RECORD_ID.test(r.record_id)) throw new DrawingFormatError("invalid_record");
  if (typeof r.drawing_id !== "string" || !UUID.test(r.drawing_id) || typeof r.device !== "string" || !UUID.test(r.device))
    throw new DrawingFormatError("invalid_record");
  if (!Number.isInteger(r.lamport) || (r.lamport as number) < 1 || (r.lamport as number) > 2 ** 53) throw new DrawingFormatError("invalid_record");
  if (typeof r.at !== "string" || !AT.test(r.at)) throw new DrawingFormatError("invalid_record");
  const body = r.body as Record<string, unknown>;
  if (!body || typeof body !== "object" || Array.isArray(body)) throw new DrawingFormatError("invalid_record");
  switch (r.kind) {
    case "create":
      if (!exactKeys(body, ["width", "height", "background", "title", "created_at"]) || validateCanvas(body.width as number, body.height as number)
        || !BACKGROUNDS.includes(body.background as Background) || !plainTitle(body.title)) throw new DrawingFormatError("invalid_record");
      break;
    case "op":
      validateOperation(body);
      if (body.id !== r.record_id) throw new DrawingFormatError("invalid_record");
      break;
    case "visibility":
      if (!exactKeys(body, ["target", "hidden"]) || typeof body.hidden !== "boolean" || typeof body.target !== "string" || !RECORD_ID.test(body.target))
        throw new DrawingFormatError("invalid_record");
      break;
    case "meta":
      if (!exactKeys(body, ["field", "value"])) throw new DrawingFormatError("invalid_record");
      if (!(body.field === "title" && plainTitle(body.value)) && !(body.field === "trashed" && typeof body.value === "boolean"))
        throw new DrawingFormatError("invalid_record");
      break;
    default:
      throw new DrawingFormatError("invalid_record");
  }
  return r as unknown as DrawRecord;
}

export function validateCanvas(width: number, height: number): string | null {
  if (!Number.isInteger(width) || !Number.isInteger(height)) return "Use whole pixels for the canvas size.";
  if (width < LIMITS.min_canvas || height < LIMITS.min_canvas) return `The canvas must be at least ${LIMITS.min_canvas} × ${LIMITS.min_canvas} pixels.`;
  if (width > LIMITS.max_canvas || height > LIMITS.max_canvas || width * height > LIMITS.max_canvas_pixels)
    return "Canvas too large. Drawings can be up to 8192 pixels on a side and 33.5 million pixels in total.";
  return null;
}

/** Document coordinates are stored to 1/100 px and pressure to 1/1000, so a
 *  reloaded drawing replays exactly what was drawn. */
export const quantize = (value: number) => Math.round(value * 100) / 100;
export const quantizePressure = (value: number) => Math.min(1, Math.max(0, Math.round(value * 1000) / 1000));

/** A new operation id: 128 random bits, which is also its record id. */
export function operationId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export const pointCount = (op: StrokeOp | EraseOp) => op.points.length / (op.type === "stroke" && op.pressure ? 3 : 2);

/** Serialized size as the backend counts it (compact JSON, before its envelope). */
export const operationBytes = (op: Operation) => JSON.stringify(op).length;

/** Refuse (never truncate) an edit past the per-operation limit. */
export function checkOperation(op: Operation, visibleCount: number): string | null {
  if (operationBytes(op) > LIMITS.max_operation_bytes) return "That stroke is too long to save. Draw it in shorter strokes.";
  if (visibleCount + 1 > LIMITS.max_operations) return "This drawing reached 20,000 edits. Start a new drawing or clear this one.";
  return null;
}

/** Index in `ops` after the last Clear: replay can start there. */
export function replayStart(ops: readonly Operation[]): number {
  for (let i = ops.length - 1; i >= 0; i--) if (ops[i].type === "clear") return i + 1;
  return 0;
}

/** Background in effect: the latest visible background operation, else the drawing's own. */
export function effectiveBackground(ops: readonly Operation[], initial: Background): Background {
  for (let i = ops.length - 1; i >= 0; i--) {
    const op = ops[i];
    if (op.type === "background") return op.value;
  }
  return initial;
}

export const CANVAS_PRESETS = [
  { id: "hd", label: "1920 × 1080", width: 1920, height: 1080 },
  { id: "square", label: "1080 × 1080", width: 1080, height: 1080 },
  { id: "a4", label: "A4 portrait (2480 × 3508)", width: 2480, height: 3508 },
  { id: "a4l", label: "A4 landscape (3508 × 2480)", width: 3508, height: 2480 },
  { id: "small", label: "800 × 600", width: 800, height: 600 },
] as const;
