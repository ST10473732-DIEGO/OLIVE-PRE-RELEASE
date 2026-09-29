// OLIVE Notes replica: the phone's local-first document store and sync engine.
//
// It runs inside the iOS app's JavaScriptCore (bundled by
// desktop/scripts/build-notes-engine.mjs) and mirrors olive/notes/service.py and
// olive/notes/sync_engine.py: same Yjs documents, same change-feed cursors, same
// olive-notes/1 messages. Storage and transport stay in the host (Swift):
//   * host.commit(batch) must apply one batch atomically (one SQLite transaction)
//     BEFORE the engine announces or sends anything;
//   * the host sends requests produced by next() and returns answers.
// No clocks decide conflicts; the CRDT does. Note text is data, never commands.
import * as Y from "yjs";
import { BODY, META, fromBase64, readMeta, toBase64 } from "./doc";
import { displayTitle, normalize, preview, textDiff, utf8Length } from "./text";
import {
  LIMITS, PROTOCOL, ProtocolError, covers, decodeRequest, decodeStateVector, uuid as checkUuid, validateResult,
  type Entry, type SyncRow,
} from "./protocol";

export const LOCAL = "olive-local";
export const REMOTE = "olive-remote";
const EMPTY_SV = new Uint8Array([0]);
const HOT = 8;
const COMPACT_UPDATES = 200;

export interface Host {
  loadIndex(): string;
  loadDocument(noteId: string): string;
  commit(batch: string): boolean;
  search(query: string): string;
  sha256(dataBase64: string): string;
  uuid(): string;
  now(): string;
  nowSeconds(): number;
  emit(event: string): void;
}

export interface Row {
  note_id: string; created_at: string; created_by: string; title: string; display_title: string; preview: string;
  pinned: boolean; trashed: boolean; trashed_at: string; edited_at: string; local_updated_at: string;
  text_length: number; change_seq: number; last_change_peer: string | null; status: string;
  /** Committed text not yet in the search index; survives a restart (see tick). */
  search_pending?: boolean;
}
interface Purge { note_id: string; change_seq: number; purged_at: string; purged_by: string }
interface Peer { device_id: string; acked_seq: number; peer_epoch: string | null; last_sync: string | null; last_error: string | null }
interface Batch {
  store_seq?: number; epoch?: string; rows?: Row[]; delete_notes?: string[];
  updates?: { note_id: string; update_id: string; payload: string; origin: string; device: string }[];
  purges?: Purge[]; peers?: Peer[]; search?: { note_id: string; title: string; body: string }[];
  snapshots?: { note_id: string; state: string; sha256: string }[];
}
interface Meta { kind: "skip" | "purge" | "offer" | "update" | "transfer"; seq: number; note_id?: string; sv?: Uint8Array }
interface Prepared { arguments: Record<string, unknown> | null; meta: Meta[]; transfers: Transfer[]; acked: number; entries: { note_id: string }[] }
interface Transfer { note_id: string; seq: number; sv: Uint8Array; data: Uint8Array }
interface Pending { ticket: string; operation: string; batch?: Prepared; transfer?: Transfer; last?: boolean; entries?: { note_id: string }[] }
interface Pump { hello: boolean; queue: { operation: string; arguments: Record<string, unknown>; transfer: Transfer; last: boolean }[];
  inflight: Pending | null; rounds: number; stalled: number }

export class NotesError extends Error {}

export class Replica {
  rows = new Map<string, Row>();
  purges = new Map<string, Purge>();
  peers = new Map<string, Peer>();
  storeSeq = 0;
  epoch = "";
  private docs = new Map<string, Y.Doc>();
  private undoManagers = new Map<string, Y.UndoManager>();
  private counts = new Map<string, number>();
  private remoteSv = new Map<string, Map<string, Uint8Array>>();
  private transfers = new Map<string, { note_id: string; seq: number; count: number; total_bytes: number; sha256: string; parts: Map<number, Uint8Array>; size: number; expires: number; sv: Uint8Array }>();
  private dirtySearch = new Set<string>();
  private corrupt = new Set<string>();
  private pumps = new Map<string, Pump>();
  refused = new Map<string, Map<string, string>>();
  openId: string | null = null;

  constructor(private host: Host, readonly deviceId: string) {
    const index = JSON.parse(host.loadIndex()) as { rows: Row[]; purges: Purge[]; peers: Peer[]; meta: { store_seq: number; epoch: string } };
    for (const row of index.rows) this.rows.set(row.note_id, row);
    for (const purge of index.purges) this.purges.set(purge.note_id, purge);
    for (const peer of index.peers) this.peers.set(peer.device_id, peer);
    this.storeSeq = index.meta.store_seq || 0;
    this.epoch = index.meta.epoch;
    if (!this.epoch) {
      const epoch = host.uuid();
      if (!host.commit(JSON.stringify({ epoch }))) throw new NotesError("notes_unavailable");
      this.epoch = epoch;
    }
    for (const row of this.rows.values()) {
      if (row.status !== "ok") this.corrupt.add(row.note_id);
      else if (row.search_pending) this.dirtySearch.add(row.note_id);
    }
  }

