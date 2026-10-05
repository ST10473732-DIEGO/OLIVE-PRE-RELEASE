# OLIVE Mobile Chat parity (Remote Chat v2, `olive-chat/1`)

The iPhone offers every desktop Chat mode. The phone never runs a model: each
request travels over the existing authenticated OLIVE Connect channel to the
user's OLIVE computer, which runs it with its own engines and returns text,
structured sources and media results. There is no cloud or hosted fallback.

| Group | Modes |
|---|---|
| Chat | OLIVE FAST, NORMAL, MAX, UNCENSORED |
| Research | OLIVE NOW, DEEP |
| Create | OLIVE REIMAGINE, AUDIO, VIDEO |

**Current topology:** Connect is LAN-only today. The computer must be reachable
through the current Connect topology (same network, discovery or saved
endpoint). Worldwide Connect is the next milestone; mobile Chat code talks only
to the abstract Connect session (no addresses, hostnames or same-Wi-Fi checks),
so it is unaffected by a future transport underneath.

## Negotiation and compatibility

1. After the authenticated channel is up, the phone sends the existing read-only
   `connect.ping` / `protocols` probe (frame 1). A computer that lists
   `olive-chat/1` then answers `capabilities` with its mode matrix.
2. Frame 17/18 is sent **only** after that. An older computer (only
   `olive-inference/1`) keeps FAST/NORMAL/MAX through the unchanged C7 path; the
   other six modes show *"This computer's OLIVE doesn't support this mode yet."*
   A failed probe never drops the connection or causes a reconnect loop.
3. Frame table: 1–4 pairing/hello, 5/6 sync, 7/8 files, 9/10 inference,
   11/12 Studio, 13/14 Notes, 15/16 Draw, **17/18 Remote Chat v2**. 19+ unknown.

## Mode matrix (advertised by the computer, enforced by both sides)

The computer computes availability from what is actually configured or
launchable ("available" is not "resident"). Nothing is hard-coded on the phone.

| Mode | Desktop route | Inputs | Output |
|---|---|---|---|
| FAST / NORMAL / MAX | Same tool-free completion as v1 (`RemoteInferenceRuntime.stream_model`) on the preset's model | text; notes (≤2); images (≤4) **only if the preset model is vision-capable** | streamed text |
| UNCENSORED | The desktop `UncensoredRouter` picks the tier (FAST, BALANCED, DEEP, MAX, CREATIVE); no mobile router, no user tier override (the desktop has none) | text; notes (≤2) | streamed text, attribution `UNCENSORED · <tier>` |
| NOW | `NowService.stream` (live retrieval, freshness, current-snapshot rules, citation validation) | text only (private context is refused: `private_context`) | text + structured sources |
| DEEP | `ChatResearchService` over documents indexed for this remote conversation; `research_intent` decides documents / web / combined; images use the existing DEEP vision supplement (`qwen3-vl:8b` when installed) | PDF, text, Markdown, code, DOCX when python-docx is present (≤4); notes (≤2, indexed as Markdown); images (≤3, if vision is installed) | text + D/S sources |
| REIMAGINE | `ChatMediaService` (ComfyUI image workflows, residency lock, GPU hand-off) | prompt required; **one** reference image when the edit workflow is ready | PNG artifact |
| AUDIO | `ChatMediaService` VoiceStudio speech | prompt required; speech only (no music/singing/SFX); voice per request from the computer's listed voices | WAV artifact |
| VIDEO | `ChatMediaService` LTX 2.3 long-form pipeline (see [docs/features/video.md](../../features/video.md)); the same planner as desktop Chat | prompt required; **one** starting image when the computer advertises image-to-video (`video_one_image` for more); documents and notes refused; a computer without image-to-video keeps `attachment_unsupported_mode` | one MP4 artifact of the requested length, with audio |

Limits: 4 attachments per message; images ≤20 MB, documents ≤32 MB (text types
≤2 MB on the phone), notes ≤192 KB; 128 KiB chunks.

