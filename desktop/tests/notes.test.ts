import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import * as Y from "yjs";
import { TextareaBinding, findAll } from "../src/features/notes/binding";
import { NoteSession, type NotesBridge, type NoteSummary } from "../src/features/notes/session";
import { displayTitle, normalize, preview, textDiff, tooLarge, transformIndex } from "../src/features/notes/engine/text";
import { fromBase64, readMeta, toBase64 } from "../src/features/notes/engine/doc";
import spec from "../src/features/notes/engine/protocol_v1.json";
import { sortNotes, stableOrder, syncLine } from "../src/features/notes/notesModel";
import { notesSchemas } from "../electron/notes-contracts";

/** A textarea that follows the HTML setRangeText("preserve") selection rules. */
class FakeArea {
  private text = "";
  selectionStart = 0;
  selectionEnd = 0;
  scrollTop = 120;
  private listeners = new Map<string, EventListener[]>();
  get value() { return this.text; }
  set value(next: string) { this.text = next; this.selectionStart = this.selectionEnd = next.length; }
  setRangeText(replacement: string, start: number, end: number) {
    const delta = replacement.length - (end - start);
    this.text = this.text.slice(0, start) + replacement + this.text.slice(end);
    const newEnd = start + replacement.length;
    if (this.selectionStart > end) this.selectionStart += delta; else if (this.selectionStart > start) this.selectionStart = start;
    if (this.selectionEnd > end) this.selectionEnd += delta; else if (this.selectionEnd > start) this.selectionEnd = newEnd;
  }
  setSelectionRange(start: number, end: number) { this.selectionStart = start; this.selectionEnd = end; }
  addEventListener(type: string, listener: EventListener) { this.listeners.set(type, [...(this.listeners.get(type) || []), listener]); }
  removeEventListener(type: string, listener: EventListener) { this.listeners.set(type, (this.listeners.get(type) || []).filter((l) => l !== listener)); }
  fire(type: string, event: object = {}) {
    for (const listener of this.listeners.get(type) || []) listener({ preventDefault() {}, ...event } as unknown as Event);
  }
  /** User types/pastes over the selection. */
  type(text: string) {
    const start = this.selectionStart;
    this.text = this.text.slice(0, start) + text + this.text.slice(this.selectionEnd);
    this.selectionStart = this.selectionEnd = start + text.length;
    this.fire("input");
  }
  backspace() {
    const start = this.selectionStart === this.selectionEnd ? this.selectionStart - 1 : this.selectionStart;
    this.text = this.text.slice(0, start) + this.text.slice(this.selectionEnd);
    this.selectionStart = this.selectionEnd = start;
    this.fire("input");
  }
}

/** In-memory backend: one authoritative Y.Doc and a list of connected views. */
class FakeBackend {
  doc = new Y.Doc();
  applies = 0;
  fail = 0;
  views: NoteSession[] = [];
  constructor(text = "") {
    this.doc.getText("body").insert(0, text);
    this.doc.getMap("meta").set("title", "");
  }
  bridge(): NotesBridge {
    const note = { note_id: "n1" } as NoteSummary;
    return {
      open: async () => ({ state: toBase64(Y.encodeStateAsUpdate(this.doc)), chunks: 0, token: "", note }),
      chunk: async () => ({ data: "" }),
      since: async (_id, sv) => ({ state: toBase64(Y.encodeStateAsUpdate(this.doc, fromBase64(sv))), chunks: 0, token: "" }),
      apply: async (_id, update, view) => {
        this.applies++;
        if (this.fail > 0) { this.fail--; throw new Error("Runtime disconnected"); }
        Y.applyUpdate(this.doc, fromBase64(update));
        for (const other of this.views) other.remote(update, view);
        return { saved: true };
      },
    };
  }
  async session(view: string) {
    const session = new NoteSession("n1", this.bridge(), view, 5);
    await session.load();
    this.views.push(session);
    return session;
  }
  /** A phone edit arriving through sync: the backend changes and broadcasts. */
  remote(change: (text: Y.Text) => void) {
    const before = Y.encodeStateVector(this.doc);
    change(this.doc.getText("body"));
    const update = toBase64(Y.encodeStateAsUpdate(this.doc, before));
    for (const view of this.views) view.remote(update, "phone");
  }
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 20));