  private emit(event: Record<string, unknown>) {
    this.host.emit(JSON.stringify(event));
  }

  // --- documents -------------------------------------------------------------------
  private document(id: string): Y.Doc {
    const cached = this.docs.get(id);
    if (cached) { this.docs.delete(id); this.docs.set(id, cached); return cached; }
    if (this.purges.has(id)) throw new NotesError("note_purged");
    if (!this.rows.has(id)) throw new NotesError("note_not_found");
    if (this.corrupt.has(id)) throw new NotesError("note_data_corrupted");
    const doc = new Y.Doc();
    try {
      const data = JSON.parse(this.host.loadDocument(id)) as { snapshot: string | null; updates: string[]; corrupt?: boolean } | null;
      if (!data || data.corrupt) throw new Error("missing_or_corrupt"); // Host keeps the bytes for recovery.
      if (data.snapshot) Y.applyUpdate(doc, fromBase64(data.snapshot), REMOTE);
      for (const update of data.updates) Y.applyUpdate(doc, fromBase64(update), REMOTE);
      this.counts.set(id, data.updates.length);
    } catch {
      doc.destroy();
      this.markCorrupt(id);
      throw new NotesError("note_data_corrupted");
    }
    this.attach(id, doc);
    return doc;
  }

  private attach(id: string, doc: Y.Doc) {
    this.docs.set(id, doc);
    // Track this device's own edits from the moment the document is loaded.
    this.undoManagers.set(id, new Y.UndoManager(doc.getText(BODY), { trackedOrigins: new Set([LOCAL]), captureTimeout: 500 }));
    doc.getText(BODY).observe((event, transaction) => {
      if (transaction.origin === LOCAL || id !== this.openId) return;
      // Remote or undo edits for the open editor: UTF-16 positions (NSString-compatible).
      const delta = (event.delta as { retain?: number; insert?: unknown; delete?: number }[])
        .map((op) => (op.insert !== undefined && typeof op.insert !== "string" ? { insert: "" } : op));
      this.emit({ type: "delta", note_id: id, delta });
    });
    while (this.docs.size > HOT) {
      const [oldest] = this.docs.keys();
      if (oldest === this.openId) break;
      this.docs.get(oldest)?.destroy();
      this.docs.delete(oldest);
      this.undoManagers.get(oldest)?.destroy();
      this.undoManagers.delete(oldest);
    }
  }

  private markCorrupt(id: string) {
    this.corrupt.add(id);
    const row = this.rows.get(id);
    if (row && row.status !== "corrupt") {
      const updated = { ...row, status: "corrupt" };
      if (this.host.commit(JSON.stringify({ rows: [updated] }))) this.rows.set(id, updated);
    }
  }

  private capture(doc: Y.Doc, change: () => void): Uint8Array | null {
    const captured: Uint8Array[] = [];
    const listener = (update: Uint8Array) => captured.push(update);
    doc.on("update", listener);
    try { change(); } finally { doc.off("update", listener); }
    if (!captured.length) return null;
    return captured.length === 1 ? captured[0] : Y.mergeUpdates(captured);
  }

  private buildRow(id: string, doc: Y.Doc, seq: number, peer: string | null): Row {
    const meta = readMeta(doc);
    const body = doc.getText(BODY).toString();
    const now = this.host.now();
    return {
      note_id: id, created_at: meta.created_at || now, created_by: meta.created_by, title: meta.title,
      display_title: displayTitle(meta.title, body), preview: preview(meta.title, body), pinned: meta.pinned,
      trashed: meta.trashed, trashed_at: meta.trashed_at, edited_at: meta.edited_at || now, local_updated_at: now,
      text_length: body.length, change_seq: seq, last_change_peer: peer, status: "ok",
    };
  }