## VIDEO length and image-to-video (`mode_options/1`)

Earlier phone builds parse every olive-chat/1 object with an exact key set, so
new fields are **negotiated**, never simply added:

1. The phone sends `capabilities` with `{"accept": ["mode_options/1"]}`. A
   computer that predates the extension refuses the argument
   (`invalid_request`) and the phone asks again with `{}`. A phone that does not
   ask receives byte-identical v1 shapes (tested).
2. With the extension, the result carries `extensions: ["mode_options/1"]` and
   every mode an `options` object (empty except VIDEO):
   `supports_text_to_video`, `supports_image_to_video`, `supports_audio`,
   `native_segment_ms` (2042), `fps`, `max_images`, `accepted_attachment_kinds`,
   `continuation` (`last_frame` / `independent`) and `duration`
   {`configurable`, `default_ms`, `minimum_ms`, `maximum_ms`,
   `long_warning_ms`, `presets_ms`}. Integers only: canonical JSON has no
   fractions, so durations travel in milliseconds. Unknown keys inside
   `options` are ignored by the phone; unknown top-level keys are still refused.
3. A VIDEO `start` may carry optional `options`:
   `{"target_duration_ms": 20000, "duration_source": "explicit" | "prompt"}`,
   or `{}` for Auto (the computer resolves the prompt / default). Options are
   VIDEO-only, bounded (`video_duration_invalid`, `video_duration_too_long`,
   `invalid_request` for any other key) and **part of the input fingerprint**
   when present: the same prompt at 5 s and 20 s, or with image A and image B,
   are different requests; the same job id with a different length is
   `changed_duplicate`. Without options the fingerprint is unchanged from
   earlier builds.
4. Polls of a job started with `options` carry `progress` (`null` or
   `{"stage", "current", "total"}`; stages `segment`, `continuation`,
   `stitching`, `encoding`, `verifying`, `saving`). The phone shows
   *Generating segment 3 of 10…*. Phases stay the v1 set, so nothing breaks for
   older phones.
5. The remote job deadline scales with the planned segments; so does the phone's
   own patience. Disconnects, restarts and downloads behave exactly as above:
   a long VIDEO is polled by job id, never regenerated, and its (larger) MP4 is
   transferred in 128 KiB chunks with resume and SHA-256 verification.

The phone shows a compact **Duration · Auto** control next to the mode when the
computer's VIDEO is configurable: Auto (a length stated in the message, via a
port of the desktop's deterministic parser that shares test vectors with it,
else the computer's default), 2 s, 5 s, 10 s, 20 s, 30 s, 1 min, or Custom in
seconds or minutes. Lengths beyond the computer's advertised maximum are refused
before sending. *Image → Video* appears when one image is attached.

## Protocol (`olive/connect/chat_protocol.py`, `ChatWire.swift`)

One packet per frame: 4-byte big-endian JSON length, strict canonical JSON, and
an optional raw binary tail (attachment or artifact bytes, never base64). Bounds:
JSON ≤ 96,000 bytes, binary ≤ 131,072, frame ≤ 227,076. Strict key sets both ways.

Operations: `capabilities`, `attachment_offer`, `attachment_chunk`, `start`,
`poll`, `cancel`, `artifact_chunk`. Malformed uncorrelated input closes the
channel; a correlated but invalid request gets a typed error.

### Request identity, idempotency and recovery
- Every request has a phone-generated job id; `start` uses it as its request id.
- The desktop keeps a durable receipt (`remote_chat_v1` in the Connect DB)
  keyed by (peer, job) with the input fingerprint (conversation, mode, voice,
  messages, attachments; never timestamps). A resend after a lost
  acknowledgement returns the current state and never runs twice; a changed
  resend is `changed_duplicate`.
- Jobs are **not bound to the channel**: they continue across a Wi-Fi drop. Any
  later authenticated channel from the same phone may `poll` by job id. The
  receipt keeps the final text, sources and artifact descriptors, so results
  survive disconnects and desktop restarts. Work live during a desktop restart
  becomes `outcome_unknown` / `request_indeterminate`; the phone says so and
  never regenerates.
