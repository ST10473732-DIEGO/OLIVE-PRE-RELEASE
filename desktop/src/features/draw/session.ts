// One open drawing in this window: a replica of its record set, this window's
// not-yet-confirmed strokes, and the save queue.
//
// A completed stroke renders at once (pending, on top) and is sent to the
// backend, which makes it a record with the next Lamport value and commits it.
// Records made elsewhere (another window, another device) arrive through
// `pull()` from this view's feed cursor and are merged by the replica rules, so
// the picture is the same everywhere. Undo/Redo are this device's own: the
// backend keeps the stacks and answers with a visibility record.
import { DrawReplica } from "./replica";
import {
  DrawingFormatError, SCHEMA_VERSION, checkOperation, effectiveBackground, replayStart,
  type Background, type DrawRecord, type DrawingSummary, type Operation,
} from "./model";

export type SaveState = "saved" | "saving" | "error";
export interface History { undo: number; redo: number }
export interface Page {
  drawing: DrawingSummary;
  records: unknown[];
  cursor: number;
  more: boolean;
  history: History;
  missing_assets: string[];
  device: string;
}
export interface DrawBridge {
  open: (drawing_id: string) => Promise<Page>;
  since: (drawing_id: string, after: number) => Promise<Page>;
  append: (drawing_id: string, op: Operation) => Promise<{ record: DrawRecord; cursor: number; history: History; drawing: DrawingSummary }>;
  undo: (drawing_id: string) => Promise<{ record: DrawRecord | null; history: History }>;
  redo: (drawing_id: string) => Promise<{ record: DrawRecord | null; history: History }>;
  thumbnail?: (drawing_id: string, revision: number, image: string) => Promise<unknown>;
}

const RETRY = [300, 1000, 3000, 8000];
/** Refusals that will never succeed on retry (the edit itself is not acceptable). */
const PERMANENT = /malformed|size limit|20,000 edits|Recently Deleted|permanently deleted|no longer exists|format unsupported/;

export class DrawSession {
  readonly id: string;
  readonly replica: DrawReplica;
  drawing: DrawingSummary;
  device = "";
  history: History = { undo: 0, redo: 0 };
  missing = new Set<string>();
  saveState: SaveState = "saved";
  error = "";
  /** Changes whenever the visible picture changes. */
  version = 0;
  private cursor = 0;
  private pending: Operation[] = [];
  private visibleCache: Operation[] | null = null;
  private queue: Promise<void> = Promise.resolve();
  private busy = 0;
  private pulling: Promise<void> | null = null;
  private pullAgain = false;
  private closed = false;
  private listeners = new Set<() => void>();

  private constructor(private bridge: DrawBridge, first: Page) {
    this.id = first.drawing.drawing_id;
    this.drawing = first.drawing;
    this.replica = new DrawReplica(this.id);
  }

  /** Load every page and validate every record before anything renders. */
  static async load(drawingId: string, bridge: DrawBridge): Promise<DrawSession> {
    let page = await bridge.open(drawingId);
    if (page.drawing.schema_version > SCHEMA_VERSION || page.drawing.status === "unsupported") throw new DrawingFormatError("unsupported");
    const session = new DrawSession(bridge, page);
    session.take(page);
    while (page.more) {
      page = await bridge.since(drawingId, page.cursor);
      session.take(page);
    }
    if (!session.replica.create) throw new DrawingFormatError("incomplete");
    session.version = 1;
    return session;
  }

  /** Merge one page of records; returns true if the picture changed (metadata
   *  such as the title is updated too, without re-rendering the canvas). */
  private take(page: Page): boolean {
    let changed = false;
    for (const raw of page.records) {
      const record = raw as DrawRecord;
      const wasPending = this.pending.findIndex((op) => op.id === record.record_id);
      const result = this.replica.apply(raw);
      if (wasPending >= 0) {
        this.pending.splice(wasPending, 1);
        this.visibleCache = null;
        // The pending copy was drawn on top; only a different final position is a change.
        if (result.changed && !(result.appended && wasPending === 0)) changed = true;
      } else if (result.changed) {
        changed = true;
      }
    }
    if (changed) this.visibleCache = null;
    this.cursor = Math.max(this.cursor, page.cursor);
    this.history = page.history;
    this.device = page.device;
    this.drawing = { ...page.drawing, title: this.replica.title || page.drawing.title, trashed: this.replica.trashed };
    this.missing = new Set(page.missing_assets);
    return changed;
  }