  /** One atomic local commit: CRDT update(s) + row + change feed position. */
  private commitChange(id: string, doc: Y.Doc, updates: (Uint8Array | null)[], options: { origin: string; device: string; peer?: string | null; created?: boolean; content?: boolean }) {
    const payloads = updates.filter((u): u is Uint8Array => Boolean(u && u.length));
    if (!payloads.length) return this.rows.get(id)!;
    if (options.created && this.rows.size >= LIMITS.max_notes) throw new NotesError("notes_capacity");
    const seq = this.storeSeq + 1;
    const row = this.buildRow(id, doc, seq, options.peer ?? null);
    if (options.content !== false || this.rows.get(id)?.search_pending) row.search_pending = true;
    const batch: Batch = {
      store_seq: seq, rows: [row],
      updates: payloads.map((payload) => {
        const encoded = toBase64(payload);
        return {
          note_id: id, payload: encoded, origin: options.origin, device: options.device,
          update_id: options.origin === "remote" ? "r:" + this.host.sha256(toBase64(new TextEncoderLite().encode(id + encoded))) : this.host.uuid(),
        };
      }),
    };
    if (!this.host.commit(JSON.stringify(batch))) {
      // Not durable: forget the in-memory change so the store stays authoritative.
      this.docs.get(id)?.destroy();
      this.docs.delete(id);
      this.undoManagers.get(id)?.destroy();
      this.undoManagers.delete(id);
      this.emit({ type: "reset", note_id: id, error: "Could not save locally" });
      throw new NotesError("could_not_save_locally");
    }
    this.storeSeq = seq;
    this.rows.set(id, row);
    this.counts.set(id, (this.counts.get(id) || 0) + payloads.length);
    if (options.content !== false) this.dirtySearch.add(id);
    this.emit({ type: "changed", note_id: id, origin: options.origin });
    return row;
  }

