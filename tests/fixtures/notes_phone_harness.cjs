// Runs the committed phone bundle (NotesEngine.js) the way the iOS app does:
// in a bare JavaScript context WITHOUT crypto, TextEncoder, atob or console,
// with an OliveNotesHost whose commit() is atomic (like the Swift SQLite store).
// JSON lines on stdin: {"id", "cmd", "args"} -> {"id", "result" | "error"}.
"use strict";
const vm = require("node:vm");
const fs = require("node:fs");
const crypto = require("node:crypto");
const readline = require("node:readline");

const bundlePath = process.argv[2];
const source = fs.readFileSync(bundlePath, "utf8");
let store = { rows: new Map(), updates: [], snapshots: new Map(), purges: new Map(), peers: new Map(), search: new Map(), meta: { store_seq: 0, epoch: "" }, seq: 0 };
let failCommits = 0;
let events = [];
let context = null;

function clone(value) { return structuredClone(value); }

const host = {
  loadIndex() {
    return JSON.stringify({ rows: [...store.rows.values()], purges: [...store.purges.values()], peers: [...store.peers.values()], meta: store.meta });
  },
  loadDocument(id) {
    if (!store.rows.has(id)) return "null";
    const snapshot = store.snapshots.get(id);
    return JSON.stringify({ snapshot: snapshot ? snapshot.state : null, updates: store.updates.filter((u) => u.note_id === id).map((u) => u.payload) });
  },
  commit(raw) {
    if (failCommits > 0) { failCommits--; return false; }
    const batch = JSON.parse(raw);
    const next = { ...store, rows: new Map(store.rows), updates: [...store.updates], snapshots: new Map(store.snapshots), purges: new Map(store.purges),
      peers: new Map(store.peers), search: new Map(store.search), meta: { ...store.meta } };
    if (batch.epoch) next.meta.epoch = batch.epoch;
    if (batch.store_seq) next.meta.store_seq = batch.store_seq;
    for (const row of batch.rows || []) next.rows.set(row.note_id, clone(row));
    for (const id of batch.delete_notes || []) {
      next.rows.delete(id); next.snapshots.delete(id); next.search.delete(id);
      next.updates = next.updates.filter((u) => u.note_id !== id);
    }
    for (const purge of batch.purges || []) next.purges.set(purge.note_id, clone(purge));
    for (const update of batch.updates || []) {
      if (!next.rows.has(update.note_id)) throw new Error("foreign key: note row missing");
      if (!next.updates.some((u) => u.update_id === update.update_id)) next.updates.push({ ...update, seq: ++next.seq });
    }
    for (const peer of batch.peers || []) next.peers.set(peer.device_id, clone(peer));
    for (const row of batch.search || []) next.search.set(row.note_id, clone(row));
    for (const snapshot of batch.snapshots || []) {
      next.snapshots.set(snapshot.note_id, clone(snapshot));
      next.updates = next.updates.filter((u) => u.note_id !== snapshot.note_id);
    }
    store = next;
    return true;
  },
  search(query) {
    const needle = query.toLowerCase();
    return JSON.stringify([...store.search.values()].filter((r) => (r.title + "\n" + r.body).toLowerCase().includes(needle)).map((r) => r.note_id));
  },
  sha256(b64) { return crypto.createHash("sha256").update(Buffer.from(b64, "base64")).digest("hex"); },
  uuid() { return crypto.randomUUID(); },
  now() { return new Date().toISOString(); },
  nowSeconds() { return Math.floor(Date.now() / 1000); },
  randomBytes(n) { return crypto.randomBytes(n).toString("base64"); },
  emit(event) { events.push(JSON.parse(event)); if (events.length > 5000) events = events.slice(-2000); },
};

function boot(deviceId) {
  // Deliberately NOT exposing crypto, TextEncoder, TextDecoder, atob, btoa, console.
  const sandbox = { OliveNotesHost: host };
  sandbox.globalThis = sandbox;
  context = vm.createContext(sandbox);
  // Node adds some web globals to new contexts; remove them to match JavaScriptCore.
  vm.runInContext("for (const name of ['console','crypto','TextEncoder','TextDecoder','atob','btoa','structuredClone','queueMicrotask','setTimeout']) { try { delete globalThis[name]; } catch (e) {} }", context);
  const missing = ["crypto", "TextEncoder", "atob", "console"].filter((name) => vm.runInContext(`typeof ${name}`, context) !== "undefined");
  if (missing.length) throw new Error("sandbox leaks " + missing.join(","));
  vm.runInContext(source, context, { filename: "NotesEngine.js" });
  const started = JSON.parse(vm.runInContext("OliveNotes.start", context)(deviceId));
  if (!started.ok) throw new Error(started.error);
}

const commands = {
  boot: ([deviceId]) => { boot(deviceId); return true; },
  restart: ([deviceId]) => { boot(deviceId); return true; },
  call: ([method, ...args]) => vm.runInContext("OliveNotes", context)[method](...args),
  failCommits: ([count]) => { failCommits = count; return true; },
  events: () => { const out = events; events = []; return out; },
  stats: () => ({ updates: store.updates.length, snapshots: store.snapshots.size, rows: store.rows.size, purges: store.purges.size }),
};

readline.createInterface({ input: process.stdin }).on("line", (line) => {
  const message = JSON.parse(line);
  let reply;
  try { reply = { id: message.id, result: commands[message.cmd](message.args || []) }; }
  catch (error) { reply = { id: message.id, error: String(error && error.message || error) }; }
  process.stdout.write(JSON.stringify(reply) + "\n");
});
