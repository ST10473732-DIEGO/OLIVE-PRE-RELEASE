// OLIVE-owned view over a note's Yjs document. Library calls stay here and in
// the session/engine modules; UI code works with plain strings and metadata.
import * as Y from "yjs";
import spec from "./protocol_v1.json";
import { normalize, textDiff } from "./text";

export const BODY = spec.document.body;
export const META = spec.document.meta;

export interface NoteMeta {
  title: string;
  pinned: boolean;
  trashed: boolean;
  trashed_at: string;
  created_at: string;
  created_by: string;
  edited_at: string;
}

export const body = (doc: Y.Doc) => doc.getText(BODY);
export const meta = (doc: Y.Doc) => doc.getMap<unknown>(META);

/** Typed, bounded metadata. A peer can store anything in the map; ignore bad types. */
export function readMeta(doc: Y.Doc): NoteMeta {
  const m = meta(doc);
  const str = (key: string, limit = 64) => { const v = m.get(key); return typeof v === "string" ? v.slice(0, limit) : ""; };
  const title = m.get("title");
  return {
    title: typeof title === "string" ? title.trim().slice(0, 200) : "",
    pinned: m.get("pinned") === true,
    trashed: m.get("trashed") === true,
    trashed_at: str("trashed_at"),
    created_at: str("created_at"),
    created_by: str("created_by"),
    edited_at: str("edited_at") || str("created_at"),
  };
}

/** Replace the body with `next` as ONE minimal edit inside the given origin. */
export function replaceBody(doc: Y.Doc, next: string, origin: unknown): boolean {
  const text = body(doc);
  const change = textDiff(text.toString(), normalize(next));
  if (!change) return false;
  doc.transact(() => {
    if (change.remove) text.delete(change.index, change.remove);
    if (change.insert) text.insert(change.index, change.insert);
  }, origin);
  return true;
}

// Base64 without atob/btoa: the phone runs this code in a bare JavaScriptCore.
const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
const LOOKUP = new Int16Array(128).fill(-1);
for (let i = 0; i < ALPHABET.length; i++) LOOKUP[ALPHABET.charCodeAt(i)] = i;

export function toBase64(bytes: Uint8Array): string {
  const parts: string[] = [];
  let chunk = "";
  for (let i = 0; i < bytes.length; i += 3) {
    const a = bytes[i], b = bytes[i + 1], c = bytes[i + 2];
    chunk += ALPHABET[a >> 2] + ALPHABET[((a & 3) << 4) | ((b ?? 0) >> 4)] +
      (i + 1 < bytes.length ? ALPHABET[((b & 15) << 2) | ((c ?? 0) >> 6)] : "=") +
      (i + 2 < bytes.length ? ALPHABET[c & 63] : "=");
    if (chunk.length >= 8192) { parts.push(chunk); chunk = ""; }
  }
  parts.push(chunk);
  return parts.join("");
}

export function fromBase64(value: string): Uint8Array {
  if (value.length % 4 !== 0) throw new Error("invalid_base64");
  const padding = value.endsWith("==") ? 2 : value.endsWith("=") ? 1 : 0;
  const out = new Uint8Array((value.length / 4) * 3 - padding);
  let o = 0;
  for (let i = 0; i < value.length; i += 4) {
    const n = [0, 1, 2, 3].map((k) => {
      const ch = value.charCodeAt(i + k);
      if (ch === 61 && i + k >= value.length - padding) return 0; // '='
      const v = ch < 128 ? LOOKUP[ch] : -1;
      if (v < 0) throw new Error("invalid_base64");
      return v;
    });
    const triple = (n[0] << 18) | (n[1] << 12) | (n[2] << 6) | n[3];
    if (o < out.length) out[o++] = (triple >> 16) & 255;
    if (o < out.length) out[o++] = (triple >> 8) & 255;
    if (o < out.length) out[o++] = triple & 255;
  }
  return out;
}