describe("OLIVE Notes text rules", () => {
  it("never splits a surrogate pair and normalizes line endings", () => {
    expect(textDiff("a😀b", "a😁b")).toEqual({ index: 1, remove: 2, insert: "😁" });
    expect(textDiff("x👍🏽", "x👍")).toEqual({ index: 3, remove: 2, insert: "" });
    expect(textDiff("same", "same")).toBeNull();
    expect(normalize("a\r\nb\rc\0")).toBe("a\nb\nc");
    expect(displayTitle("", "\n\n  Project Ideas \nmore")).toBe("Project Ideas");
    expect(displayTitle("Shopping", "Milk")).toBe("Shopping");
    expect(displayTitle("", "   ")).toBe("Untitled Note");
    expect(preview("", "Title\nBuild   OLIVE\nNotes")).toBe("Build OLIVE Notes");
    expect(transformIndex(5, [{ insert: "abc" }])).toBe(8);
    expect(transformIndex(5, [{ retain: 5 }, { insert: "abc" }])).toBe(5);
    expect(transformIndex(5, [{ retain: 2 }, { delete: 5 }])).toBe(2);
    expect(tooLarge("x".repeat(100))).toBe(false);
    expect(tooLarge("x".repeat(spec.limits.max_note_text_bytes + 1))).toBe(true);
    expect(findAll("İstanbul istanbul", "istanbul").length).toBeGreaterThanOrEqual(1);
  });

  it("shares one protocol definition with the Python backend", () => {
    const python = JSON.parse(readFileSync(new URL("../../olive/notes/protocol_v1.json", import.meta.url), "utf8"));
    expect(python).toEqual(spec);
  });

  it("reads bounded metadata even when a peer stores bad types", () => {
    const doc = new Y.Doc();
    doc.getMap("meta").set("title", 42);
    doc.getMap("meta").set("pinned", "yes");
    expect(readMeta(doc)).toMatchObject({ title: "", pinned: false, trashed: false });
  });
});

describe("OLIVE Notes editor binding", () => {
  it("syncs typing, paste and delete between two views", async () => {
    const backend = new FakeBackend();
    const desktop = await backend.session("desktop");
    const other = await backend.session("second-window");
    const a = new FakeArea(), b = new FakeArea();
    new TextareaBinding(a as never, desktop);
    new TextareaBinding(b as never, other);
    a.type("Desktop line 1");
    await desktop.flush();
    expect(b.value).toBe("Desktop line 1");
    b.selectionStart = b.selectionEnd = b.value.length;
    b.type("\nPasted paragraph with emoji 😀");
    await other.flush();
    expect(a.value).toBe("Desktop line 1\nPasted paragraph with emoji 😀");
    a.selectionStart = 0; a.selectionEnd = 8;
    a.type("");
    await desktop.flush();
    expect(b.value).toBe("line 1\nPasted paragraph with emoji 😀");
    expect(backend.doc.getText("body").toString()).toBe(b.value);
  });

  it("keeps the caret on the same text when a remote edit lands above it", async () => {
    const long = "x".repeat(5000) + "CARET" + "y".repeat(5000);
    const backend = new FakeBackend(long);
    const session = await backend.session("desktop");
    const area = new FakeArea();
    new TextareaBinding(area as never, session);
    area.setSelectionRange(5000, 5005); // "CARET" selected
    backend.remote((text) => text.insert(10, "REMOTE "));
    expect(area.value.slice(area.selectionStart, area.selectionEnd)).toBe("CARET");
    expect(area.scrollTop).toBe(120);
    backend.remote((text) => text.delete(0, 3));
    expect(area.value.slice(area.selectionStart, area.selectionEnd)).toBe("CARET");
    backend.remote((text) => text.insert(text.length, " tail"));
    expect(area.value.slice(area.selectionStart, area.selectionEnd)).toBe("CARET");
    expect(area.value).toBe(backend.doc.getText("body").toString());
  });

  it("undo removes only this device's typing, never the phone's", async () => {
    const backend = new FakeBackend("start");
    const session = await backend.session("desktop");
    const area = new FakeArea();
    const binding = new TextareaBinding(area as never, session);
    area.setSelectionRange(5, 5);
    area.type(" A");
    await session.flush();
    backend.remote((text) => text.insert(0, "B "));
    expect(area.value).toBe("B start A");
    binding.undo();
    await session.flush();
    expect(area.value).toBe("B start");
    expect(backend.doc.getText("body").toString()).toBe("B start");
    binding.redo();
    expect(area.value).toBe("B start A");
    area.fire("keydown", { key: "z", ctrlKey: true, metaKey: false, altKey: false, shiftKey: false });
    expect(area.value).toBe("B start");
  });

  it("does not disturb IME composition and merges remote edits afterwards", async () => {
    const backend = new FakeBackend("hello world");
    const session = await backend.session("desktop");
    const area = new FakeArea();
    new TextareaBinding(area as never, session);
    area.setSelectionRange(11, 11);
    area.fire("compositionstart");
    area.type(" にほ");                 // provisional composition text
    backend.remote((text) => text.insert(0, "REMOTE "));
    expect(area.value).toBe("hello world にほ"); // untouched while composing
    area.value = "hello world 日本";
    area.setSelectionRange(14, 14);
    area.fire("compositionend");
    expect(area.value).toBe("REMOTE hello world 日本");
    await session.flush();
    expect(backend.doc.getText("body").toString()).toBe("REMOTE hello world 日本");
  });

  it("batches a burst of keystrokes and keeps edits when saving fails", async () => {
    const backend = new FakeBackend();
    const session = await backend.session("desktop");
    const area = new FakeArea();
    new TextareaBinding(area as never, session);
    for (const character of "hello world") area.type(character);
    expect(session.saveState).toBe("saving");
    await session.flush();
    expect(backend.applies).toBe(1);
    expect(session.saveState).toBe("saved");
    backend.fail = 1;
    area.type("!");
    await session.flush();
    expect(session.saveState).toBe("retrying");
    expect(backend.doc.getText("body").toString()).toBe("hello world");
    await new Promise((resolve) => setTimeout(resolve, 600));
    await session.flush();
    expect(session.saveState).toBe("saved");
    expect(backend.doc.getText("body").toString()).toBe("hello world!");
  });

  it("refuses an oversized paste before it reaches the document", async () => {
    const backend = new FakeBackend();
    const session = await backend.session("desktop");
    const area = new FakeArea();
    let limited = 0;
    new TextareaBinding(area as never, session, () => limited++);
    area.type("z".repeat(spec.limits.max_note_text_bytes + 10));
    expect(limited).toBe(1);
    expect(area.value).toBe("");
    expect(session.text.length).toBe(0);
  });

  it("replace all is one undoable edit that keeps unrelated text", async () => {
    const backend = new FakeBackend("cat dog cat bird CAT");
    const session = await backend.session("desktop");
    const area = new FakeArea();
    const binding = new TextareaBinding(area as never, session);
    expect(binding.replaceAll("cat", "fox")).toBe(3);
    expect(area.value).toBe("fox dog fox bird fox");
    binding.undo();
    expect(area.value).toBe("cat dog cat bird CAT");
  });
});