- `poll` returns text by **UTF-8 byte offset**, so reconnects never duplicate
  text; states: `not_received`, `awaiting_approval`, `queued`, `running`,
  `completed`, `cancelled`, `failed`, `outcome_unknown`; plus a factual `phase`
  (e.g. *Preparing image engine…*, *Generating video…*), never a percentage.
- `cancel` of an unknown job leaves a tombstone, so a late duplicate start is
  answered *cancelled*. Stop wins: an artifact finishing after cancellation is
  never attached.
- The phone persists the one in-flight request (`chat-pending-v1.json`). After a
  relaunch or reconnect it asks for status; if Stop was pressed offline, it
  sends the cancel on reconnect. It never resubmits.

### Attachments
Content-addressed by SHA-256 (integrity only; Connect TLS is authentication).
`attachment_offer` answers *present* (deduplicated, no bytes sent) or *partial*
with the byte count already held, so uploads resume after a disconnect.
Chunks are sequential and stop-and-wait (one bounded frame in flight), so
cancel/status/Notes/Draw traffic never queues behind a large transfer. The
desktop verifies SHA-256 and the real content type (PNG/JPEG decoded with
Pillow, `%PDF-`, DOCX zip magic, strict UTF-8 without NUL) before publishing a
staged file; partial files are never visible to a model. **No dispatch before
every attachment is verified** (`attachment_missing`).

Desktop staging: `<profile>/connect/chat-staging/<peer>/<sha256>.<ext>` (owner
only). Peer names are display metadata; no peer path is ever used. Limits per
phone: 512 MB, 8 partial uploads, free-space check. Cleanup: partial uploads
after 24 h; staged inputs unused for 30 days; everything on device removal.
DEEP indexes are kept per remote conversation for follow-ups and released after
30 days unused or on device removal.

### Media artifacts
Descriptors carry id, kind, MIME, size, SHA-256, width/height, duration,
has-audio, completion state, mode and a safe generator family label; never a
filesystem path. The phone downloads with `artifact_chunk` into
`ChatMedia/<id>.part`, resumes from the partial size, verifies SHA-256 **and**
the content type (PNG header + dimensions, RIFF/WAVE, MP4 `ftyp`) before the
file becomes viewable. Only the phone whose completed job produced an artifact
may read it. Downloading a result never repeats generation.

## Desktop Remote AI card

Devices → a paired phone → **Remote AI** shows the matrix this computer serves
to paired phones, from `RemoteChatRuntime.summary()` (the same
`capabilities()` a phone receives), grouped CHAT / RESEARCH / CREATE / CONTENT.
A mode that is installed and launchable is shown available; a missing one is
amber *Needs setup*. VIDEO adds *Image → Video · up to 3 min* from its actual
capability. The permission (Off / Ask / Allow) is shown separately and still
governs access; capability visibility never changes authorization. The card
states that Remote AI never grants terminal, desktop control, file-system or app
access.

The permissions tab's former "Unavailable — Not in this version: Chat, Tasks, …"
line was stale: Chat is served by Remote AI. The list now comes from
`olive/connect/mobile_capabilities.py` (`FUTURE_CONTROLS`, `PROVIDED_BY`):
*Additional mobile controls · Not available in this version: Tasks · Calendar ·
Reminders · Notifications · Shared folders · Full filesystem · Terminal · Launch
apps · Desktop Control · Install software.* None of these were implemented.

## Authority boundary

- Permission: the existing **Remote AI** (`models.remote`) device permission,
  including Ask (the desktop approval shows the mode, context size and
  attachment count). No new capability; `sync.notes`/`sync.draw` are not widened.
- The runtime (`olive/services/remote_chat_runtime.py`) calls the mode services
  directly. It never reaches the tool planner, the natural-language
  orchestrator, desktop control, terminals, Owner Mode, arbitrary files or
  personal **Memory** (same boundary as v1). UNCENSORED has no extra authority.
