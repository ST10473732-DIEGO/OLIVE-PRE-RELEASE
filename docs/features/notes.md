# OLIVE Notes

OLIVE Notes is a local-first plain-text notepad in the OLIVE desktop app and
the OLIVE phone app. Notes are saved on the device as you type and synchronize
with paired OLIVE devices over OLIVE Connect when you allow it. There is no
Save button, no account, no cloud service and no AI model involved in editing
or syncing.

Status of verification is listed at the end (§27, §28). In short: the desktop
app, the sync protocol and real Connect TLS transport are tested on Linux. The
Swift phone code is compiled and tested with Xcode, and live sync was verified
between the real Linux (CachyOS) OLIVE desktop and a physical iPhone over the
local network. The iOS Simulator was not used.

## 1. Product behaviour

- **Desktop:** the **Notes** view of the **OLIVE DrawNote** navigation space
  (between Chat and Plan; see `docs/features/draw.md`). Note
  list with search, pinned notes first, then most recently edited. Editor with
  a title field and a plain-text body. Toolbar: pin, history, duplicate,
  export as `.txt`, delete. Import `.txt`/`.md`. **Recently Deleted** view with
  Restore and Delete permanently. `Ctrl+N` new note, `Ctrl+F` find in note
  (with replace), `Ctrl+Shift+F` search notes, `Ctrl+Z` / `Ctrl+Shift+Z` /
  `Ctrl+Y` undo/redo of this device's typing. At narrow widths the list and the
  editor become two screens with a back button.
- **Phone:** **Notes** tab (screen title *OLIVE Notes*). List with search,
  pinned section, swipe to pin or delete, Recently Deleted with restore and
  permanent delete, full-screen editor with title, pin, undo/redo, share as
  text. Settings › OLIVE Notes › *Sync notes with your computer*.
- **Titles:** an explicit title wins. Without one, the list shows the first
  non-empty line, else "Untitled Note". Typing never renames a note whose title
  was set. Duplicate titles are allowed; identity is a UUID `note_id`.
- **Empty notes** are valid and are never deleted automatically.
- **Status line** separates local saving from syncing: *Saving…*, *Saved
  locally*, *Syncing…*, *Synced with …*, *Offline — changes will sync … later*,
  *Sync issue with …*, *Could not save locally · retrying*, *Notes storage
  unavailable*. "Saved" is shown only after the backend has committed the edit
  to SQLite.

## 2. Local-first architecture

```
 desktop renderer (textarea)        phone UITextView
        │ Yjs update                      │ UTF-16 edit
        ▼                                 ▼
 Electron IPC (typed notes.*)      JavaScriptCore: NotesEngine.js
        │                                 │ host.commit(batch)
        ▼                                 ▼
 NotesService (one owner thread)   NotesDatabase (SQLite, 1 transaction)
   pycrdt documents                       │
   notes.sqlite3 (WAL, FULL sync)         │
        │ durable change feed             │ durable change feed
        ▼                                 ▼
 NotesSyncEngine ◄── olive-notes/1 over OLIVE Connect frames 13/14 ──► replica engine
```

Every edit is committed locally first: the CRDT update, the note's metadata
row and its change-feed position are written in one SQLite transaction.
Only then is it announced to other views or offered to peers. The sync layer
reads the durable feed; nothing waits in memory for a network.

Desktop modules: `olive/notes/` (`document.py` CRDT adapter, `store.py`,
`service.py`, `worker.py`, `protocol.py`, `sync_engine.py`, `chat.py`,
`contracts.py`), `olive/connect/notes.py` (Connect adapter),
`olive/bridge/notes_routes.py`, `desktop/src/features/notes/`. Phone:
`mobile/ios/OLIVEMobile/Core/Notes/`, `Features/Notes/`, and
`Resources/NotesEngine.js` built from `desktop/src/features/notes/engine/`.

## 3. Note schema

A note is one Yjs document:

| Part | Content |
| --- | --- |
| `body` (Y.Text) | Plain text, LF line endings |
| `meta` (Y.Map) | `schema`, `title`, `pinned`, `trashed`, `trashed_at`, `created_at`, `created_by`, `edited_at` |

`meta` values from peers are read defensively: wrong types are ignored (for
example a non-string title reads as no title).

Desktop `notes.sqlite3` (schema v1, `PRAGMA user_version=1`):

