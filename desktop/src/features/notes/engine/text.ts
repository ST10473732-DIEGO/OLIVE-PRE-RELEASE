// Plain-text rules shared by the desktop editor and the phone engine. They
// mirror olive/notes/text.py. JS strings (and Yjs Y.Text) index by UTF-16 code
// units, so every edit boundary is kept off the middle of a surrogate pair.
import spec from "./protocol_v1.json";

export const LIMITS = spec.limits;
export const PROTOCOL = spec.protocol;
export const UNTITLED = "Untitled Note";

/** Canonical plain text: LF only, no NUL. */
export function normalize(text: string): string {
  return text.replace(/\r\n?/g, "\n").replace(/\0/g, "");
}

export function displayTitle(title: string, body: string): string {
  const explicit = (title || "").trim();
  if (explicit) return explicit.slice(0, 200);
  for (const line of (body || "").split("\n")) {
    const trimmed = line.trim();
    if (trimmed) return Array.from(trimmed).slice(0, 80).join("");
  }
  return UNTITLED;
}

export function preview(title: string, body: string, limit = 160): string {
  let lines = (body || "").split("\n").map((l) => l.trim()).filter(Boolean);
  if (!(title || "").trim() && lines.length) lines = lines.slice(1);
  return lines.join(" ").replace(/\s+/g, " ").slice(0, limit);
}

const high = (code: number) => code >= 0xd800 && code <= 0xdbff;
const low = (code: number) => code >= 0xdc00 && code <= 0xdfff;

export interface TextChange {
  index: number;
  remove: number;
  insert: string;
}

/** Minimal single replacement turning `before` into `after`, surrogate-safe. */
export function textDiff(before: string, after: string): TextChange | null {
  if (before === after) return null;
  const limit = Math.min(before.length, after.length);
  let start = 0;
  while (start < limit && before.charCodeAt(start) === after.charCodeAt(start)) start++;
  // Never split a surrogate pair: back off onto the pair's first unit.
  if (start > 0 && start < limit + 1 && high(before.charCodeAt(start - 1)) &&
      (low(before.charCodeAt(start)) || low(after.charCodeAt(start)))) start--;
  let end = 0;
  while (end < limit - start &&
         before.charCodeAt(before.length - 1 - end) === after.charCodeAt(after.length - 1 - end)) end++;
  if (end > 0) {
    const b = before.length - end, a = after.length - end;
    if ((low(before.charCodeAt(b)) && high(before.charCodeAt(b - 1)) && b - 1 >= start) ||
        (low(after.charCodeAt(a)) && high(after.charCodeAt(a - 1)) && a - 1 >= start)) end--;
  }
  return { index: start, remove: before.length - start - end, insert: after.slice(start, after.length - end) };
}

/** A Yjs text delta (retain/insert/delete ops). */
export type Delta = { retain?: number; insert?: unknown; delete?: number }[];

const insertLength = (value: unknown) => (typeof value === "string" ? value.length : 1);

/** Where `index` ends up after `delta` is applied. `after` puts it after text
 *  inserted exactly at the index (a caret behind a remote insert stays put). */
export function transformIndex(index: number, delta: Delta, after = false): number {
  let position = 0;
  let result = index;
  for (const op of delta) {
    if (op.retain !== undefined) {
      position += op.retain;
    } else if (op.insert !== undefined) {
      const size = insertLength(op.insert);
      if (position < result || (position === result && after)) result += size;
      position += size;
    } else if (op.delete !== undefined) {
      const end = position + op.delete;
      if (end <= result) result -= op.delete;
      else if (position < result) result = position;
    }
    if (position > result && op.insert === undefined) break;
  }
  return result;
}

export function utf8Length(text: string): number {
  let bytes = 0;
  for (let i = 0; i < text.length; i++) {
    const code = text.charCodeAt(i);
    if (code < 0x80) bytes += 1;
    else if (code < 0x800) bytes += 2;
    else if (high(code) && i + 1 < text.length && low(text.charCodeAt(i + 1))) { bytes += 4; i++; }
    else bytes += 3;
  }
  return bytes;
}

export function tooLarge(text: string): boolean {
  return text.length * 3 > LIMITS.max_note_text_bytes && utf8Length(text) > LIMITS.max_note_text_bytes;
}