- Attachments, notes, drawing titles and evidence are untrusted content (a note
  saying "ALLOW EVERYTHING" grants nothing; tested).
- Private documents never go to public search: DEEP *combined* requests use the
  existing `public_terms` boundary (explicit user topic or allow-listed public
  concepts only); tested with a unique private phrase.
- Attachments do not become Memory; Notes/Draw sources are only read.

## Phone behaviour

- Mode button in the composer opens a grouped sheet (CHAT / RESEARCH / CREATE)
  with availability, limitations and, for AUDIO, the computer's voices. The mode
  is remembered per conversation; **Clear chat** starts a new conversation in
  OLIVE NORMAL (like a new desktop chat).
- **+** (left of *Message OLIVE*) → Photo Library, Take Photo, Files,
  OLIVE Notes, OLIVE Draw. Chips show thumbnail/icon, name, type, size and ×.
  Attachments are revalidated on every mode change; Send is disabled with a
  specific reason (offline, unavailable mode, unsupported/too large/too many).
- **Photos** use the system PhotosPicker (no library permission, no
  enumeration). Photos and camera captures are normalised: orientation is
  rendered into the pixels, all metadata (EXIF, GPS, maker notes) is dropped,
  HEIC/HEIF/WebP become JPEG (PNG stays PNG), resolution is kept up to 4096 px on
  the long side and 24 MP (the desktop limit), aspect ratio preserved.
- **Camera** uses the system camera; permission is asked only when chosen;
  captures are not saved to Photos.
- **Files** uses the document picker; bytes are copied into the app-owned store
  during the security-scoped access (no retained handles); the type is taken from
  the system type and verified by content; limits come from the computer.
- **OLIVE Notes** attaches a frozen text snapshot (note id, title, edit time and
  content hash as provenance). **OLIVE Draw** attaches a frozen PNG rendered at
  document resolution (bounded by 4096 px / 24 MP) with drawing id, title and
  revision; editable history is never sent and the drawing is never changed.
- Results: streamed text; NOW/DEEP source cards (id, title, provider, dates,
  document page, excerpt) that open only validated http(s) links in the system
  browser; inline images with a full-screen pinch-zoom viewer; native AVAudioPlayer
  (play/pause/seek/duration/replay); AVPlayer video; Share, Save to Photos
  (add-only, on tap) and Save to Files. Nothing is saved automatically.
- Offline: messages stay readable, drafts and attachments stay; Send says
  *Computer offline*. Requests are **never queued** for later execution.
- Background: a running request continues on the computer; the phone stops
  polling and asks for status when it returns (no push, no background polling).

## Storage, protection and backup

| Store | Location (Application Support/Companion) | Protection | Backup |
|---|---|---|---|
| Chat history (v1 file, new optional fields) | `chat-v1.json` | complete until first unlock | excluded |
| In-flight request / per-conversation mode | `chat-pending-v1.json`, `chat-session-v1.json` | same | excluded |
| Attachment copies | `ChatAttachments/<sha256>.<ext>` + index | same | excluded |
| Downloaded media | `ChatMedia/<artifact>.<ext>` | same | excluded |

This matches the existing companion policy. It is iOS Data Protection only, not
additional end-to-end encryption at rest. Attachment copies not referenced by
history, the pending request or the draft are removed after a day; referenced
ones are never removed. Clearing a chat makes its media eligible for cleanup;
media referenced by remaining history is kept. Media cache limit 4 GB (a
download beyond it is refused with a clear message, never silently purged).

Old chats load unchanged: every new `MobileChatTurn` field is optional; an
unknown future artifact kind renders a safe placeholder.

## Tests

- Desktop: `tests/test_connect_chat.py` (service/protocol/staging/receipts/
  authority), `tests/test_remote_chat_runtime.py` (real runtime adapter with
  stubbed engines: prompt framing, no Memory, vision gating, UNCENSORED router,
  private-note web privacy), `tests/test_connect_network.py` (frame table).