| Table | Purpose |
| --- | --- |
| `meta` | `store_seq` (change feed counter), `epoch` (store identity) |
| `notes` | One row per live note: title, display title, preview, pinned, trashed, edited times, `change_seq`, `last_change_peer`, `status` (`ok`/`corrupt`) |
| `note_snapshots` | Compacted Yjs state + SHA-256 |
| `note_updates` | Yjs updates since the snapshot (+ origin, device, SHA-256, unique `update_id`) |
| `note_purges` | Permanent-deletion markers with their own `change_seq` |
| `note_peers` | Per peer: `acked_seq`, `peer_epoch`, last sync, last error, protocol |
| `note_history` | Local-only version checkpoints (title + text + SHA-256) |
| `note_search` | FTS5 index (title, body); a plain table with `instr` search if FTS5 is missing |

Selection, scroll position and the open note are per-device UI state and are
never synced. The phone database (`Companion/Notes/notes-v1.sqlite3`) has the
same logical tables with JSON rows written by the engine.

## 4. CRDT choice

Yjs update format v1 everywhere:

| Where | Library | Version | Licence |
| --- | --- | --- | --- |
| Desktop backend (Python) | `pycrdt` (Rust `yrs`) | 0.14.6 (pinned in `requirements.txt`) | MIT |
| Desktop renderer | `yjs` | 13.6.33 (exact, `desktop/package.json`) | MIT |
| Phone (JavaScriptCore) | same `yjs` 13.6.33 + `lib0` 0.2.119, bundled | `NotesEngine.js`, 112 KB | MIT (`NotesEngine.LICENSES.txt`) |

## 5. Why

- OLIVE's backend is Python, the renderer is TypeScript and the phone is Swift.
  Yjs is the only mature text CRDT with maintained implementations for all
  three paths: `pycrdt` is maintained by the Jupyter project, and `yjs` runs
  unmodified in iOS's system JavaScriptCore (no third-party binary framework).
- Automerge was considered; its Python binding is at 0.1.x. A native Swift Yjs
  binding requires a Rust binary framework, which could not be built or checked
  here.
- Binary compatibility between `pycrdt` and `yjs` is tested with Unicode text,
  randomized edits and the phone bundle (see "Tested flows").
- Important detail found in testing: `pycrdt`'s `Text` indexes by **UTF-8 byte
  offsets**. All Python edits go through `NoteDocument.splice`, which converts
  code-point positions to byte offsets. Without it, edits in non-ASCII text land
  in the wrong place and can split a character.

## 6. Desktop editor architecture

The renderer keeps a Yjs replica of the open note (`session.ts`). A plain
`<textarea>` is bound to it (`binding.ts`):

- Local input becomes one minimal edit (origin `olive-local`), batched for
  about 30 ms, and sent as a Yjs update via `notes.apply`. Large updates are
  split into parts below the 1 MiB bridge limit.
- Remote updates arrive as `notes.update` events and are applied with
  `setRangeText(..., "preserve")` operation by operation, so the caret,
  selection and scroll position stay on the same text.
- During IME composition the textarea is not touched; remote edits are queued
  and merged when composition ends.
- Undo/redo uses a Yjs `UndoManager` that tracks only this device's origin, so
  remote typing is never undone locally. Electron's Edit menu and the keydown
  handler are de-duplicated so one `Ctrl+Z` undoes once.
- Paste inserts plain text only. Oversized pastes are refused before they reach
  the document.
- Several windows can have the same note open: the backend is the single owner
  and broadcasts updates; each view ignores only its own echo.

## 7. Phone editor architecture

The phone runs the same engine code in JavaScriptCore (`NotesEngineHost`).
Storage is `NotesDatabase` (SQLite via the system library, iOS Data Protection
*complete until first user authentication*, excluded from backup like other
OLIVE companion data). `NoteTextView` wraps `UITextView`: each change becomes
one UTF-16 range edit (NSString and Yjs share UTF-16 indices); remote and undo
edits arrive as UTF-16 deltas applied to the text storage with the selection
transformed. Marked (IME) text is not interrupted: queued remote deltas are
merged when composition ends, and the composed change is mapped through them.
UIKit's own undo registration is disabled; the note's undo uses the engine's
local-only undo. The title field shows renames that sync in while the note is
open and writes a title only when the user edited it, so leaving the editor
never reverts another device's rename.

## 8. Sync protocol (`olive-notes/1`)