describe("OLIVE Notes list and status", () => {
  const note = (id: string, edited: string, pinned = false) =>
    ({ note_id: id, edited_at: edited, pinned, title: "", display_title: id, preview: "", trashed: false, trashed_at: "", created_at: edited, text_length: 0, status: "ok" });
  it("sorts pinned first then recent, and holds the note being typed", () => {
    const list = [note("a", "2026-01-01"), note("b", "2026-01-03"), note("c", "2026-01-02", true)];
    expect(sortNotes(list).map((n) => n.note_id)).toEqual(["c", "b", "a"]);
    const edited = [note("a", "2026-01-09"), note("b", "2026-01-03"), note("c", "2026-01-02", true)];
    expect(stableOrder(["c", "b", "a"], edited, "a").map((n) => n.note_id)).toEqual(["c", "b", "a"]);
    expect(stableOrder(["c", "b", "a"], edited, null).map((n) => n.note_id)).toEqual(["c", "a", "b"]);
  });
  it("distinguishes local saving from sync", () => {
    const phone = { device_id: "p", name: "iPhone", state: "synced", pending: 0 };
    expect(syncLine({ available: true, peers: [] }, "saved").label).toBe("Saved locally");
    expect(syncLine({ available: true, peers: [phone] }, "saving").label).toBe("Saving…");
    expect(syncLine({ available: true, peers: [phone] }, "saved").label).toBe("Synced with iPhone");
    expect(syncLine({ available: true, peers: [{ ...phone, state: "offline", pending: 2 }] }, "saved").label)
      .toBe("Offline — changes will sync to iPhone later");
    expect(syncLine({ available: true, peers: [{ ...phone, state: "syncing", pending: 1 }] }, "saved").label).toBe("Syncing…");
    expect(syncLine({ available: true, peers: [{ ...phone, state: "error", pending: 1 }] }, "saved").tone).toBe("warning");
    expect(syncLine({ available: false, message: "Notes storage unavailable.", peers: [] }, "saved").tone).toBe("error");
    expect(syncLine({ available: true, peers: [] }, "retrying").label).toContain("Could not save locally");
  });
  it("renderer contracts are typed and strict", () => {
    const id = "123e4567-e89b-42d3-a456-426614174000";
    expect(notesSchemas["notes.open"].safeParse({ note_id: id }).success).toBe(true);
    expect(notesSchemas["notes.open"].safeParse({ note_id: "Shopping" }).success).toBe(false);
    expect(notesSchemas["notes.apply"].safeParse({ note_id: id, update: "<script>" }).success).toBe(false);
    expect(notesSchemas["notes.list"].safeParse({ view: "notes", sql: "DROP" }).success).toBe(false);
    expect(Object.keys(notesSchemas).some((name) => /sql|exec|eval|file/.test(name))).toBe(false);
  });
});