  // --- view model -------------------------------------------------------------
  get readOnly() { return this.replica.trashed; }
  get title() { return this.replica.title; }
  /** Visible operations in drawing order, this window's unconfirmed strokes last. */
  get visible(): Operation[] {
    if (!this.visibleCache) {
      const confirmed = this.replica.visible;
      this.visibleCache = this.pending.length ? [...confirmed, ...this.pending.filter((op) => !this.replica.has(op.id))] : confirmed;
    }
    return this.visibleCache;
  }
  get replayStart() { return replayStart(this.visible); }
  get background(): Background { return effectiveBackground(this.visible, this.replica.create?.background ?? this.drawing.background); }
  get canUndo() { return !this.readOnly && this.history.undo > 0; }
  get canRedo() { return !this.readOnly && this.history.redo > 0; }
  get imageIds(): string[] { return this.visible.flatMap((op) => (op.type === "image" ? [op.asset_id] : [])); }
  get dirty() { return this.busy > 0 || this.pending.length > 0; }
  /** The backend revision the current picture corresponds to (for thumbnails). */
  get savedRevision() { return this.saveState === "saved" && !this.dirty ? this.drawing.revision : null; }

  subscribe(listener: () => void) {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }
  private emit() { for (const listener of this.listeners) listener(); }
  /** Something outside the record set changed how the picture renders (an image arrived). */
  invalidate() { this.bump(); this.emit(); }
  private bump() { this.version += 1; this.visibleCache = null; }

  // --- edits ------------------------------------------------------------------
  /** Apply one completed local edit. Returns an error message if it was refused. */
  edit(op: Operation): string | null {
    if (this.readOnly) return "This drawing is in Recently Deleted. Restore it to edit it.";
    const refused = checkOperation(op, this.visible.length);
    if (refused) return refused;
    this.pending.push(op);
    this.history = { undo: this.history.undo + 1, redo: 0 };
    this.bump();
    this.enqueue(async () => {
      for (let attempt = 0; ; attempt++) {
        try {
          const saved = await this.bridge.append(this.id, op);
          const page: Page = { drawing: { ...this.drawing, revision: saved.drawing.revision, updated_at: saved.drawing.updated_at,
            op_count: saved.drawing.op_count, schema_version: saved.drawing.schema_version },
            records: [saved.record], cursor: this.cursor, more: false, history: saved.history,
            missing_assets: [...this.missing], device: this.device };
          if (this.take(page)) this.bump();
          return;
        } catch (failure) {
          const message = failure instanceof Error && failure.message ? failure.message : "Could not save drawing.";
          if (PERMANENT.test(message) || attempt >= RETRY.length || this.closed) {
            this.pending = this.pending.filter((p) => p.id !== op.id);
            this.bump();
            throw new Error(PERMANENT.test(message) ? message : "Could not save drawing. That edit was not saved.", { cause: failure });
          }
          this.saveState = "error";
          this.error = message;
          this.emit();
          await new Promise((resolve) => setTimeout(resolve, RETRY[attempt]));
        }
      }
    });
    return null;
  }

  undo() { this.step("undo"); }
  redo() { this.step("redo"); }

  private step(which: "undo" | "redo") {
    if (this.readOnly) return;
    this.enqueue(async () => {
      const result = await this.bridge[which](this.id);
      const page: Page = { drawing: this.drawing, records: result.record ? [result.record] : [], cursor: this.cursor, more: false,
        history: result.history, missing_assets: [...this.missing], device: this.device };
      if (this.take(page)) this.bump();
    });
  }

  private enqueue(task: () => Promise<void>) {
    this.busy += 1;
    this.saveState = "saving";
    this.error = "";
    this.emit();
    this.queue = this.queue.then(task).then(
      () => { this.saveState = "saved"; this.error = ""; },
      (failure) => { this.saveState = "error"; this.error = failure instanceof Error ? failure.message : "Could not save drawing."; },
    ).finally(() => {
      this.busy -= 1;
      if (this.busy && this.saveState === "saved") this.saveState = "saving";
      this.emit();
    });
  }

  /** Fetch records newer than this view's cursor (another window or device). */
  pull(): Promise<void> {
    if (this.pulling) {
      this.pullAgain = true;
      return this.pulling;
    }
    this.pulling = (async () => {
      do {
        this.pullAgain = false;
        let page: Page;
        let changed = false;
        do {
          page = await this.bridge.since(this.id, this.cursor);
          changed = this.take(page) || changed;
        } while (page.more && !this.closed);
        if (changed) this.bump();
        this.emit();
      } while (this.pullAgain && !this.closed);
    })().finally(() => { this.pulling = null; });
    return this.pulling;
  }

  /** Wait until every edit made here is saved (before export, switching, closing). */
  async flush(): Promise<void> {
    while (this.busy) await this.queue;
    if (this.saveState === "error") throw new Error(this.error || "Could not save drawing.");
  }

  /** Replace the backend's view after a rename/restore elsewhere in the UI. */
  setDrawing(update: Partial<DrawingSummary>) {
    this.drawing = { ...this.drawing, ...update };
    this.emit();
  }

  async close() {
    try { await this.flush(); } finally {
      this.closed = true;
      this.listeners.clear();
    }
  }
}