Connect frame types **13** (request) and **14** (response), 512,000-byte
limit. The canonical definition (limits, operations, statuses, errors) is
`olive/notes/protocol_v1.json`; the TypeScript engine uses a copy that a test
keeps identical.

Request envelope: `protocol_version`, `request_id`, `source_device_id`,
`target_device_id`, `operation`, `arguments`, `timestamp`, `expires_at`
(lifetime ≤ 120 s, 5 s future tolerance). Response: `completed` with `result`,
or `rejected` with a fixed `error` code.

| Operation | Arguments | Result |
| --- | --- | --- |
| `hello` | `versions` | `versions`, `epoch` |
| `sync` | `epoch`, `entries[]` (`note_id`, `seq`, `sv`, `purged`, optional `update`) | `epoch`, `results[]` (`note_id`, `status`, `sv`, optional `error`) |
| `chunk` | `epoch`, `transfer_id`, `note_id`, `seq`, `sv`, `index`, `count`, `total_bytes`, `sha256`, `data` | `epoch`, `status`, `sv` |

Statuses: `applied`, `current`, `needs`, `purged`, `rejected`, `partial`.
Byte fields are base64 and are decoded with explicit bounds before any CRDT
code sees them. Unknown versions, operations or fields are rejected; nothing is
deserialized into objects or executed.

| Limit | Value |
| --- | --- |
| Frame | 512,000 bytes |
| Entries per `sync` | 64 |
| Inline update | 200,000 bytes; 400,000 per request |
| Chunk / whole transfer | 200,000 / 8,000,000 bytes; 2 transfers per peer; 60 s idle |
| State vector | 4,096 bytes |
| Note text | 1,500,000 UTF-8 bytes |
| Notes per device | 10,000 |
| Rate | 3,000 Notes frames per peer per minute (separate Connect budget) |

## 9. Initial sync

A newly allowed peer has `acked_seq = 0`. The sender offers its change feed in
pages of up to 64 entries (note ID, feed position, state vector). The receiver
answers with its own state vectors. The sender then sends each note's diff
(chunked above 200 KB). A note is created on the receiver only when a complete
update is applied, in one transaction, so an interruption never leaves a
half-created note. `acked_seq` advances only over entries the peer confirmed,
so a restarted initial sync resumes safely with no duplicates.

## 10. Reconnect

On a new Connect channel the dialling side (and the phone) sends `hello`, which
exchanges store epochs. Each side then pushes only what changed after the
peer's `acked_seq`, as state-vector diffs. Diffs always carry the full delete
set, because deletions are invisible in state vectors.

## 11. Offline edits

Edits are committed locally and stay in the change feed. When the peer returns
they are sent automatically; no user action is needed. The phone syncs while
OLIVE is in the foreground and connected (see §25).

## 12. Deduplication

CRDT updates are idempotent: applying one twice changes nothing and produces no
event. A lost answer means the sender resends; the receiver's state vector
answer tells it what is already there. Updates stored from peers use a
content-derived `update_id`, so the same update is stored once.

## 13. Conflict and convergence semantics

Text merges automatically by the Yjs algorithm; there is no timestamp winner
and no "choose a version" dialog for ordinary concurrent typing.

- **Same position:** both insertions are kept, in an order that is the same on
  every device (tested: "Hello beautiful amazing world"-style results converge
  exactly).
- **Delete vs edit:** text inserted inside a range another device deleted is
  kept; the deleted text stays deleted (tested result: `Keep this. very End.`).
- **Metadata** (`title`, `pinned`, `trashed`): each key is a Yjs map entry. A
  later write that saw an earlier one replaces it. Concurrent writes resolve
  deterministically by Yjs client order, so every device shows the same title
  and nothing oscillates.
- **Echo suppression:** a change that came from peer P is not sent back to P
  if everything before it had been delivered to P. Otherwise the diff is sent
  (harmless) so nothing can be lost.

## 14. Delete and tombstones

*Delete* moves a note to **Recently Deleted** (`trashed = true`), which syncs.
An old offline copy cannot undo this: its older value of `trashed` was already
superseded. There is no automatic purge; notes stay in Recently Deleted until
you delete them permanently.

## 15. Restore

Restore sets `trashed = false` on the same note (same `note_id`, same document)
and syncs like any edit.

## 16. History

