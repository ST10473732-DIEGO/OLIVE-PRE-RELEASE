// One open note in the renderer: a Yjs replica of the backend's document.
// The backend owns the durable copy; the renderer never opens the database.
// Local edits are batched (about 30 ms) and sent as Yjs updates; "Saved" means
// the backend committed them to SQLite. Remote updates arrive as events.
import * as Y from "yjs";
import { body, fromBase64, toBase64 } from "./engine/doc";

export const LOCAL = "olive-local";
export const REMOTE = "olive-remote";

export type SaveState = "saved" | "saving" | "retrying" | "error";

export interface NoteSummary {
  note_id: string;
  title: string;
  display_title: string;
  preview: string;
  pinned: boolean;
  trashed: boolean;
  trashed_at: string;
  created_at: string;
  edited_at: string;
  text_length: number;
  status: string;
  snippet?: string;
}

interface Delivery { state: string; chunks: number; token: string }

export interface NotesBridge {
  open(noteId: string): Promise<Delivery & { note: NoteSummary }>;
  chunk(token: string, index: number): Promise<{ data: string }>;
  since(noteId: string, stateVector: string): Promise<Delivery>;
  apply(noteId: string, update: string, view: string,
        upload?: { id: string; index: number; count: number }): Promise<{ saved: boolean; note?: NoteSummary }>;
}

const PART = 450_000; // Bytes per bridge message; base64 stays far below the 1 MiB line limit.

export class NoteSession {
  readonly doc = new Y.Doc();
  readonly text: Y.Text;
  readonly undo: Y.UndoManager;
  saveState: SaveState = "saved";
  error = "";
  note: NoteSummary | null = null;
  private queue: Uint8Array[] = [];
  private running: Promise<void> | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private retries = 0;
  private closed = false;
  private listeners = new Set<() => void>();

  constructor(readonly noteId: string, private bridge: NotesBridge, readonly view: string, private delay = 30) {
    this.text = body(this.doc);
    // Undo covers this device's own typing only: remote edits are never tracked.
    this.undo = new Y.UndoManager(this.text, { trackedOrigins: new Set([LOCAL]), captureTimeout: 500 });
    this.doc.on("update", (update: Uint8Array, origin: unknown) => {
      if (origin === REMOTE || this.closed) return;
      this.queue.push(update);
      this.schedule();
    });
  }

  subscribe(listener: () => void) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify() {
    for (const listener of this.listeners) listener();
  }

  private async receive(delivery: Delivery) {
    if (delivery.chunks) {
      const parts: Uint8Array[] = [];
      for (let index = 0; index < delivery.chunks; index++)
        parts.push(fromBase64((await this.bridge.chunk(delivery.token, index)).data));
      const size = parts.reduce((sum, part) => sum + part.length, 0);
      const joined = new Uint8Array(size);
      let offset = 0;
      for (const part of parts) { joined.set(part, offset); offset += part.length; }
      return joined;
    }
    return fromBase64(delivery.state);
  }

  async load() {
    const opened = await this.bridge.open(this.noteId);
    this.note = opened.note;
    Y.applyUpdate(this.doc, await this.receive(opened), REMOTE);
    return opened.note;
  }

  /** A backend event. Our own echoes are skipped; Yjs would ignore them anyway. */
  remote(update: string, view: string) {
    if (view === this.view || this.closed) return;
    Y.applyUpdate(this.doc, fromBase64(update), REMOTE);
  }

  /** Catch up after a missed or oversized event. */
  async resync() {
    const delivery = await this.bridge.since(this.noteId, toBase64(Y.encodeStateVector(this.doc)));
    if (!this.closed) Y.applyUpdate(this.doc, await this.receive(delivery), REMOTE);
  }

  get pending() {
    return this.queue.length > 0 || this.running !== null;
  }

  private schedule(wait = this.delay) {
    if (this.saveState !== "retrying") this.saveState = "saving";
    this.notify();
    clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.flush(), wait);
  }

  /** Commit queued edits to the backend. Resolves once they are durable (or failed). */
  async flush(): Promise<void> {
    clearTimeout(this.timer);
    if (this.running) {
      await this.running;
      if (this.queue.length && this.saveState !== "retrying") return this.flush();
      return;
    }
    if (!this.queue.length) return;
    const update = this.queue.length === 1 ? this.queue[0] : Y.mergeUpdates(this.queue);
    this.queue = [];
    this.running = (async () => {
      try {
        await this.send(update);
        this.retries = 0;
        this.error = "";
        this.saveState = this.queue.length ? "saving" : "saved";
      } catch (failure) {
        // Keep the edit: it stays queued (in memory, in order) and is retried.
        this.queue.unshift(update);
        this.error = failure instanceof Error ? failure.message : "Could not save locally.";
        this.retries++;
        this.saveState = /too large|corrupted|no longer exists|permanently deleted/i.test(this.error) ? "error" : "retrying";
        if (this.saveState === "retrying" && !this.closed)
          this.schedule(Math.min(8000, 500 * 2 ** Math.min(4, this.retries - 1)));
      } finally {
        this.running = null;
        this.notify();
      }
    })();
    await this.running;
    if (this.queue.length && this.saveState === "saving") await this.flush();
  }

  private async send(update: Uint8Array) {
    if (update.length <= PART) {
      const result = await this.bridge.apply(this.noteId, toBase64(update), this.view);
      if (result.note) this.note = result.note;
      return;
    }
    const id = `${this.view.slice(0, 20)}-${Date.now().toString(36)}`;
    const count = Math.ceil(update.length / PART);
    for (let index = 0; index < count; index++) {
      const result = await this.bridge.apply(this.noteId, toBase64(update.subarray(index * PART, (index + 1) * PART)), this.view,
        { id, index, count });
      if (result.note) this.note = result.note;
    }
  }

  /** Flush, then release. Never waits for a phone: only local persistence. */
  async close() {
    await this.flush().catch(() => undefined);
    this.closed = true;
    clearTimeout(this.timer);
    this.listeners.clear();
    this.undo.destroy();
    this.doc.destroy();
  }
}