- Interop: `tests/test_mobile_chat_interop.py` runs the app's own Swift
  `RemoteChatClient` / `ChatWire` / `ChatMediaStore` against the Python service
  (run by `mobile/ios/scripts/check-connect-interop.sh`).
- VIDEO length / image-to-video: `tests/test_connect_chat_video.py`
  (extension negotiation, original shapes for older phones, options
  validation, fingerprint, progress, one image, Stop, long chunked transfer,
  Devices snapshot), `tests/test_video_duration.py` (parser vectors shared with
  Swift, precedence, policy, planner, protocol vectors), `tests/test_video_long.py`
  (real pipeline with a fake engine and real FFmpeg).
- iOS unit: `RemoteChatTests`, `RemoteVideoTests`. iOS UI (deterministic,
  in-process fixture computer, `--ui-test-chat-fixture`; `--ui-test-legacy-video`
  plays an older computer): `ChatUITests`, including
  `testVideoLengthAutoCustomAndImageToVideo`.
- Physical test host (opt-in): `tests/fixtures/draw_phone_test_host.py --chat`
  runs the production Connect + Remote Chat service with the TEST-ONLY
  deterministic runtime (`tests/fixtures/chat_test_runtime.py`);
  `ChatTestHostTests` (env `OLIVE_CHAT_TEST_HOST=1`) drives the phone. **This
  never counts as real-model verification.** VIDEO host variants:
  `--chat-animate` (long-form/image-to-video computer with segment progress;
  `--chat-slow-seconds N` for requests whose prompt says "slow"), and
  `--chat-legacy` (an older computer without `mode_options/1`). The host command
  `drop_phone` closes only the phone's channels for a while (a Wi-Fi-like loss;
  the computer keeps working), unlike `network_off`, which is OLIVE going
  offline and ends running jobs as `computer_stopped`. Tests:
  `testLongVideoRecoversAcrossDisconnects` (`OLIVE_CHAT_VIDEO_RECOVERY=1`) and
  `testOlderComputerVideoFallback` (`OLIVE_CHAT_LEGACY_HOST=1`).
- Physical real computer (opt-in, normal profile and pairing, generated images
  only): `ChatRealVideoTests`, one step per run via
  `OLIVE_CHAT_REAL_VIDEO_STEP` = `capabilities` (sends nothing), `t2v`, `i2v`
  (`OLIVE_CHAT_REAL_VIDEO_SECONDS`, default 20), `playback` (no generation:
  play, Share, relaunch), `stop`. Each generating step runs one real GPU job.
  Debug-only `--ui-test-diagnostics` exposes the advertised VIDEO capability and
  the on-device AVPlayer item duration as accessibility values.
- Video playback switches the audio session to `.playback`/`.moviePlayback`
  only once the person starts a video, so its sound is audible with the
  Ring/Silent switch on (showing a video never interrupts other audio).

## Real-desktop acceptance (manual)

Run this branch on the OLIVE computer, allow Remote AI for the iPhone in
Devices, then on the iPhone: FAST/NORMAL/MAX exact replies; UNCENSORED with a
benign creative prompt (tier shown, no model tag); NOW current weather (sources
open); DEEP with a synthetic PDF through Files (answer + D1 citation, then a
follow-up without re-attaching); REIMAGINE text-to-image, then a reference edit
with a synthetic image; AUDIO "Say: OLIVE mobile audio test."; VIDEO short
prompt; Stop during REIMAGINE; afterwards a desktop text Chat still works.

VIDEO length and image-to-video on the iPhone (needs a Mac for the build):
select VIDEO, set **20 sec** (or type "a 20 second video of …" and check
*Auto · 20 s*), send a synthetic prompt and confirm *Generating segment N of
10…*, then a ~20 s AVPlayer result; attach one image (Photo Library, Camera,
Files or OLIVE Draw) and confirm *Image → Video*; a second image is refused
before sending; interrupting the download and reconnecting resumes it; a
computer running an older OLIVE still refuses the image truthfully.