History is local and private (not synced). Checkpoints are made when editing
pauses for 45 seconds (at most one per 5 minutes), on rename, before deleting,
and before and after a restore. Each note keeps up to 100 checkpoints. Entries
show the time, the device names that edited in that period (from Connect's
paired-device names; identity comes from the authenticated device ID), and the
reason. **Restoring a version is a new edit** (minimal diff to the old text),
so other devices receive it normally.

## 17. Compaction

After 200 logged updates a note's log is folded into a snapshot with a
lossless Yjs merge. The merge is checked (text, state vector and metadata must
match a full replay) before the log rows are deleted in the same transaction.
A stale device can still catch up because peers diff their current state
against its state vector. Measured: 10,000 single-character edits produced
10,001 log rows / 242,828 update bytes; after compaction, one snapshot of
115,833 bytes.

## 18. Search

Local only. Desktop: SQLite FTS5 over title and body (diacritics folded), plus
substring matching for other scripts and partial words. The index is updated
about 0.8 s after changes and before every search, not on every keystroke.
Phone: substring search over a local index table, refreshed by `tick()`
(about 1 s after edits, and when the app goes to the background). A note whose
text is not yet indexed is marked in its stored row, so an index update lost to
a crash or forced termination is redone on the next start. Queries never
leave the device.

## 19. Connect integration

Notes uses the existing C3 mutually authenticated TLS 1.3 channel; no new
socket, listener, relay or cloud path. `olive/connect/notes.py`:

- receives frame 13 only on an authenticated channel; the message's device
  fields must equal the channel's identity;
- pushes one pump per peer, triggered by local changes (about 40 ms batching),
  by the peer coming online, by a permission turning on, or by the peer
  contacting us;
- retries the **transport** with backoff (0.5, 1, 2, 4, 8 s); edits are never
  retried because they are already durable.

Compatibility: an older OLIVE drops a connection on an unknown frame type. So
the phone first sends an optional read-only probe (`notes`) on the Remote AI
channel. It needs only the paired, authenticated channel, not Remote AI
permission, and reports `sync.notes` Allow/Off. An older desktop drops the
channel on it; after two consecutive probe failures the phone stops probing
until OLIVE is relaunched (or the computer is re-selected) and Notes stays
local, so an older desktop sees at most two reconnects. A single failure, such
as Wi-Fi returning mid-probe, does not turn Notes off. A desktop never sends
Notes frames to a phone that has not sent one first; desktops that dial a
desktop speak first. The phone learns that Notes sync was switched to Allow or
Off within about 15 seconds (the existing Connect status interval).

## 20. Authentication

Only paired, non-revoked devices whose certificate matches the stored identity
can exchange Notes. Identity comes from the TLS channel, never from message
content. Revoking a device closes its channel; Notes then stops sending to it
and refuses its requests. Local notes on either side are not touched (there is
no remote wipe).

## 21. Device permissions

- Desktop: Devices › *device* › Permissions › **Notes sync**: **Off** (default)
  or **Allow**. *Ask* is not offered, because live sync cannot wait for an
  approval on every keystroke. Notes access is separate from Remote AI, Files
  and Chat sync.
- Phone: Settings › OLIVE Notes › *Sync notes with your computer* (default on).
  Nothing is exchanged unless the computer also allows Notes sync for this
  phone.

## 22. Privacy and security

- Transport: Connect's mutually authenticated TLS 1.3 on the local network.
  This is authenticated encryption **in transit**; it is not end-to-end
  encryption through a relay (there is no relay), and it does not protect a
  compromised device.
- At rest: desktop notes are in `notes.sqlite3` in the OLIVE profile, created
  user-only (0600 on Linux), protected by your OS account. OLIVE does not
  encrypt it. Phone notes use iOS Data Protection. Notes are included in OLIVE
  backups (`notes` component); restoring a backup gives the notebook a new
  epoch so paired devices resend what it may lack.
- Logs contain note IDs, sizes and error categories, never note text.
- Note text is data. It cannot grant permissions, run commands or trigger
  actions. Rendering is plain text (no HTML).
- Snapshot and update checksums (SHA-256) detect corruption. A corrupt note is
  marked, shown as "Note data corrupted", kept on disk for recovery and never
  sent to peers. A newer or unrecognized database is left untouched and shown
  as *Notes storage unavailable*.

## 23. Chat integration

Literal requests are handled by a deterministic grammar (`olive/notes/chat.py`)
before research and desktop routing, with or without a model:

- "Open OLIVE Notes" / "Open my notes" → opens OLIVE DrawNote › Notes (never an app
  launch; "Open Kate" stays desktop navigation);
