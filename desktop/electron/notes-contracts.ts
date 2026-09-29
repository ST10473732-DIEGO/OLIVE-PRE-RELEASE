import { z } from "zod";
// OLIVE Notes renderer contracts. Typed operations only: no SQL, paths or eval.
// Mirrors olive/notes/contracts.py (export/import paths come from main-process dialogs).
const id = z.string().uuid();
const b64 = (max: number) => z.string().max(max).regex(/^[A-Za-z0-9+/]*={0,2}$/);
const text = (max: number) => z.string().max(max).refine((v) => !v.includes("\0"));
const empty = z.object({}).strict();
export const notesSchemas = {
  "notes.list": z.object({ view: z.enum(["notes", "trash"]).optional() }).strict(),
  "notes.get": z.object({ note_id: id }).strict(),
  "notes.create": z.object({ title: text(200).optional(), text: text(200_000).optional() }).strict(),
  "notes.open": z.object({ note_id: id }).strict(),
  "notes.state_chunk": z.object({ token: z.string().regex(/^[0-9a-f]{32}$/), index: z.number().int().min(0).max(63) }).strict(),
  "notes.state_since": z.object({ note_id: id, state_vector: b64(8000) }).strict(),
  "notes.apply": z
    .object({
      note_id: id,
      update: b64(900_000),
      view: z.string().max(64).optional(),
      upload: z.object({ id: z.string().min(1).max(64), index: z.number().int().min(0).max(23), count: z.number().int().min(1).max(24) }).strict().optional(),
    })
    .strict(),
  "notes.rename": z.object({ note_id: id, title: text(200) }).strict(),
  "notes.pin": z.object({ note_id: id, pinned: z.boolean() }).strict(),
  "notes.trash": z.object({ note_id: id }).strict(),
  "notes.restore": z.object({ note_id: id }).strict(),
  "notes.purge": z.object({ note_id: id, confirmed: z.boolean() }).strict(),
  "notes.duplicate": z.object({ note_id: id }).strict(),
  "notes.search": z.object({ query: text(500), include_trash: z.boolean().optional() }).strict(),
  "notes.history": z.object({ note_id: id }).strict(),
  "notes.history_get": z.object({ history_id: id }).strict(),
  "notes.history_restore": z.object({ note_id: id, history_id: id }).strict(),
  "notes.status": empty,
};
