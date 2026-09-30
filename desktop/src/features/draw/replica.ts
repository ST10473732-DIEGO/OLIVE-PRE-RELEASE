// OLIVE Draw replica: the record set of one drawing and the picture it means.
// Pure TypeScript (no DOM, no bridge), so a phone engine can run it unchanged
// in JavaScriptCore or port it and check itself against conformance_v1.json.
//
// Rules (identical to olive/draw/records.py):
//  * records are immutable and unique by record_id; applying one twice does nothing;
//  * operations are drawn in (lamport, device, record_id) order — never wall-clock;
//  * an operation is hidden iff the greatest visibility record targeting it
//    *made by the operation's own device* says so (local-origin Undo/Redo);
//  * title and trashed take the value of their greatest meta record.
import { validateOperation, validateRecord, type Background, type DrawRecord, type Operation } from "./model";

export type OrderKey = [number, string, string];
export const keyOf = (r: { lamport: number; device: string; record_id: string }): OrderKey => [r.lamport, r.device, r.record_id];
export function compareKeys(a: OrderKey, b: OrderKey): number {
  if (a[0] !== b[0]) return a[0] - b[0];
  if (a[1] !== b[1]) return a[1] < b[1] ? -1 : 1;
  return a[2] === b[2] ? 0 : a[2] < b[2] ? -1 : 1;
}

interface Entry { key: OrderKey; id: string; device: string; op: Operation }
interface Winner { key: OrderKey; hidden: boolean }

export interface ApplyResult {
  /** The visible picture changed. */
  changed: boolean;
  /** The only change was a new visible operation after every other one. */
  appended: boolean;
  /** Title/trash/size changed. */
  meta: boolean;
}

export class DrawReplica {
  readonly ids = new Set<string>();
  private entries: Entry[] = [];                    // content operations, in order
  private visibility = new Map<string, Winner>();   // target -> winner (own device only)
  private pendingVisibility = new Map<string, DrawRecord[]>();  // target not seen yet
  private titleKey: OrderKey | null = null;
  private trashKey: OrderKey | null = null;
  create: { width: number; height: number; background: Background; title: string; created_at: string } | null = null;
  title = "";
  trashed = false;
  clock = 0;
  private cache: Operation[] | null = null;

  constructor(readonly drawingId: string) {}

  /** Apply one record (idempotent, order-independent). Throws on malformed data. */
  apply(raw: unknown): ApplyResult {
    const record = validateRecord(raw);
    const none = { changed: false, appended: false, meta: false };
    if (record.drawing_id !== this.drawingId || this.ids.has(record.record_id)) return none;
    this.ids.add(record.record_id);
    this.clock = Math.max(this.clock, record.lamport);
    const key = keyOf(record);
    const body = record.body;
    switch (record.kind) {
      case "create":
        this.create = body as DrawReplica["create"] & object;
        if (!this.titleKey) this.title = this.create!.title;
        return { changed: true, appended: false, meta: true };
      case "op": {
        const op = validateOperation(body);
        const entry: Entry = { key, id: record.record_id, device: record.device, op };
        let index = this.entries.length;
        while (index > 0 && compareKeys(this.entries[index - 1].key, key) > 0) index--;
        this.entries.splice(index, 0, entry);
        for (const early of this.pendingVisibility.get(record.record_id) ?? []) this.foldVisibility(early);
        this.pendingVisibility.delete(record.record_id);
        this.cache = null;
        const hidden = this.visibility.get(record.record_id)?.hidden ?? false;
        const last = index === this.entries.length - 1;
        return { changed: !hidden, appended: !hidden && last, meta: false };
      }
      case "visibility": {
        const target = body.target as string;
        if (!this.entries.some((e) => e.id === target)) {
          const list = this.pendingVisibility.get(target) ?? [];
          list.push(record);
          this.pendingVisibility.set(target, list);
          return none;
        }
        const before = this.visibility.get(target)?.hidden ?? false;
        this.foldVisibility(record);
        const after = this.visibility.get(target)?.hidden ?? false;
        if (before !== after) this.cache = null;
        return { changed: before !== after, appended: false, meta: false };
      }
      case "meta": {
        if (body.field === "title" && (!this.titleKey || compareKeys(key, this.titleKey) > 0)) {
          this.titleKey = key;
          this.title = body.value as string;
          return { changed: false, appended: false, meta: true };
        }
        if (body.field === "trashed" && (!this.trashKey || compareKeys(key, this.trashKey) > 0)) {
          this.trashKey = key;
          this.trashed = body.value as boolean;
          return { changed: false, appended: false, meta: true };
        }
        return none;
      }
    }
    return none;
  }

  private foldVisibility(record: DrawRecord) {
    const target = record.body.target as string;
    const entry = this.entries.find((e) => e.id === target);
    if (!entry || entry.device !== record.device) return;   // Only the author's device can undo it.
    const key = keyOf(record);
    const current = this.visibility.get(target);
    if (!current || compareKeys(key, current.key) > 0) this.visibility.set(target, { key, hidden: record.body.hidden as boolean });
  }

  /** Every operation in drawing order (hidden ones included). */
  get order(): string[] { return this.entries.map((e) => e.id); }

  /** The visible operations in drawing order. */
  get visible(): Operation[] {
    if (!this.cache) this.cache = this.entries.filter((e) => !this.visibility.get(e.id)?.hidden).map((e) => e.op);
    return this.cache;
  }

  isHidden(id: string) { return this.visibility.get(id)?.hidden ?? false; }
  has(id: string) { return this.ids.has(id); }
}