  // --- local operations -------------------------------------------------------------
  list(view: "notes" | "trash" = "notes"): Row[] {
    const rows = [...this.rows.values()].filter((r) => r.trashed === (view === "trash"));
    return view === "trash"
      ? rows.sort((a, b) => b.trashed_at.localeCompare(a.trashed_at))
      : rows.sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.edited_at.localeCompare(a.edited_at) || a.note_id.localeCompare(b.note_id));
  }

  create(title = "", body = ""): Row {
    const id = this.host.uuid();
    const text = normalize(body);
    if (utf8Length(text) > LIMITS.max_note_text_bytes) throw new NotesError("note_too_large");
    const doc = new Y.Doc();
    const now = this.host.now();
    const update = this.capture(doc, () => doc.transact(() => {
      const meta = doc.getMap(META);
      meta.set("schema", 1); meta.set("created_at", now); meta.set("created_by", this.deviceId); meta.set("edited_at", now);
      meta.set("title", normalize(title).trim().slice(0, LIMITS.max_title_chars)); meta.set("pinned", false);
      meta.set("trashed", false); meta.set("trashed_at", "");
      if (text) doc.getText(BODY).insert(0, text);
    }, LOCAL));
    this.attach(id, doc);
    try {
      return this.commitChange(id, doc, [update], { origin: "local", device: this.deviceId, created: true });
    } catch (error) {
      this.docs.delete(id);
      throw error;
    }
  }

  open(id: string) {
    const doc = this.document(id);
    this.openId = id;
    return { note: this.rows.get(id), text: doc.getText(BODY).toString() };
  }

  close(id: string) {
    if (this.openId === id) this.openId = null;
  }

  text(id: string): string {
    return this.document(id).getText(BODY).toString();
  }

  private touch(doc: Y.Doc): Uint8Array | null {
    const edited = readMeta(doc).edited_at;
    const age = Date.parse(this.host.now()) - Date.parse(edited || "1970-01-01T00:00:00Z");
    if (age < 10_000) return null;
    return this.capture(doc, () => doc.transact(() => doc.getMap(META).set("edited_at", this.host.now()), LOCAL));
  }

  /** One editor change in UTF-16 code units (NSString ranges map directly). */
  edit(id: string, index: number, remove: number, insert: string): Row {
    const doc = this.document(id);
    const text = doc.getText(BODY);
    const current = text.toString();
    if (!Number.isInteger(index) || !Number.isInteger(remove) || index < 0 || remove < 0 || index + remove > current.length)
      throw new NotesError("invalid_edit");
    const value = normalize(insert);
    const next = current.slice(0, index) + value + current.slice(index + remove);
    if (next.length * 3 > LIMITS.max_note_text_bytes && utf8Length(next) > LIMITS.max_note_text_bytes) throw new NotesError("note_too_large");
    const update = this.capture(doc, () => doc.transact(() => {
      if (remove) text.delete(index, remove);
      if (value) text.insert(index, value);
    }, LOCAL));
    return this.commitChange(id, doc, [update, this.touch(doc)], { origin: "local", device: this.deviceId });
  }

  replaceText(id: string, next: string): Row {
    const current = this.text(id);
    const change = textDiff(current, normalize(next));
    return change ? this.edit(id, change.index, change.remove, change.insert) : this.rows.get(id)!;
  }

  private setMeta(id: string, values: Record<string, string | boolean>, content = false): Row {
    const doc = this.document(id);
    const meta = doc.getMap(META);
    const changes = Object.entries(values).filter(([key, value]) => meta.get(key) !== value);
    if (!changes.length) return this.rows.get(id)!;
    const update = this.capture(doc, () => doc.transact(() => {
      for (const [key, value] of changes) meta.set(key, value);
      if ("title" in values) meta.set("edited_at", this.host.now());
    }, LOCAL));
    return this.commitChange(id, doc, [update], { origin: "local", device: this.deviceId, content });
  }

  rename(id: string, title: string) { return this.setMeta(id, { title: normalize(title).trim().slice(0, LIMITS.max_title_chars) }, true); }
  pin(id: string, pinned: boolean) { return this.setMeta(id, { pinned }); }
  trash(id: string) { return this.setMeta(id, { trashed: true, trashed_at: this.host.now() }); }
  restore(id: string) { return this.setMeta(id, { trashed: false, trashed_at: "" }); }

  private undoManager(id: string) {
    this.document(id);
    return this.undoManagers.get(id)!;
  }

  /** Undo/redo this device's own typing only (remote edits are never tracked). */
  undo(id: string, redo = false) {
    const doc = this.document(id);
    const manager = this.undoManager(id);
    const update = this.capture(doc, () => { if (redo) manager.redo(); else manager.undo(); });
    return this.commitChange(id, doc, [update], { origin: "local", device: this.deviceId });
  }

  purge(id: string, options: { origin?: string; peer?: string | null } = {}) {
    if (this.purges.has(id)) return;
    const row = this.rows.get(id);
    if (options.origin !== "remote" && (!row || !row.trashed)) throw new NotesError(row ? "not_in_trash" : "note_not_found");
    const seq = this.storeSeq + 1;
    const purge: Purge = { note_id: id, change_seq: seq, purged_at: this.host.now(), purged_by: options.peer || this.deviceId };
    if (!this.host.commit(JSON.stringify({ store_seq: seq, delete_notes: [id], purges: [purge] }))) throw new NotesError("could_not_save_locally");
    this.storeSeq = seq;
    this.rows.delete(id);
    this.purges.set(id, purge);
    this.docs.get(id)?.destroy();
    this.docs.delete(id);
    this.undoManagers.delete(id);
    this.dirtySearch.delete(id);
    this.corrupt.delete(id);
    if (this.openId === id) this.openId = null;
    this.emit({ type: "purged", note_id: id });
  }

  search(query: string): (Row & { snippet: string })[] {
    this.tick();
    const needle = query.trim();
    if (!needle || needle.length > 500) return [];
    const ids = JSON.parse(this.host.search(needle)) as string[];
    return ids.slice(0, 50).flatMap((id) => {
      const row = this.rows.get(id);
      if (!row) return [];
      let snippet = "";
      try {
        const body = this.text(id);
        const at = body.toLowerCase().indexOf(needle.toLowerCase());
        if (at >= 0) snippet = body.slice(Math.max(0, at - 50), at + needle.length + 70).replace(/\s+/g, " ").trim();
      } catch { /* corrupted notes still match by title */ }
      return [{ ...row, snippet }];
    });
  }

  /** Deferred work: search index text and log compaction. Never network. */
  tick() {
    if (this.dirtySearch.size) {
      const rows = [...this.dirtySearch].flatMap((id) => {
        try { return [{ note_id: id, title: this.rows.get(id)?.display_title || "", body: this.text(id) }]; } catch { return []; }
      });
      // The index rows and the cleared flags commit together, so a restart
      // before this point re-indexes instead of leaving a note unsearchable.
      const indexed = rows.flatMap(({ note_id }) => {
        const row = this.rows.get(note_id);
        return row?.search_pending ? [{ ...row, search_pending: false }] : [];
      });
      if (this.host.commit(JSON.stringify({ search: rows, rows: indexed }))) {
        this.dirtySearch.clear();
        for (const row of indexed) this.rows.set(row.note_id, row);
      }
    }
    for (const [id, count] of this.counts) if (count >= COMPACT_UPDATES) this.compact(id);
  }

  private compact(id: string) {
    try {
      const data = JSON.parse(this.host.loadDocument(id)) as { snapshot: string | null; updates: string[] };
      const parts = [...(data.snapshot ? [fromBase64(data.snapshot)] : []), ...data.updates.map(fromBase64)];
      const merged = Y.mergeUpdates(parts);
      const check = new Y.Doc();
      Y.applyUpdate(check, merged);
      if (check.getText(BODY).toString() !== this.text(id)) return;
      const state = toBase64(merged);
      if (this.host.commit(JSON.stringify({ snapshots: [{ note_id: id, state, sha256: this.host.sha256(state) }] }))) this.counts.set(id, 0);
    } catch { /* keep the log; retried later */ }
  }

  // --- sync: receiving ----------------------------------------------------------------
  private peer(id: string): Peer {
    return this.peers.get(id) || { device_id: id, acked_seq: 0, peer_epoch: null, last_sync: null, last_error: null };
  }

  private savePeer(id: string, values: Partial<Peer>) {
    const next = { ...this.peer(id), ...values };
    if (this.host.commit(JSON.stringify({ peers: [next] }))) this.peers.set(id, next);
  }

  private observeEpoch(peer: string, epoch: string): boolean {
    const stored = this.peer(peer);
    if (stored.peer_epoch === epoch) return false;
    if (stored.peer_epoch !== null) {
      this.remoteSv.delete(peer);
      this.savePeer(peer, { acked_seq: 0, peer_epoch: epoch });
    } else this.savePeer(peer, { peer_epoch: epoch });
    return true;
  }

  private known(peer: string) {
    let map = this.remoteSv.get(peer);
    if (!map) { map = new Map(); this.remoteSv.set(peer, map); }
    return map;
  }

  private stateVectorOf(id: string): { sv: Uint8Array; exists: boolean } {
    try { return { sv: Y.encodeStateVector(this.document(id)), exists: true }; } catch { return { sv: EMPTY_SV, exists: false }; }
  }

  private applyRemote(id: string, update: Uint8Array, peer: string): { status: string; sv: Uint8Array } {
    if (this.purges.has(id)) return { status: "purged", sv: EMPTY_SV };
    const row = this.rows.get(id);
    if (this.corrupt.has(id)) return { status: "rejected:invalid_update", sv: EMPTY_SV };
    let incoming: Map<number, number>;
    try { incoming = decodeStateVector(Y.encodeStateVectorFromUpdate(update)); } catch { return { status: "rejected:invalid_update", sv: EMPTY_SV }; }
    const created = !row;
    const doc = created ? new Y.Doc() : this.document(id);
    const before = doc.getText(BODY).toString();
    let effective: Uint8Array | null;
    try {
      effective = this.capture(doc, () => Y.applyUpdate(doc, update, REMOTE));
    } catch {
      if (!created) { this.docs.get(id)?.destroy(); this.docs.delete(id); }
      return { status: "rejected:invalid_update", sv: EMPTY_SV };
    }
    const after = doc.getText(BODY).toString();
    if (utf8Length(after) > LIMITS.max_note_text_bytes) {
      if (!created) { this.docs.get(id)?.destroy(); this.docs.delete(id); }
      return { status: "rejected:note_too_large", sv: EMPTY_SV };
    }
    const pending = !covers(decodeStateVector(Y.encodeStateVector(doc)), incoming);
    if (effective || pending) {
      const delivered = created || row!.last_change_peer === peer || row!.change_seq <= this.peer(peer).acked_seq;
      if (created) this.attach(id, doc);
      try {
        this.commitChange(id, doc, [pending ? update : effective], {
          origin: "remote", device: peer, peer: delivered ? peer : null, created, content: after !== before,
        });
      } catch (error) {
        if (created) this.docs.delete(id);
        return { status: error instanceof NotesError && error.message === "notes_capacity" ? "rejected:notes_capacity" : "rejected:invalid_update", sv: EMPTY_SV };
      }
    }
    return { status: "applied", sv: Y.encodeStateVector(doc) };
  }

  private applyEntry(peer: string, id: string, update: Uint8Array, senderSv: Uint8Array) {
    const { status, sv } = this.applyRemote(id, update, peer);
    if (status === "purged") return { note_id: id, status: "purged", sv: "" };
    if (status.startsWith("rejected")) return { note_id: id, status: "rejected", sv: "", error: status.split(":")[1] || "invalid_update" };
    const covered = covers(decodeStateVector(sv), decodeStateVector(senderSv));
    return { note_id: id, status: covered ? "applied" : "needs", sv: toBase64(sv) };
  }

  /** A Connect request from an authenticated, permitted peer. Returns the response JSON. */
  handle(peer: string, raw: string): string {
    let requestId: string | null = null;
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      if (typeof parsed.request_id === "string") requestId = parsed.request_id;
      const request = decodeRequest(parsed);
      requestId = request.request_id;
      if (request.source_device_id !== peer) throw new ProtocolError("source_mismatch");
      if (request.target_device_id !== this.deviceId) throw new ProtocolError("wrong_target");
      const now = this.host.nowSeconds();
      if (request.timestamp > now + LIMITS.future_tolerance_seconds || request.expires_at <= now) throw new ProtocolError("expired_request");
      const args = request.arguments;
      let result: Record<string, unknown>;
      if (request.operation === "hello") {
        if (!(args.versions as string[]).includes(PROTOCOL)) throw new ProtocolError("unsupported_protocol");
        result = { versions: [PROTOCOL], epoch: this.epoch };
      } else {
        this.observeEpoch(peer, args.epoch as string);
        if (request.operation === "sync") {
          result = { epoch: this.epoch, results: (args.entries as Entry[]).map((entry) => this.receiveEntry(peer, entry)) };
        } else {
          result = this.receiveChunk(peer, args);
        }
      }
      return JSON.stringify({ protocol_version: PROTOCOL, request_id: requestId, state: "completed", result });
    } catch (error) {
      const code = error instanceof ProtocolError ? error.message : error instanceof NotesError ? "notes_unavailable" : "malformed_message";
      return JSON.stringify({ protocol_version: PROTOCOL, request_id: requestId && /^[0-9a-f-]{36}$/.test(requestId) ? requestId : null, state: "rejected", error: code });
    }
  }

  private receiveEntry(peer: string, entry: Entry) {
    this.known(peer).set(entry.note_id, entry.sv);
    if (entry.purged) {
      this.purge(entry.note_id, { origin: "remote", peer });
      return { note_id: entry.note_id, status: "purged", sv: "" };
    }
    if (this.purges.has(entry.note_id)) return { note_id: entry.note_id, status: "purged", sv: "" };
    if (entry.update) return this.applyEntry(peer, entry.note_id, entry.update, entry.sv);
    const { sv, exists } = this.stateVectorOf(entry.note_id);
    const covered = exists && covers(decodeStateVector(sv), decodeStateVector(entry.sv));
    return { note_id: entry.note_id, status: covered ? "current" : "needs", sv: toBase64(sv) };
  }

  private receiveChunk(peer: string, args: Record<string, unknown>) {
    const now = Date.now();
    for (const [key, value] of this.transfers) if (value.expires < now) this.transfers.delete(key);
    const key = `${peer}:${args.transfer_id}`;
    let staging = this.transfers.get(key);
    if (!staging) {
      if ([...this.transfers.keys()].filter((k) => k.startsWith(peer + ":")).length >= LIMITS.max_transfers_per_peer) throw new ProtocolError("busy");
      staging = { note_id: args.note_id as string, seq: args.seq as number, count: args.count as number, total_bytes: args.total_bytes as number,
        sha256: args.sha256 as string, parts: new Map(), size: 0, expires: 0, sv: args.sv as Uint8Array };
      this.transfers.set(key, staging);
    } else if (staging.note_id !== args.note_id || staging.count !== args.count || staging.total_bytes !== args.total_bytes || staging.sha256 !== args.sha256) {
      this.transfers.delete(key);
      throw new ProtocolError("malformed_message");
    }
    staging.expires = now + LIMITS.transfer_idle_seconds * 1000;
    const index = args.index as number;
    if (!staging.parts.has(index)) {
      const data = args.data as Uint8Array;
      staging.parts.set(index, data);
      staging.size += data.length;
    }
    if (staging.size > staging.total_bytes) { this.transfers.delete(key); throw new ProtocolError("payload_too_large"); }
    if (staging.parts.size < staging.count) return { epoch: this.epoch, status: "partial", sv: "" };
    this.transfers.delete(key);
    const payload = new Uint8Array(staging.total_bytes);
    let offset = 0;
    for (let i = 0; i < staging.count; i++) { const part = staging.parts.get(i)!; payload.set(part, offset); offset += part.length; }
    if (offset !== staging.total_bytes || this.host.sha256(toBase64(payload)) !== staging.sha256) throw new ProtocolError("invalid_update");
    this.known(peer).set(staging.note_id, args.sv as Uint8Array);
    if (this.purges.has(staging.note_id)) return { epoch: this.epoch, status: "purged", sv: "" };
    const { note_id: _ignored, ...rest } = this.applyEntry(peer, staging.note_id, payload, args.sv as Uint8Array);
    void _ignored;
    return { epoch: this.epoch, ...rest };
  }

  // --- sync: sending (a state machine the host drives) --------------------------------
  pending(peer: string): number {
    const acked = this.peer(peer).acked_seq;
    let count = 0;
    for (const row of this.rows.values()) if (row.change_seq > acked && row.status === "ok" && row.last_change_peer !== peer) count++;
    for (const purge of this.purges.values()) if (purge.change_seq > acked) count++;
    return count;
  }

  private prepare(peer: string): Prepared | null {
    const acked = this.peer(peer).acked_seq;
    type Item = { seq: number; id: string; purged: boolean; skip: boolean };
    const feed: Item[] = [];
    for (const row of this.rows.values()) if (row.change_seq > acked)
      feed.push({ seq: row.change_seq, id: row.note_id, purged: false, skip: row.last_change_peer === peer || row.status !== "ok" });
    for (const purge of this.purges.values()) if (purge.change_seq > acked) feed.push({ seq: purge.change_seq, id: purge.note_id, purged: true, skip: false });
    feed.sort((a, b) => a.seq - b.seq);
    const page = feed.slice(0, LIMITS.max_entries);
    if (!page.length) return null;
    const entries: Record<string, unknown>[] = [];
    const meta: Meta[] = [];
    const transfers: Transfer[] = [];
    let budget = LIMITS.max_request_update_bytes;
    const known = this.remoteSv.get(peer) || new Map<string, Uint8Array>();
    for (const item of page) {
      if (item.skip) { meta.push({ kind: "skip", seq: item.seq }); continue; }
      if (item.purged) {
        entries.push({ note_id: item.id, seq: item.seq, sv: toBase64(EMPTY_SV), purged: true });
        meta.push({ kind: "purge", seq: item.seq, note_id: item.id });
        continue;
      }
      let doc: Y.Doc;
      try { doc = this.document(item.id); } catch { meta.push({ kind: "skip", seq: item.seq }); continue; }
      const sv = Y.encodeStateVector(doc);
      const entry: Record<string, unknown> = { note_id: item.id, seq: item.seq, sv: toBase64(sv), purged: false };
      let kind: Meta["kind"] = "offer";
      const remote = known.get(item.id);
      if (remote) {
        const update = Y.encodeStateAsUpdate(doc, remote);
        if (update.length > LIMITS.max_inline_update_bytes) {
          kind = "transfer";
          transfers.push({ note_id: item.id, seq: item.seq, sv, data: update });
        } else if (update.length <= budget) {
          entry.update = toBase64(update);
          budget -= update.length;
          kind = "update";
        } else if (entries.length) break;
      }
      entries.push(entry);
      meta.push({ kind, seq: item.seq, note_id: item.id, sv });
    }
    if (!entries.length) {
      this.savePeer(peer, { acked_seq: meta[meta.length - 1].seq });
      return { arguments: null, meta, transfers: [], acked, entries: [] };
    }
    return { arguments: { epoch: this.epoch, entries }, meta, transfers, acked, entries: entries as { note_id: string }[] };
  }

  private process(peer: string, batch: Prepared, result: { epoch: string; results: SyncRow[] }): boolean {
    if (this.observeEpoch(peer, result.epoch) && this.peer(peer).acked_seq === 0 && batch.acked > 0) return true;
    const refused = this.refused.get(peer) || new Map<string, string>();
    this.refused.set(peer, refused);
    const known = this.known(peer);
    const rows = result.results[Symbol.iterator]();
    const delivered: boolean[] = [];
    let learned = false;
    for (const item of batch.meta) {
      if (item.kind === "skip") { delivered.push(true); continue; }
      const row = rows.next().value as SyncRow;
      const id = item.note_id!;
      if (row.status === "purged") {
        if (item.kind !== "purge") this.purge(id, { origin: "remote", peer });
        delivered.push(true);
        continue;
      }
      if (row.status === "rejected") { refused.set(id, row.error || "invalid_update"); delivered.push(true); continue; }
      refused.delete(id);
      known.set(id, row.sv!);
      learned = true;
      const covered = covers(decodeStateVector(row.sv!), decodeStateVector(item.sv!));
      delivered.push(item.kind === "update" && covered && (row.status === "applied" || row.status === "current"));
    }
    let acked = batch.acked;
    for (let i = 0; i < batch.meta.length && delivered[i]; i++) acked = batch.meta[i].seq;
    if (acked > batch.acked) this.savePeer(peer, { acked_seq: acked, last_error: null });
    return acked > batch.acked || learned;
  }

  private pump(peer: string): Pump {
    let pump = this.pumps.get(peer);
    if (!pump) { pump = { hello: false, queue: [], inflight: null, rounds: 0, stalled: 0 }; this.pumps.set(peer, pump); }
    return pump;
  }

  private request(peer: string, operation: string, args: Record<string, unknown>, pending: Omit<Pending, "ticket" | "operation">) {
    const ticket = this.host.uuid();
    const now = this.host.nowSeconds();
    this.pump(peer).inflight = { ticket, operation, ...pending };
    return JSON.stringify({ ticket, request: { protocol_version: PROTOCOL, request_id: ticket, source_device_id: this.deviceId,
      target_device_id: checkUuid(peer), operation, arguments: args, timestamp: now, expires_at: now + LIMITS.max_request_lifetime_seconds } });
  }

  /** The next request to send to `peer`, or {"done": "synced" | "partial"}. */
  next(peer: string): string {
    const pump = this.pump(peer);
    if (pump.inflight) return JSON.stringify({ wait: true });
    if (!pump.hello) return this.request(peer, "hello", { versions: [PROTOCOL] }, {});
    const queued = pump.queue.shift();
    if (queued) return this.request(peer, "chunk", queued.arguments, { transfer: queued.transfer, last: queued.last });
    for (let guard = 0; guard < 4; guard++) {
      if (pump.rounds >= LIMITS.max_rounds_per_pump) { pump.rounds = 0; return JSON.stringify({ done: "partial" }); }
      const batch = this.prepare(peer);
      if (!batch) {
        pump.rounds = 0;
        this.savePeer(peer, { last_sync: this.host.now(), last_error: null });
        return JSON.stringify({ done: "synced" });
      }
      if (batch.arguments) return this.request(peer, "sync", batch.arguments, { batch, entries: batch.entries });
    }
    return JSON.stringify({ done: "partial" });
  }

  /** The peer's response to the request with `ticket`. Returns {"ok":true} or {"error":code}. */
  answer(peer: string, ticket: string, raw: string): string {
    const pump = this.pump(peer);
    const pending = pump.inflight;
    if (!pending || pending.ticket !== ticket) return JSON.stringify({ error: "stale_answer" });
    pump.inflight = null;
    try {
      const response = JSON.parse(raw) as Record<string, unknown>;
      if (response.protocol_version !== PROTOCOL || response.request_id !== ticket) throw new ProtocolError("malformed_message");
      if (response.state === "rejected") throw new ProtocolError(typeof response.error === "string" ? response.error : "malformed_message");
      if (response.state !== "completed") throw new ProtocolError("malformed_message");
      if (pending.operation === "hello") {
        const result = validateResult("hello", response.result) as { versions: string[]; epoch: string };
        if (!result.versions.includes(PROTOCOL)) throw new ProtocolError("unsupported_protocol");
        this.observeEpoch(peer, result.epoch);
        pump.hello = true;
      } else if (pending.operation === "sync") {
        const result = validateResult("sync", response.result, pending.entries) as { epoch: string; results: SyncRow[] };
        const progress = this.process(peer, pending.batch!, result);
        for (const transfer of pending.batch!.transfers) pump.queue.push(...this.chunks(transfer));
        pump.rounds++;
        pump.stalled = progress || pending.batch!.transfers.length ? 0 : pump.stalled + 1;
        if (pump.stalled >= 3) { pump.stalled = 0; throw new ProtocolError("sync_stalled"); }
      } else {
        const result = validateResult("chunk", response.result) as { status: string; sv: Uint8Array | null; error?: string };
        if (result.status === "rejected") throw new ProtocolError(result.error || "invalid_update");
        if (pending.last) {
          if (result.status === "purged") this.purge(pending.transfer!.note_id, { origin: "remote", peer });
          else if (result.sv) this.known(peer).set(pending.transfer!.note_id, result.sv);
        }
      }
      return JSON.stringify({ ok: true });
    } catch (error) {
      return JSON.stringify({ error: this.fail(peer, error instanceof Error ? error.message : "malformed_message") });
    }
  }

  private chunks(transfer: Transfer) {
    const size = LIMITS.max_chunk_bytes;
    const count = Math.ceil(transfer.data.length / size);
    const base = { epoch: this.epoch, transfer_id: this.host.uuid(), note_id: transfer.note_id, seq: transfer.seq, sv: toBase64(transfer.sv),
      count, total_bytes: transfer.data.length, sha256: this.host.sha256(toBase64(transfer.data)) };
    return Array.from({ length: count }, (_, index) => ({
      operation: "chunk", transfer, last: index === count - 1,
      arguments: { ...base, index, data: toBase64(transfer.data.subarray(index * size, (index + 1) * size)) },
    }));
  }

  /** Transport failure or a rejected request: edits stay durable; retry later. */
  fail(peer: string, code: string): string {
    const pump = this.pump(peer);
    pump.inflight = null;
    pump.queue = [];
    pump.rounds = 0;
    if (["permission_off", "device_not_paired", "unsupported_protocol", "identity_mismatch"].includes(code)) pump.hello = false;
    this.savePeer(peer, { last_error: code.slice(0, 64) });
    return code;
  }

  /** The Connect channel closed: transient knowledge goes, durable cursors stay. */
  disconnected(peer: string) {
    this.pumps.delete(peer);
    for (const key of [...this.transfers.keys()]) if (key.startsWith(peer + ":")) this.transfers.delete(key);
  }

  status(peer: string) {
    const stored = this.peer(peer);
    return { pending: this.pending(peer), last_sync: stored.last_sync, last_error: stored.last_error, refused: this.refused.get(peer)?.size || 0 };
  }
}

/** Minimal UTF-8 encoder: JavaScriptCore has no TextEncoder. */
class TextEncoderLite {
  encode(text: string): Uint8Array {
    const out: number[] = [];
    for (const character of text) {
      const code = character.codePointAt(0)!;
      if (code < 0x80) out.push(code);
      else if (code < 0x800) out.push(0xc0 | (code >> 6), 0x80 | (code & 63));
      else if (code < 0x10000) out.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 63), 0x80 | (code & 63));
      else out.push(0xf0 | (code >> 18), 0x80 | ((code >> 12) & 63), 0x80 | ((code >> 6) & 63), 0x80 | (code & 63));
    }
    return new Uint8Array(out);
  }
}
