// Imported images for OLIVE Draw: OLIVE-owned, content-addressed (SHA-256) assets.
//
// Import: the Electron main process lets the person choose a file, checks its
// real type (PNG/JPEG by content), size and header dimensions, and hands the
// bytes to this renderer. Here, in the sandboxed renderer, Chromium decodes the
// image, applies its EXIF orientation, converts it to sRGB and re-encodes it
// (PNG for PNG sources, JPEG 95% for JPEG sources) at the size it will occupy
// on the canvas. Re-encoding drops every metadata block (EXIF, GPS, text). The
// backend checks the result again and stores it under its SHA-256.
import { LIMITS, operationId, type ImageOp } from "./model";

export interface AssetBridge {
  info: (asset_id: string) => Promise<{ asset_id: string; mime: string; width: number; height: number; size: number } | null>;
  upload: (asset_id: string, index: number, count: number, data: string) => Promise<{ stored: boolean }>;
  chunk: (asset_id: string, index: number) => Promise<{ mime: string; width: number; height: number; size: number; count: number; data: string }>;
}

export const CHUNK_BYTES = 450_000;
const MARGIN = 0.9;

export function base64(bytes: Uint8Array): string {
  let text = "";
  for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(text);
}
export function fromBase64(text: string): Uint8Array<ArrayBuffer> {
  const raw = atob(text);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export async function sha256(bytes: Uint8Array<ArrayBuffer>): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Where an imported image goes: natural size and centred when it fits, else
 *  scaled down (aspect kept) to fit the canvas with a margin. Never upscaled. */
export function placement(imageWidth: number, imageHeight: number, canvasWidth: number, canvasHeight: number) {
  let width = imageWidth, height = imageHeight;
  if (width > canvasWidth || height > canvasHeight) {
    const scale = Math.min((canvasWidth * MARGIN) / width, (canvasHeight * MARGIN) / height);
    width = Math.max(1, Math.round(width * scale));
    height = Math.max(1, Math.round(height * scale));
  }
  return { x: Math.round(((canvasWidth - width) / 2) * 100) / 100, y: Math.round(((canvasHeight - height) / 2) * 100) / 100, width, height };
}

/** Decode, orient, convert to sRGB and re-encode a chosen image (metadata-free). */
export async function normalizeImage(data: Uint8Array<ArrayBuffer>, mime: "image/png" | "image/jpeg", canvasWidth: number, canvasHeight: number) {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(new Blob([data], { type: mime }), { imageOrientation: "from-image", colorSpaceConversion: "default" });
  } catch {
    throw new Error("Could not import image: the file is not a valid PNG or JPEG image.");
  }
  try {
    const place = placement(bitmap.width, bitmap.height, canvasWidth, canvasHeight);
    if (place.width * place.height > LIMITS.max_asset_pixels || place.width > LIMITS.max_asset_side || place.height > LIMITS.max_asset_side)
      throw new Error("Could not import image: it is too large.");
    const surface = new OffscreenCanvas(place.width, place.height);
    const ctx = surface.getContext("2d", { colorSpace: "srgb" })!;
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(bitmap, 0, 0, place.width, place.height);
    const blob = await surface.convertToBlob(mime === "image/png" ? { type: "image/png" } : { type: "image/jpeg", quality: 0.95 });
    const bytes = new Uint8Array(await blob.arrayBuffer());
    if (bytes.length > LIMITS.max_asset_bytes) throw new Error("Could not import image: it is too large.");
    return { bytes, place };
  } finally {
    bitmap.close();
  }
}

/** Store normalized bytes (unless the same asset already exists) and return the id. */
export async function uploadAsset(bridge: AssetBridge, bytes: Uint8Array<ArrayBuffer>): Promise<string> {
  const id = await sha256(bytes);
  if (await bridge.info(id)) return id;       // Content-addressed: identical bytes are stored once.
  const count = Math.max(1, Math.ceil(bytes.length / CHUNK_BYTES));
  for (let index = 0; index < count; index++)
    await bridge.upload(id, index, count, base64(bytes.subarray(index * CHUNK_BYTES, (index + 1) * CHUNK_BYTES)));
  return id;
}

export function imageOperation(assetId: string, place: { x: number; y: number; width: number; height: number }): ImageOp {
  return { type: "image", id: operationId(), asset_id: assetId, x: place.x, y: place.y, width: place.width, height: place.height, opacity: 1 };
}

type Slot = { state: "loading" | "ready" | "missing" | "broken"; bitmap?: ImageBitmap; promise?: Promise<void> };

/** Decoded images for rendering. Missing assets (still arriving from another
 *  device) are retried when the backend announces them; they never render
 *  partially. */
export class AssetCache {
  private slots = new Map<string, Slot>();
  private listeners = new Set<() => void>();
  constructor(private bridge: AssetBridge) {}

  subscribe(listener: () => void) {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }
  private emit() { for (const listener of this.listeners) listener(); }

  get(id: string): ImageBitmap | null {
    const slot = this.slots.get(id);
    if (slot?.state === "ready") return slot.bitmap!;
    if (!slot) void this.load(id);
    return null;
  }

  state(id: string) { return this.slots.get(id)?.state ?? "loading"; }

  /** Ready bitmaps for every id, or the ids that are not available yet. */
  async require(ids: Iterable<string>): Promise<string[]> {
    const wanted = [...new Set(ids)];
    await Promise.all(wanted.map((id) => this.load(id)));
    return wanted.filter((id) => this.slots.get(id)?.state !== "ready");
  }

  /** The backend stored a new asset (import finished, or it arrived from a peer). */
  announce(id: string) {
    const slot = this.slots.get(id);
    if (slot && slot.state !== "ready" && slot.state !== "loading") {
      this.slots.delete(id);
      void this.load(id);
    }
  }

  load(id: string): Promise<void> {
    const existing = this.slots.get(id);
    if (existing?.promise) return existing.promise;
    if (existing && existing.state !== "loading") return Promise.resolve();
    const slot: Slot = { state: "loading" };
    this.slots.set(id, slot);
    slot.promise = (async () => {
      try {
        const first = await this.bridge.chunk(id, 0);
        const parts = [fromBase64(first.data)];
        for (let index = 1; index < first.count; index++) parts.push(fromBase64((await this.bridge.chunk(id, index)).data));
        const bytes = new Uint8Array(parts.reduce((sum, p) => sum + p.length, 0));
        let offset = 0;
        for (const part of parts) { bytes.set(part, offset); offset += part.length; }
        if (bytes.length !== first.size || (await sha256(bytes)) !== id) throw new Error("checksum");
        slot.bitmap = await createImageBitmap(new Blob([bytes], { type: first.mime }), { imageOrientation: "none" });
        slot.state = "ready";
      } catch (failure) {
        slot.state = failure instanceof Error && /not available/.test(failure.message) ? "missing" : "broken";
      } finally {
        slot.promise = undefined;
        this.emit();
      }
    })();
    return slot.promise;
  }

  close() {
    for (const slot of this.slots.values()) slot.bitmap?.close();
    this.slots.clear();
    this.listeners.clear();
  }
}