- "Open my Shopping note", "Read my Shopping note";
- "Create a note called Ideas and add 'OLIVE Notes'";
- "Add 'buy milk' to my Shopping note" (one CRDT append; it syncs);
- "Search my notes for RaceDay" (local only);
- "Rename my X note to Y", "Restore my X note";
- "Delete my X note" (to Recently Deleted; asks by default);
- "Permanently delete my X note" (always asks for confirmation);
- "Summarise my X note" → the model receives the note as clearly marked
  untrusted data. The answer records provenance (note ID, title, revision
  hash). Summaries run on This device only: not with Remote AI, NOW or web
  research.

Titles resolve by exact match (case-insensitive). If several notes share the
title, OLIVE lists them and asks which one; it never guesses. Notes are never
added to Chat automatically. Typed tools `notes.list/read/search/create/append/
replace/rename/delete/restore` exist for the agent registry (writes require
confirmation there) and are classified for Owner Mode. Permission keys:
`notes.read` and `notes.write` allow, `notes.delete` asks.

Not done in this milestone: an "Attach → Note" item in the Chat composer. The
provenance and evidence path it would use exists (`note_evidence`), but the
picker UI was deferred.

## 24. Clipboard

Out of scope. Copying text does not change a note, so there is nothing to
sync. OLIVE Notes does not monitor, store or sync the clipboard. Any future
"OLIVE Clipboard" must be a separate feature with its own permission, because
clipboards often hold passwords, tokens and codes.

## 25. Phone background behaviour

