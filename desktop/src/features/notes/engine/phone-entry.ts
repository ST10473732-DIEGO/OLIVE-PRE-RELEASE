// The phone's OLIVE Notes engine entry point (bundled into the iOS app; see
// desktop/scripts/build-notes-engine.mjs). Swift installs `OliveNotesHost`
// before evaluating the bundle and calls `OliveNotes.*` with plain strings.
import { NotesError, Replica, type Host } from "./replica";

declare const OliveNotesHost: Host;

let replica: Replica | null = null;
const current = () => {
  if (!replica) throw new NotesError("notes_unavailable");
  return replica;
};
const wrap = (action: () => unknown): string => {
  try {
    return JSON.stringify({ ok: true, value: action() ?? null });
  } catch (error) {
    return JSON.stringify({ ok: false, error: error instanceof NotesError ? error.message : "notes_unavailable" });
  }
};

const api = {
  version: "olive-notes/1",
  start: (deviceId: string) => wrap(() => { replica = new Replica(OliveNotesHost, deviceId); return true; }),
  list: (view: "notes" | "trash") => wrap(() => current().list(view)),
  create: (title: string, body: string) => wrap(() => current().create(title, body)),
  open: (id: string) => wrap(() => current().open(id)),
  close: (id: string) => wrap(() => current().close(id)),
  text: (id: string) => wrap(() => current().text(id)),
  edit: (id: string, index: number, remove: number, insert: string) => wrap(() => current().edit(id, index, remove, insert)),
  replaceText: (id: string, text: string) => wrap(() => current().replaceText(id, text)),
  rename: (id: string, title: string) => wrap(() => current().rename(id, title)),
  pin: (id: string, pinned: boolean) => wrap(() => current().pin(id, pinned)),
  trash: (id: string) => wrap(() => current().trash(id)),
  restore: (id: string) => wrap(() => current().restore(id)),
  purge: (id: string) => wrap(() => current().purge(id)),
  undo: (id: string, redo: boolean) => wrap(() => current().undo(id, redo)),
  search: (query: string) => wrap(() => current().search(query)),
  tick: () => wrap(() => current().tick()),
  status: (peer: string) => wrap(() => current().status(peer)),
  // Sync. `handle` returns the raw olive-notes/1 response for Connect frame 14.
  handle: (peer: string, raw: string) => current().handle(peer, raw),
  next: (peer: string) => current().next(peer),
  answer: (peer: string, ticket: string, raw: string) => current().answer(peer, ticket, raw),
  fail: (peer: string, code: string) => wrap(() => current().fail(peer, code)),
  disconnected: (peer: string) => wrap(() => current().disconnected(peer)),
};

(globalThis as unknown as { OliveNotes: typeof api }).OliveNotes = api;
