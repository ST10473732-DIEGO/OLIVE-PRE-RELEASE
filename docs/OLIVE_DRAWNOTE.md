# OLIVE DrawNote

OLIVE DrawNote is one section of OLIVE Desktop and of OLIVE for iPhone, with
two sub-applications:

```
OLIVE DrawNote
 ├── Notes  — the existing OLIVE Notes (unchanged; syncs with the phone)
 └── Draw   — OLIVE Draw: a manual Paint-style canvas with image import and
              cross-device sync (desktop and iPhone)
```

Draw is a normal local application. It works with Ollama, ComfyUI and
VoiceStudio stopped and no model loaded, and never involves the model residency
manager. REIMAGINE remains the AI image generator; Draw is a manual canvas and
Chat has no pixel or stroke authority over it.

**Status of sync.** Draw sync is implemented on the desktop and on the iPhone
(see [OLIVE Draw on iPhone](#olive-draw-on-iphone)). Verified: desktop ↔ desktop
over OLIVE Connect TLS; a physical iPhone ↔ a Mac test host running the
production Python Connect/Draw services over real TLS on the LAN; and a physical
iPhone ↔ the user's CachyOS desktop in both directions (live strokes, local-origin
Undo/Redo, image transfer, offline + force-quit + desktop restart, drawing
creation). Completed drawing edits synchronize near-real-time (one completed
stroke is one unit); individual touch or pointer points are not streamed.

## Product structure and routing

- The navigation row reads **OLIVE DrawNote**, a multi-view *space* (like Plan,
  Library and Build): `{ id: "drawnote", routes: ["notes", "draw"] }` in
  `desktop/src/navigation/features.ts`, shown as **Notes | Draw** tabs.
- Route ids stay `notes` and `draw`: every existing Notes link (Chat
  `notes.navigate`, Home hand-offs, palette, search) still works and lands on
  DrawNote › Notes. No persisted route migration is needed.
- DrawNote reopens the section last used on this device (renderer preference,
  never synced). Chat requests that name Notes or Draw override it.
- Notes and Draw stay mounted once visited, so switching keeps the open note,
  caret and CRDT session, and the open drawing, zoom and history.

### Notes preservation

Nothing in `olive/notes`, `notes.sqlite3`, `olive-notes/1`, the Notes CRDT,
Connect frames 13/14 or the phone Notes engine/store changed. On the phone the
Notes tab became **OLIVE DrawNote** with a Notes | Draw switch; the Notes screens
themselves are unchanged apart from the section switch and title. Notes is wrapped in
the same `SpaceSlot` provider as other multi-view pages (its status and actions
appear in the DrawNote header). The phone app keeps calling the product Notes.

### Chat routing

`olive/draw/chat.py` is a bounded, literal grammar checked before the Notes
grammar and before desktop/app routing:

| Request | Result |
| --- | --- |
| "Open OLIVE Draw", "Open Draw", "Go to Draw", "Open my drawings" | DrawNote › Draw |
| "Open DrawNote and go to Draw" / "… go to Notes" | that section |
| "Open OLIVE DrawNote" | last-used section |
| "New drawing [called …]" | an empty 1920 × 1080 drawing, opened |
| "Open my "Plan" drawing" / "Open drawing called Plan" | exact title; duplicates are asked about |
| "List my drawings" | titles and sizes only |

Whole-message matches only ("draw a conclusion", "Draw a cat", "Open LibreOffice
Draw" are not Draw requests). No model is involved. Chat cannot import images:
importing is a manual action with the system file dialog.

## Architecture

| Layer | File |
| --- | --- |
| Document schema + limits (shared, byte-identical copies) | `olive/draw/drawing_schema.json`, `desktop/src/features/draw/drawing_schema.json` |
| Record/operation validation | `olive/draw/document.py`, `desktop/src/features/draw/model.ts` |
| Replica rules (materialization) | `olive/draw/records.py`, `desktop/src/features/draw/replica.ts` |
| Replica conformance fixture (shared) | `olive/draw/conformance_v1.json` (+ renderer copy) |
| Storage (store schema 2, migration) | `olive/draw/store.py` (`drawings.sqlite3`) |
| Service (library, edits, undo, assets) | `olive/draw/service.py`, `olive/draw/assets.py` |
| Bridge contract / routes | `olive/draw/contracts.py`, `olive/bridge/draw_routes.py`, `desktop/electron/draw-contracts.ts` |
| Sync protocol + engine | `olive/draw/protocol_v1.json`, `olive/draw/protocol.py`, `olive/draw/sync_engine.py` |
| Connect adapter | `olive/connect/draw.py` (+ frames in `network_wire.py`/`network.py`) |
| Import (main) / Export (main) | `desktop/electron/main/file-actions.ts` (`draw-import-image`, `draw-export`) |
| Renderer: session, assets, canvas, page | `session.ts`, `assets.ts`, `render.ts`, `CanvasView.tsx`, `Draw.tsx` |

## Replicated Draw model

### What the single-editor model was (store schema 1)

The first version stored an ordered operation log with a history head: the
picture was `ops[0:head]`, Undo moved the head back, and a new edit truncated the
redo branch. Operation ids were 12 random hex characters; order was the log
index; erase/clear/background depended on that index; saves carried
`base_revision` and a second window got a save conflict. That model cannot merge
two devices' offline edits: two logs with different content at the same index
have no correct merge, and a truncating Undo on one device would delete another
device's work.

### What it is now (store schema 2)

A drawing is a **grow-only set of immutable records**:

```
record = { record_id, drawing_id, device, lamport, kind, at, body }

create      {width, height, background, title, created_at}   once per drawing
op          one drawing operation; body.id == record_id
visibility  {target, hidden}   Undo/Redo, only by the target's own device
meta        {field: "title" | "trashed", value}
```

- **Operation ids:** `record_id` is 128 random bits (32 hex), chosen by the
  editing view, so a retried save is recognised and never applied twice.
  `device` is the authenticated Connect device id of the device that made it.
- **Order:** every replica sorts operations by `(lamport, device, record_id)`.
  `lamport` is a Lamport clock per drawing: a new record gets `max(seen) + 1`,
  so anything drawn after seeing an edit sorts after it; concurrent edits are
  ordered by device id, then record id. Wall-clock time (`at`) is display only
  and never decides order or conflicts. Arrival order never matters.
- **Picture:** visible operations replayed in that order. Clear erases what is
  before it in the order; the eraser is an operation in the order
  (`destination-out`); background is the last visible background operation.
- **Metadata:** `title` and `trashed` are last-writer registers by the same
  order (deterministic, no oscillation).
- **Permanent deletion:** a tombstone per drawing; it beats every record.

**Why this and not Yjs.** Notes uses Yjs because text needs sequence CRDT
merges inside a document. Draw operations are immutable whole objects that are
only ever appended, so the only questions are "which set" and "which order".
A grow-only set with a Lamport total order is the textbook answer (a CmRDT
G-Set with LWW registers): convergence follows because every replica's state
is a pure function of its record set, and the set union is commutative,
associative and idempotent. It keeps records small, plain JSON in SQLite rows
(cheap deltas: one stroke is one row and one ~0.7 KB message), is trivial to
implement in Swift, and supports persistent local-origin undo, which Yjs's
in-memory UndoManager does not. The rules are specified in
`olive/draw/records.py` and `replica.ts` and checked by a shared conformance
fixture (both implementations, every scenario, 12 random arrival orders).

### Local-origin undo and redo

Undo acts on **this device's own edits**. The device keeps an Undo and a Redo
stack (local table `draw_history`, never synced, survives restart). Undo pops
this device's latest still-visible operation and records a `visibility`
(`hidden: true`) record; Redo records `hidden: false`. A visibility record from
any device other than the operation's author is ignored by every replica. So:

```
Desktop: red   Phone: blue   Desktop: green   → Desktop Undo hides green only.
```

Remote edits arriving between Undo and Redo do not affect Redo. A new local edit
clears this device's Redo stack. Two windows on one desktop share the device's
stacks. Undoing a Clear reveals what it hid; undoing an image import removes it.

### Concurrent edits (all deterministic, all converge)

| Situation | Result on every replica |
| --- | --- |
| A and B draw offline | both strokes kept; order by (lamport, device, id) |
| A erases where B draws | both kept; the later one in the order wins visually |
| A clears while B draws | both kept; B's stroke survives iff it sorts after the Clear; Undo of the Clear shows everything |
| A and B change background | the later background operation in the order |
| A and B rename | the greater meta record (same order) |
| A trashes, B restores | the greater meta record |
| A purges, stale B edits | purged everywhere; B's records are dropped and B purges too |

"Later in the order" is a pure function of the records, never of packet arrival.

## Storage (store schema 2)

`drawings.sqlite3` in the profile (0600 on POSIX, WAL, `synchronous=FULL`,
`PRAGMA user_version = 2`):

```
meta(store_id, epoch, feed_seq)
drawings            materialized view: title, size, background, trash, counts, clock, last change
draw_records        every record (seq = local feed position, record_id UNIQUE, sort_key, source peer)
draw_visibility     winning visibility per operation
draw_history        this device's Undo/Redo stacks (local only)
draw_purges         permanent-deletion tombstones (with feed seq)
draw_assets         image bytes, content-addressed by SHA-256
draw_wanted         assets referenced by an operation but not yet here
draw_peers          per-peer cursor (acked_seq), peer epoch, last sync
draw_thumbnails     local preview cache (never synced)
```

Every change is one transaction. A record insert is idempotent and
materialization is order-independent (tested by replaying fixtures in random
orders against fresh stores).

### Migration from store schema 1

On first open, a SQLite backup copy of the v1 file is written next to it
(`drawings.sqlite3.store-v1-<timestamp>.bak`), then in one transaction the v1
tables are renamed `legacy_v1_*` (kept, not deleted) and each v1 drawing becomes
records made by this device: its operations in their old order (ids derived
deterministically), the redo branch as hidden operations, the same Undo/Redo
stacks, trash state and thumbnail. Opening again does not migrate again. A
newer or unrecognised database is left untouched ("Drawing storage unavailable").

### Schema versions (separate on purpose)

| Version | Value | Meaning |
| --- | --- | --- |
| Document schema | 1 or 2 per drawing | v1: stroke/erase/clear/background; v2 adds `image`. A drawing becomes v2 only when an image operation is added; opening never rewrites it. |
| Store schema | 2 (`user_version`) | SQLite layout above; v1 is migrated as described. |
| Sync protocol | `olive-draw/1` | Connect frames 15/16; peers must support document schemas 1 and 2. |

## Autosave

No Save button. A completed stroke renders at once (pending, on top) and is sent
immediately as `draw.append {drawing_id, op}`; the backend assigns the next
Lamport value, commits, and announces a feed position. One request is in flight
at a time; a failed append is retried with the same id (idempotent); an edit the
backend can never accept (size limit, trashed drawing) is dropped with its
message. The status bar shows **Saving…**, **Saved locally** or **Could not save
drawing**. Every open view pulls `draw.since {drawing_id, after}` when a
`draw.records` event arrives, so other windows and other devices update live.

### Crash durability

Completed strokes are committed within milliseconds of pointer-up. Tested: a
writer process `os._exit`s after 25 appends (all 25 present, integrity ok), and
the Electron app is SIGKILLed after drawing (strokes present on relaunch). A
stroke still in progress (pointer down) at the instant of a crash is lost. The
sync outbox is the durable feed plus per-peer cursors, so unsent edits survive a
crash and resume on reconnect.

## Image import

**Draw → Import image → choose PNG/JPEG → the image appears centred.** It is
part of the drawing: autosaved, synced, exported, duplicated and backed up. The
drawing owns its own copy; deleting or moving the original file changes nothing.

### Flow and validation

1. The renderer asks for `draw-import-image`; the **Electron main process** shows
   the system open dialog (PNG/JPEG filter), reads the chosen file (≤ 40 MB,
   bounded read), decides the type **from the bytes** (PNG or JPEG signature;
   the extension is ignored, so a PNG named `.jpg` imports as PNG and SVG is
   refused), and reads the header dimensions (≤ 16384 per side, ≤ 50 million
   pixels) before any decoder runs. The renderer receives bytes, never a path.
2. In the **sandboxed renderer**, Chromium decodes the image with its EXIF
   orientation applied, converts it to sRGB and re-encodes it at the size it will
   occupy on the canvas: PNG for PNG sources (lossless, transparency kept), JPEG
   quality 95 for JPEG sources. Re-encoding drops every metadata block — EXIF,
   GPS location, text chunks, ICC profile (pixels are already sRGB).
3. The canonical bytes are uploaded in ≤ 450 KB chunks (`draw.asset_upload`);
   the **backend** checks size (≤ 48 MB), type, header dimensions (≤ 8192 per
   side, ≤ 33,554,432 pixels — the canvas limits), structure (Pillow `verify`
   with its decompression-bomb guard) and that the SHA-256 equals the asset id,
   then stores it.
4. An `image` operation is appended: `{type: "image", id, asset_id, x, y,
   width, height, opacity}` — only the hash and geometry, never bytes or a path.

### Placement and rendering

Natural size and centred when it fits; otherwise scaled down (aspect kept) to fit
within 90 % of the canvas and centred; small images are never upscaled. The
image is drawn on the drawing layer at its document rectangle **in operation
order**: strokes drawn after it cover it, an eraser used after it erases it, and
Clear removes it — exactly like ink. Export, thumbnails and every replica use the
same renderer, so results match (verified pixel-exact in PNG exports).
Orientation is baked into the stored asset; rendering ignores any EXIF, so every
device shows the same orientation.

### Asset store

- Content-addressed: `asset_id = SHA-256(bytes)`. Importing identical bytes
  twice stores them once; duplicating a drawing reuses the asset.
- Stored as SQLite blobs in `drawings.sqlite3` (`draw_assets`): atomic with the
  records that reference them, included in backups automatically, and no file
  paths to validate or clean up.
- **Retention policy:** assets are never deleted when a drawing is deleted or
  purged (an asset may be used by another drawing, a trashed drawing, a copy or
  a device that has not synced yet). This version keeps unreferenced assets
  rather than risk deleting needed data; a reference-aware collector is future
  work.
- An operation whose asset is not here yet shows a labelled **"Image arriving…"**
  frame (never exported, never part of the drawing); export waits (it refuses
  with a clear message until the asset arrives); the thumbnail waits too.

### REIMAGINE preparation

`DrawService.ingest_trusted_image(path)` normalizes an image file that OLIVE
itself produced (orientation, sRGB, metadata removed, PNG) into an asset. It is
not wired to any UI or Chat action in this milestone.

## Draw sync over OLIVE Connect

### Capability and permission

- `sync.draw`, separate from `sync.notes`, **Off by default** for every device.
  Devices › device › Permissions shows **Draw sync: Off / Allow** (no Ask — live
  sync cannot stop to ask per stroke) and a status line: Synced, Syncing,
  Offline · edits wait on this computer, Pending N edits / N images arriving,
  Not supported by this device's OLIVE version.
- Allowing Notes never allows Draw. Turning Draw Off or revoking the device stops
  delivery immediately; local drawings stay.

### Protocol: olive-draw/1 on Connect frames 15/16

Strict JSON envelopes (like olive-notes/1): `protocol_version`, `request_id`,
`source_device_id`, `target_device_id`, `operation`, `arguments`, `timestamp`,
`expires_at`. Frames are ≤ 512 KB. Unknown versions, operations or fields are
rejected. The authenticated TLS channel supplies the peer; message device fields
must match it; `sync.draw` must be Allow on the receiver.

| Operation | Arguments | Result |
| --- | --- | --- |
| `hello` | versions, schemas | versions, epoch, schemas, wants |
| `sync` | epoch, entries (≤ 256, ≤ 400 KB): `{seq, record}` or `{seq, purge}` | epoch, per-entry status (applied / duplicate / purged / rejected), wants |
| `asset` | epoch, transfer_id, asset_id, mime, width, height, total_bytes, count, index, data (≤ 256 KB) | epoch, status (partial / stored / exists / rejected) |

`wants` is the receiver's durable list of asset ids it needs (≤ 32).

### Durable feed, delivery and dedup

Every stored record (made here or received) and every tombstone gets a local
feed position. For each peer the device stores `acked_seq`. A pump sends the
feed after it in bounded batches; the receiver inserts each record idempotently
in one transaction; the cursor then advances. A lost answer means a resend and
the records answer `duplicate`; a restart before the answer resends from the
durable cursor. Records received from a peer are forwarded to other peers (A → B
→ C) but not echoed back to their source. One record the receiver cannot accept
(for example a future operation type) is refused alone and reported; it never
blocks the rest.

### Initial sync, deltas, reconnect

A new or stale peer receives the whole feed in bounded batches (5,000 80-point
strokes: 20 requests, 7.2 MB). After that, one new stroke is one request of about
0.7 KB. Reconnection resumes from the cursors; offline edits on both sides merge
by the replica rules with no user action.

### Asset sync

The operation travels first; its image follows by hash. The receiver lists the
asset in `wants`; the sender streams it in checksummed chunks (≤ 256 KB, ≤ 2
transfers and ≤ 96 MB staged per peer, 60 s idle expiry). Nothing is stored
until the whole asset is present, its SHA-256 equals the id and it passes the
image checks; then it becomes visible. An interrupted transfer (receiver
restarted) simply starts again; a corrupted one is refused and nothing is kept.
An asset the receiver already has is never sent again.

### Tombstones and restore epochs

Permanent deletion leaves a tombstone that syncs; records for a purged drawing
are dropped on arrival and answered `purged`, which makes a stale sender purge
too — a deleted drawing cannot be resurrected. Trash and restore are ordinary
meta records and replicate.

Every store has a random **epoch**. Restoring a Draw backup gives the restored
store a new epoch and resets its own cursors; peers that see a changed epoch
reset their cursor for it and lift echo suppression, so they offer everything
again (idempotent). Tested: sync, back up, edit, restore, reconnect → the
restored device regains what the peer had.

### Compatibility with older builds

An older OLIVE build closes a Connect channel when it sees an unknown frame kind,
so Draw frames go only to a peer that has shown it speaks olive-draw/1:

- a peer that sent us a Draw frame first (a phone always speaks first); or
- on a channel we dialed (a desktop listener), a peer that answered the
  read-only probe `connect.ping` / `protocols` with `olive-draw/1`. The probe
  grants nothing and leaves no replay record. An older desktop answers it with a
  normal, correlated "unknown operation" rejection and keeps the channel open;
  Draw then shows "Not supported by this device's OLIVE version".

Notes frames, Notes permissions and `olive-notes/1` are unchanged.

### Privacy

Draw sync is private device data over the existing OLIVE Connect channel
(mutually authenticated TLS between paired devices on the local network). No
cloud, web provider, relay or model. Thumbnails, zoom, pan, tool, colour, size,
the open drawing and the last-used section are per-device and never synced. Logs
record ids, sizes, counts and error categories only — never titles, strokes or
image bytes.

### Corruption

A record that fails validation in the local store makes that drawing
"Could not load drawing" (data kept for recovery) and it is not sent to peers;
an asset whose bytes do not match its hash is never served. Nothing is replaced
with an empty drawing.

## OLIVE Draw on iPhone

### Navigation

The phone's third tab is **DrawNote** (title **OLIVE DrawNote**) with a
segmented **Notes | Draw** switch at the top of each list. The last-used section
is remembered on the phone (`shell.v1.drawnote.section`, never synced); the saved
tab value is still `notes`, so an existing saved destination opens DrawNote.
`AppState.openNotes()` lands in Notes and `openDraw()` in Draw. Chat, Devices and
Settings are unchanged.

### Architecture

| Layer | File (under `mobile/ios/OLIVEMobile/`) |
| --- | --- |
| Records, operations, validation, limits (mirror of `document.py`/`model.ts`) | `Core/Draw/DrawDocument.swift` |
| In-memory replica (port of `replica.ts`) | `Core/Draw/DrawReplica.swift` |
| SQLite store, replica rules in SQL (port of `store.py` + `records.py`) | `Core/Draw/DrawStore.swift` |
| Library, edits, local undo, assets, olive-draw/1 engine (one actor) | `Core/Draw/DrawEngine.swift` |
| olive-draw/1 codec (port of `protocol.py`) and wire helpers | `Core/Draw/DrawProtocol.swift`, `Core/Draw/DrawWire.swift` |
| Image validation, import canonicalization | `Core/Draw/DrawAssets.swift` |
| CoreGraphics renderer (port of `render.ts`) | `Core/Draw/DrawRender.swift` |
| Touch capture and viewport math (ports of `capture.ts`, `viewport.ts`) | `Core/Draw/DrawCapture.swift` |
| Connect integration (probe, hello, frames 15/16, status) | `Core/Draw/DrawSync.swift` |
| Library, editor, canvas, DrawNote switch | `Features/Draw/*.swift` |

**Replica implementation: native Swift, not the TypeScript replica in
JavaScriptCore.** The rules are small (`replica.ts` is ~125 lines) and whole-record
based; the phone also needs them in SQL for the durable store (as Python does),
the CoreGraphics renderer needs typed operations anyway, persistence integrates
directly with SQLite without a JS↔Swift bridge per record, an actor gives simple
Swift-concurrency isolation, and the shared fixture runs directly in XCTest.
Notes stays on JavaScriptCore because it needs Yjs; Draw does not use Yjs.

Every SQLite access goes through one actor (`DrawEngine`); UI state is on the
main actor; the only `@unchecked Sendable` in Draw is a render-result box whose
ownership passes once from the render task to the main actor.

### Conformance and interoperability

- `conformance_v1.json` (the shared file, bundled into the test target by
  reference) passes on the phone through both the in-memory replica and the
  SQLite store, 16 random arrival orders per scenario plus duplicate delivery.
- Limits and protocol constants are compared field by field with the shared
  `drawing_schema.json` and `protocol_v1.json` in a unit test.
- `tests/test_draw_phone_engine.py` drives the real Swift engine (built from the
  app sources by `mobile/ios/scripts/check-connect-interop.sh`) against the real
  Python desktop engine with real olive-draw/1 bytes: conformance in random
  orders, phone records accepted by Python validation, Lamport ordering,
  local-origin undo isolation, undo history across a SIGKILL, offline edits,
  duplicate/lost/reordered delivery, restart before ACK, conflicts, three
  replicas (desktop, phone, third) with forwarding, seeded random histories,
  tombstones both ways, trash/restore, image import (EXIF/GPS stripped,
  orientation applied), placement, bad images, assets both ways, a transfer
  interrupted by killing the phone process, corrupt transfers, permission
  Off/Allow, epoch changes both ways, strict protocol rejections and a
  1,000-stroke initial sync. 25 tests.

### Storage and data protection

`Application Support/Companion/Draw/drawings.sqlite3`: store schema 2 with the
same logical tables as the desktop (`meta` store_id/epoch/feed_seq, `drawings`,
`draw_records`, `draw_visibility`, `draw_history`, `draw_purges`,
`draw_assets`, `draw_wanted`, `draw_peers`, `draw_thumbnails`), WAL,
`synchronous=FULL`, one transaction per change. The folder and the database,
`-wal` and `-shm` files use the same Data Protection class as the Notes store,
`completeUntilFirstUserAuthentication` (verified on the physical iPhone by a unit
test), and the folder is excluded from device backup. This is iOS file protection
only; the database has no additional encryption. A newer or unrecognised
database is refused without being modified; an unreadable one is kept (never
replaced by an empty store) and Draw shows "Drawing storage unavailable"; a
record that fails validation makes that drawing "Could not load drawing" and
is never sent to peers.

### Rendering, touch and Apple Pencil

- The committed picture is a raster cache of the visible viewport, rendered off
  the main thread from the operations; the live stroke is drawn separately
  (a shape layer; pressure strokes use the renderer itself). Rendered pixels are
  never stored as the drawing.
- One finger draws one stroke (or one erase) per gesture, committed at touch-up;
  points are quantized to 1/100 document px exactly as on the desktop. Two
  fingers pinch-zoom (10 %–1600 %, around the focal point) and pan; a pinch or
  pan that starts cancels a stroke begun by its first finger. The navigation
  stack's swipe-back gestures are disabled while the canvas is on screen
  (iOS 26 recognizes swipe-back anywhere, which cancelled left-to-right strokes).
- Apple Pencil: `UITouch.type == .pencil` samples use `force /
  maximumPossibleForce` as pressure, trusted only once it varies; fingers never
  produce pressure. The width rule is the desktop's
  `width × (0.2 + 0.8 × pressure)` (unit-tested, including measured stroke
  widths). A Pencil double-tap whose system preference is "switch to eraser"
  toggles the eraser. **Neither was exercised on hardware**: the test iPhone does
  not support Apple Pencil.
- Smoothing is the desktop's (quadratics through midpoints); each quadratic is
  drawn as short line pieces because CoreGraphics offsets very tight curves
  with a squared corner where Chromium draws them round. A synthetic drawing
  (strokes, pressure, translucency, eraser, image, dot) rendered by the phone
  renderer and by the desktop's `render.ts` in Chromium: 97.3 % of pixels
  identical, 98.6 % within 8 of 255 levels, all differences at antialiased edges;
  every sampled coordinate identical (stroke, translucent overlap, eraser cut,
  background, image colour, image transparency).
- Fit is the default on open; rotation keeps the logical centre and zoom and
  never changes document data. Transparent pages show a checkerboard in the
  editor only.

### Image import and export

- Sources: Photo Library (`PhotosPicker`, no library permission needed), Files
  (document picker), Camera (native `UIImagePickerController`; the photo is not
  saved to the library). PNG, JPEG and HEIC/HEIF sources are read; headers are
  bounded before decoding (40 MB, 16384 px, 50 M pixels).
- Canonicalization follows the desktop: orientation applied, sRGB, re-encoded
  at the placed size (natural size if it fits, else within 90 % of the canvas,
  never upscaled, centred), PNG for PNG sources and JPEG 95 % otherwise, then
  every APPn/COM segment (JPEG) and eXIf/text/time chunk (PNG) removed: assets
  carry pixels and colour space only. A test with synthetic EXIF (orientation,
  camera make/model, timestamp) and GPS confirms none survives. The asset id is
  the SHA-256 of these bytes; independently importing the same file on the
  phone and on the desktop is not expected to give identical bytes (different
  encoders), and nothing depends on it.
- Assets are validated again on receipt (type from bytes, header bounds, PNG
  chunk CRCs with IHDR first and IEND last or a JPEG EOI, SHA-256, a bounded
  ImageIO decode) and stored atomically only when complete; a
  missing asset shows an "Image arriving…" frame and export refuses until it
  arrives.
- Export: PNG (transparency kept) or JPEG 92 % (white under transparency),
  flattened at document resolution, offered through the standard share sheet
  with a sanitized file name; OLIVE uploads nothing.

### Sync on the phone

- On every Connect channel the phone first asks the read-only
  `connect.ping`/`protocols` probe (frame 1). Only if the computer lists
  `olive-draw/1` does it send its Draw `hello` (frame 15), which is how the
  desktop learns this phone speaks Draw. An older desktop rejects the probe,
  keeps the channel, never receives a Draw frame, and the phone shows "this
  computer's OLIVE doesn't support Draw yet" (tested with a fake older desktop:
  no Draw frame, one probe, no reconnect loop).
- Content flows only when **Settings › OLIVE DrawNote › Draw › Sync drawings
  with your computer** is on (default on) **and** the computer's
  **Devices › this iPhone › Draw sync** is Allow (default Off). With the
  phone's switch off, desktop requests are answered `permission_off`. Notes
  and Draw switches and permissions are separate.
- After a local edit is saved, the phone pumps its feed; desktop requests
  (frame 16 answers) are handled by the same engine. There is no polling: an
  edit, a desktop request or a new channel starts a pump. In the background iOS
  suspends the app and the Connect channel closes; on resume the channel
  reconnects and catches up. Completed edits are durable before anything is
  sent, and pending records survive force-quit.
- Status line: Saved on this phone · Syncing… · Synced · Offline — N edits
  waiting · N images arriving · your computer does not allow Draw sync · this
  computer's OLIVE doesn't support Draw yet · Sync issue.

### Physical iPhone verification

On a physical iPhone (no simulator):

- Unit tests on the device: document/conformance, store (undo/redo, restart,
  remote edits, library, limits, Data Protection, corrupted/newer stores),
  assets, renderer pixels, input/viewport, three-replica sync engine, DrawSync
  negotiation (fake older desktop, permission Off → Allow, phone switch off,
  offline counts) and the editor model; plus the whole existing mobile suite.
- UI (isolated profile, synthetic drawing, real touch synthesis): create, pen,
  colour, size, opacity, eraser, undo/redo, pinch zoom, Fit, transparent
  background, image import, draw over the image, share PNG and JPEG,
  duplicate, delete, Recently Deleted, restore, relaunch (drawing, image, undo
  history and DrawNote section kept), landscape rotation and accessibility text
  sizes. XCUITest cannot synthesize a two-finger drag, so pan is covered by unit
  tests only.
- Live against a Mac test host (`tests/fixtures/draw_phone_test_host.py`: the
  production Python Connect, Draw and Notes services on a temporary profile,
  paired with the phone's separate acceptance identity) over the LAN:
  permission Off (nothing received, phone shows it) and Notes Allow not
  granting Draw; Allow delivered the pending drawing 0.3 s later; desktop
  creates → phone; red/blue/green local-origin Undo/Redo isolation both ways;
  images both directions (hash-verified, nothing left wanted); both sides
  editing offline then converging; a pending edit surviving force-quit and
  arriving exactly once; background → desktop edit → resume catch-up
  (within about 2 s); desktop restart; phone trash → desktop, desktop restore → phone;
  concurrent trash/restore converging on both.
- Against the user's CachyOS desktop (existing pairing, synthetic drawings):
  with Draw sync Off the phone reported "does not allow"; after Allow, phone
  edits were acknowledged within about 40 ms of each touch-up. The user then
  confirmed on both devices: phone content visible on Linux; desktop and phone
  strokes appearing live on the other device without reopening; phone Undo/Redo
  affecting only the phone's stroke and desktop Undo only the desktop's;
  a desktop image showing "Image arriving…" then completing on the phone, and
  PNG export on the phone; a phone edit made while the desktop was offline
  surviving force-quit and arriving exactly once after the desktop restarted;
  a drawing created on Linux appearing on the phone.

### Performance (physical iPhone, Debug build)

Desktop's own benchmark strokes (80 points each): 1,000 strokes load 0.7 s
(records + replica), full-viewport render 0.13–0.26 s; 5,000 strokes load
3.6 s, render 0.6–1.2 s (off the main thread; the cached raster is transformed
during pinch/pan). One edit 1–4 ms, Undo < 1 ms. A 4000 × 3000 JPEG imports in
30 ms (placed at 1296 × 972); flatten + PNG + JPEG export of 1920 × 1080 in
26 ms. Decoded images are kept only for the open drawing and dropped on
memory warnings; canonical asset bytes stay in SQLite.

## Rendering, zoom, pan and high DPI

- Three coordinate spaces (document, CSS, device); a view maps
  `device = doc × zoom × dpr + offset` with an integer device offset, so the
  cached raster is blitted on the pixel grid. Zoom never changes document
  coordinates.
- Zoom 10 %–1600 % (toolbar, % = 100 %, Fit, Ctrl+=/−, Ctrl+0 Fit, Ctrl+1 100 %,
  Ctrl+wheel/pinch around the pointer). Pan: Space+drag, middle drag, wheel.
- Backing store `round(CSS × devicePixelRatio)`, re-measured on resize and
  display-scale changes; verified at 1, 1.25, 1.5 and 2 in Electron.
- A cache holds the committed picture for the current zoom; a stroke that lands
  at the end is drawn incrementally; anything else (remote records inserted
  earlier in the order, Undo/Redo, an image arriving) replays from the last
  Clear. A remote record arriving mid-gesture never cancels the local stroke: the
  stroke stays live and is committed on pointer-up against the updated state.
- Measured (5,000 strokes × 80 points): open ≈ 1.6 s, replay 20–30 ms, Undo
  ≈ 35 ms, frame intervals while panning and drawing 7 ms median/p95.

## Canvas sizes and limits

- New drawing: 1920 × 1080, white; presets 1080 × 1080, A4 portrait/landscape,
  800 × 600, 1920 × 1080 transparent, custom.
- Canvas 16–8192 px per side, ≤ 33,554,432 pixels; 8192 × 4096 exports in about
  0.3 s.
- Per stroke ≤ 10,000 points; ≤ 20,000 operations; ≤ 100,000 records; ≤ 400 KB
  per operation; ≤ 48 MB of operations per drawing; ≤ 5,000 drawings.
- Images: file ≤ 40 MB, source ≤ 16384 px per side and ≤ 50 M pixels; stored
  asset ≤ 48 MB, ≤ 8192 px per side, ≤ 33,554,432 pixels.
- Edits past a limit are refused with a message, never silently truncated.

## Library, export, backups

- Drawings: UUIDs, duplicate titles allowed, most recently changed first,
  thumbnails (local cache), rename, duplicate ("Title (copy)", same assets),
  Recently Deleted, restore, delete permanently (confirmation).
- Export: PNG (lossless, transparency kept) and JPEG (92 % / 80 %;
  transparency composited onto white). Rendered at document resolution with
  imported images; the main process checks signature and size against the
  drawing, shows the save dialog with a sanitized name and writes atomically.
  Exporting never changes the drawing.
- Backups: component `draw` = `drawings.sqlite3`, including records, undo stacks
  and image assets; restore validates integrity and version and renews the sync
  epoch. Exported images are user files and are not included.

## Keyboard and accessibility

Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y undo/redo (this device's edits), Ctrl+= / Ctrl+−
zoom, Ctrl+0 fit, Ctrl+1 100 %, Ctrl+N new drawing, P/B pen, E eraser, [ ] size,
Space+drag pan; never while a field, menu or dialog has focus; Delete does
nothing. Toolbar controls are labelled; the canvas has a descriptive label.

## Security

Typed bridge methods only (`draw.*`), zod schemas in Electron and exact-key
validation in Python and the renderer; strict olive-draw/1 envelopes; bounded
strings, counts, frames, chunks and staged bytes; image type from content;
headers bounded before decoding; decoding in the sandboxed renderer; Pillow
structure checks with the bomb guard; SHA-256 checks; titles rendered as text;
no `innerHTML`; no paths from the renderer or peers; no model access.

## Known limitations

- Sync unit is a completed edit; there is no live preview of a remote stroke
  while it is being drawn.
- Imported images are placed once (no move/resize/selection yet); no shapes,
  text, fill or layers.
- Unreferenced image assets are retained (no garbage collection yet).
- Apple Pencil pressure and the Pencil eraser gesture are implemented but not
  verified on hardware (the test iPhone does not support Apple Pencil). Camera
  import uses the native picker but was not exercised physically (tests use
  synthetic images). Two-finger pan on the phone is unit-tested only.
  A desktop pen's eraser end, touch and a physical trackpad were not exercised
  with real hardware; Windows was not run.
- A stroke in progress at a crash is lost; the remembered section/selection may
  reset after a hard kill.
- On the phone, opening a 5,000-stroke drawing takes about 3.6 s in a Debug
  build.

## Tested flows

- iPhone: see [Physical iPhone verification](#physical-iphone-verification);
  `tests/test_draw_phone_engine.py` (Swift engine against Python, run by
  `mobile/ios/scripts/check-connect-interop.sh`); opt-in UI tests
  `DrawUIAcceptanceTests`, `DrawUILayoutTests` (`TEST_RUNNER_OLIVE_DRAW_UI_ACCEPTANCE=1`),
  `DrawLiveAcceptanceTests` (`TEST_RUNNER_OLIVE_DRAW_LIVE_ACCEPTANCE=1`, steps in
  `TEST_RUNNER_OLIVE_DRAW_LIVE_STEPS`) and `DrawTestHostPairingTests`.

- Python: `test_draw_core` (store, migration v1→v2, assets, EXIF ingest, limits,
  backup/restore with assets, crash), `test_draw_conformance`, `test_draw_chat`,
  `test_draw_sync` (two/three replicas, faults, conflicts, local undo, tombstones,
  assets, interrupted/corrupt transfers, permissions, restore epochs, strict
  protocol, 5,000-stroke deltas, 12 seeded random histories with pixel hashes),
  `test_connect_draw` (real TLS loopback: permission separation, live both ways,
  offline convergence, image transfer, probe compatibility, revocation).
- Frontend: `desktop/tests/draw.test.ts` (schema, records, replica conformance in
  random orders, session merge/undo/retry, images, viewport, capture, renderer,
  contracts).
- Electron: `drawnote.spec.ts` (acceptance, SIGKILL, DPI ×4, 5,000 strokes, max
  canvas), `draw-images.spec.ts` (PNG/JPEG/EXIF import, source deletion, export,
  duplicate, backup/restore, dedupe), `draw-sync-live.spec.ts` (two real OLIVE
  desktops over Connect TLS), and `notes.spec.ts` (Notes unchanged).