While OLIVE Mobile is in the foreground and connected, synchronization is
near-real-time (verified with a physical iPhone and the Linux desktop: desktop
typing appeared on the phone keystroke by keystroke). When iOS suspends OLIVE,
the Connect socket is closed (existing C9.3 behaviour). Edits stay in the
phone's durable change feed and synchronize when the app resumes and
reconnects (verified: 4 minutes in the background across a desktop restart,
then catch-up on resume). There is no background polling and no claim of
real-time background sync. Offline edits are shown as pending ("Offline — N
change(s) will sync later"), also after a relaunch before Connect is back.

## 26. Known limitations

- **iOS Simulator: NOT VERIFIED** (no simulator runtime was installed; all iOS
  runtime testing used a physical iPhone).
- Sync is local-network only (OLIVE Connect over Bonjour/LAN); there is no
  Internet-wide or relay sync.
- Search on the phone folds case only for ASCII ("Café" finds "café"; "CAFÉ"
  does not).
- An update that arrives before the one it depends on is kept in memory only;
  the phone answers `needs`, so after a restart the sender resends it (tested).
  The desktop stores such updates durably.
- Desktop history is local; the phone has no history view in v1.
- Chat "attach a note" picker: deferred (see §23).
- Rich text, images, folders/tags, sharing with other people, cursor presence
  and clipboard sync are not part of v1.
- Permanent deletion wins over offline edits made to that note on another
  device (the note had to be in Recently Deleted first).
- A peer refusing a note (for example "note too large") does not block other
  notes; the note is retried when it changes again.

## 27. Tested flows

| Area | Evidence |
| --- | --- |
| Storage, CRDT adapter, history, search, compaction, corruption, migration refusal, file permissions, large notes (100 KB, 1 MB), Unicode | `tests/test_notes_core.py` |
| Two/three-device sync over a simulated Connect with real protocol bytes: create/type/paste/delete both ways, rename, pin, trash/restore, duplicates, dropped ACK, out-of-order, offline, restarts before ACK, initial and partial initial sync, revoked peer, unsupported/malformed/oversized messages, 40-round randomized convergence, tombstones, compaction + stale peer, 1 MB chunked, epoch reset, no echo | `tests/test_notes_sync.py` |
| Real OLIVE Connect TLS loopback: Off by default, live sync both ways after Allow, malformed frame, revocation, no Notes frames to a peer that has not spoken Notes | `tests/test_connect_notes.py` |
| The phone engine bundle in a bare JS context (no crypto/TextEncoder/atob/console) against the Python desktop engine: create/edit both ways with live deltas, offline convergence, 25-round randomized Unicode convergence, restart with pending edits, failed commit not saved, 700 KB chunks both ways, purge tombstone, local-only undo, search, request validation | `tests/test_notes_phone_engine.py` |
| Chat grammar, CRDT append, duplicate titles, summary provenance, no web queries, no memory extraction, confirmations, permission Off | `tests/test_notes_chat.py` |
| Renderer binding: two views, caret on a 10,000-character note, local-only undo, IME composition, batching and retry, oversized paste, replace-all | `desktop/tests/notes.test.ts` |
| Real Electron app, isolated profile: create, type, undo, rename, navigate, live Chat append with caret kept, search, pin, delete/restore, history, restart | `desktop/tests/e2e/notes.spec.ts` |
| The real Swift JavaScriptCore host and SQLite store (`check-connect-interop.sh`, `OLIVE_NOTES_SWIFT_HARNESS`) running all of the above phone-engine tests, plus: proof of the Swift runtime and its SQLite file, UTF-16/code-point positions for accents, combining marks, skin-tone/ZWJ emoji, flags, CJK, Arabic/Hebrew and astral characters both ways, lost ACK, out-of-order and duplicate updates across a restart, metadata both ways, search after restart, note text as data, corrupt bytes kept and never sent, newer schema left untouched | `tests/test_notes_phone_engine.py` |
| Swift unit tests on a physical iPhone: engine, restart, undo, UITextView bridge (remote edits in place with caret/selection kept, IME composition, local-only undo), oversized paste, purge after restart, ASCII search folding, Data Protection and backup exclusion, probe and permission gating, pending count offline, 100 KB / 1 MB notes | `mobile/ios/OLIVEMobileTests/NotesTests.swift` |
| iPhone UI (opt-in `OLIVE_NOTES_UI_ACCEPTANCE=1`, isolated profile): create, type, undo/redo, pin, rename, search, delete/restore, relaunch | `NotesUIAcceptanceTests` in `mobile/ios/OLIVEMobileUITests/ShellUITests.swift` |
| Live Linux desktop ↔ iPhone (opt-in `OLIVE_NOTES_LIVE_ACCEPTANCE=1` driving the phone; desktop by hand) | `NotesLiveAcceptanceTests`, see §28 |

Measured on the development machine: simulated in-process sync median about
3 ms from edit to durable remote apply; real Connect TLS loopback median about
55 ms (including the 40 ms batching). These are diagnostics, not guarantees.

On a physical iPhone (engine to engine on the phone, no network): a
105 KB note opened in about 36 ms and took about 6 ms per keystroke; a 1.05 MB
note opened in about 260 ms, about 50 ms per keystroke, and synced in chunks in
about 1.2 s.

## 28. Physical iPhone and Linux desktop acceptance

Verified with Xcode 27.0, Swift 6.4, a physical iPhone and the real
OLIVE desktop on CachyOS Linux over the same Wi-Fi (OLIVE Connect, existing
pairing). Phone actions were driven by `NotesLiveAcceptanceTests`; desktop
actions were performed by hand. Results:

- Notes sync Off: a phone note and a later phone edit did not reach the
  desktop; after Allow both arrived (the phone showed "Synced" within about 30
  seconds, bounded by the 15-second status interval).
- Desktop → phone: typing, multi-line paste and line deletion appeared in the
  open phone note without reopening it, keystroke by keystroke.
- Phone → desktop: typed lines and a deleted word appeared in the open desktop
  note live.
- Caret: remote inserts above the caret kept it on the same text on both sides.
- Undo: phone Undo removed only the phone's text; desktop Ctrl+Z only desktop
  text.
- Pin/unpin and rename both ways; a desktop rename while the note was open on
  the phone was not reverted.
- Search found a note online and offline on the phone.
- Offline on both sides (desktop network off), then reconnect: "Coffee" and
  "Chicken" both kept; same-position inserts kept both words in the same order;
  text inserted inside a range deleted on the other device was kept (Yjs
  semantics); both devices ended with identical text.
- Delete on the phone → desktop Recently Deleted → Restore on the desktop →
  restored on the phone (same note ID).
- A note permanently deleted on the desktop while the phone held a stale,
  edited copy was not resurrected on either device.
- Phone edit while the desktop was unreachable, forced termination, relaunch,
  reconnect: the edit reached the desktop exactly once.
- Desktop restart while the phone was in the background for 4 minutes: the
  note survived and the phone caught up on resume.
- A 102 KB note pasted on the desktop arrived complete on the phone; a phone
  edit at its end synced back.
- Desktop logs contained none of the synthetic note text.
- Device revocation was not repeated on the physical pairing (covered by the
  automated Connect tests).
