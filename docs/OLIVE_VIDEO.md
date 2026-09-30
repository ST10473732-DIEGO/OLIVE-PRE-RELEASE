# OLIVE VIDEO: target duration, long-form segments and image-to-video

OLIVE VIDEO renders on this computer with the installed LTX 2.3 runtime
(OLIVE-owned ComfyUI on `127.0.0.1:8190`, `ComfyUI-GGUF-Loader` nodes). Nothing
is downloaded. Desktop Chat and OLIVE Mobile call the same backend planner
(`olive/services/video_duration.py`) and pipeline
(`ChatMediaService._video`); only the UI differs.

## Native segment vs product duration

One LTX graph renders a **native segment**: 49 frames at 24 fps (about
2.04 s) at 768 × 448 latent, 8 distilled Euler steps, CFG 1.0, synchronized
audio, then the fixed ×2 latent upscale to 1536 × 896. Those values come from
`media_workflows.LTX` (the user's validated workflow) and are unchanged.

The **product duration** is arbitrary within a configurable policy. It is
built from bounded sequential native segments, never from one giant latent:

```
segment 1: text → video          (or: attached image → video)
           last frame ──┐
segment 2: image → video (from segment 1's last frame)
           last frame ──┐
…
stitch + trim → one MP4 of exactly round(target × 24) frames
```

A continuation segment's first rendered frame re-renders the frame it was
conditioned on, so it is dropped when stitching: each continuation adds 48 new
frames. Segments = 1 + ceil((frames − 49) / 48). 5 s → 3, 13 s → 7, 20 s → 10,
60 s → 30, 120 s → 60.

Arbitrary requested duration is achieved by bounded sequential segments; OLIVE
does not claim unlimited single-pass generation.

## Target duration

Canonical field `target_duration_seconds` (float; milliseconds on the Connect
wire). Precedence:

1. an explicit length chosen in the UI / request (`video_duration_seconds` on
   `interaction.submit`; `options.target_duration_ms` on olive-chat/1);
2. a length stated in the prompt, parsed deterministically (no LLM):
   "20 second video", "20-second video", "for 20 seconds", "20 sec(s)",
   "20s video", "half a minute", "1 minute", "1 minute 30 seconds",
   "90 seconds", "2 minutes", "0:20", "01:30". Only strong contexts count; "the
   ball drops after 3 seconds", "in her 20s", "the 1920s" and "at 5:30 pm" are
   not durations. The phone has a port of this parser; both share
   `tests/fixtures/video_duration_vectors.json`;
3. the configured default (2 s: one native segment, as before; published
   directly without re-encoding).

When an explicit length overrides a different prompt length, the UI says so
and the artifact records both (`target_duration_seconds`,
`parameters.prompt_duration_seconds`, `duration_source`).

Prompt cleaning: when the length came from the prompt, the purely operational
words are removed from the text sent to LTX ("Generate a 20 second cinematic
scene of …" → "Generate a cinematic scene of …"); the original prompt is kept
in `parameters.prompt`, the sent one in `parameters.generation_prompt`. An
explicit length leaves the prompt verbatim.

## Resource policy (configurable)

`settings.json` in the OLIVE profile:

```json
"media_video": {
  "default_duration_seconds": 2,
  "long_video_warning_seconds": 30,
  "max_duration_seconds": 180
}
```

The default maximum (3 minutes, 90 segments) comfortably allows 20 s and
minute-scale videos. Code-level ceilings that settings cannot raise stop an
accidental absurd request: 3600 s and 2000 segments. Above the configured
maximum the request is refused with the limit and the setting name
(`video_duration_too_long`); nothing is shortened silently. Below 0.5 s:
`video_duration_invalid`.

Before any GPU time: free disk space is checked against a conservative estimate
(recent measured bytes per second × segments × 2.5 + 512 MiB;
`video_storage_full`), and multi-segment or trimmed requests require FFmpeg
(`video_assembly_unavailable`; OLIVE never installs it).

Estimates are shown only from measured segment times on this computer
(`media/video-stats.json`, last 20): "About X–Y min". Otherwise the UI only says
it may take several minutes, and progress reports the real segment.

## Pipeline and verification

Per request, in an OLIVE-owned workspace `media/jobs/<random job id>/`
(`manifest.json`, `segments/`, `continuation/`, `final.tmp.mp4`):

1. GPU hand-off exactly as before (residency lock, text model unloaded,
   foreign-model check, other engines released, OLIVE's own VoiceStudio stopped).
2. Each segment: a fresh recorded seed; the graph is queued on the engine;
   the MP4 is written to `segments/NNNN.mp4` and checked with ffprobe
   (container, one video stream, 1536 × 896 or the orientation's size, 24 fps,
   ≥ 49 frames, one audio stream). The engine stays loaded between segments.
3. Continuation: FFmpeg extracts the exact last decoded frame
   (`select=eq(n,48)`) to `continuation/NNNN.png`; it is uploaded and wired into
   the next graph's `LoadImage → LTXV23ImgToVideo.image`.
4. Stitch + trim in one deterministic FFmpeg pass: exact frame ranges per
   segment; each segment's audio is cut to the same span and padded with silence
   to exactly its video length (no drift, no missing middle, one audio track);
   `concat`; H.264 High yuv420p CRF 18, AAC-LC 48 kHz stereo 192 kbit/s,
   `-movflags +faststart`, metadata stripped. Small hard audio cuts at segment
   boundaries are the truthful model behaviour; no crossfade is claimed.
5. Verification before publishing (ffprobe with frame count): MP4, one H.264
   stream, planned size, 24 fps, frames == round(target × 24), duration within
   one frame (+30 ms container slack) of the target, one AAC stream of matching
   length, SHA-256. Only then is the file moved (not copied) into
   `media/outputs/` and fsynced.
6. Always, success or not: the engine is released and verified, this job's
   uploaded frames and segment outputs in the OLIVE engine folders are deleted
   by exact job-id names, and the workspace is removed. Leftover job folders
   (a crash) are swept at startup — only 32-hex OLIVE-named folders.

Artifact (`Message.artifacts`, no paths): `duration_seconds` (**measured**),
`target_duration_seconds`, `width`, `height`, `fps`, `has_audio` (measured),
`segment_count`, `generation_mode` (`text_to_video` / `image_to_video`),
`continuation` (`none` / `last_frame` / `independent`), size, SHA-256,
generator family/workflow. Internal provenance (Media tools only): per-segment
seed, prompt id, seconds, bytes, SHA-256, conditioning image, continuation-frame
hash, `conditioned_on` (the previous last-frame hash) and a boundary PSNR
diagnostic, the source-image hash, the stitch arguments and the ffprobe result.

## Image-to-video

The previous validated graph had its `LoadImage` bypassed (mode 4). The
installed node `LTXV23ImgToVideo` (`nodes_ltx23.py`) takes an optional `image`
(first frame, resized and centre-cropped to width × height, held at
`image_strength` 0.89 as in the bundled example). Workflow `ltx-2.3-i2av` uses
the same installed files plus builtin `LoadImage`; it passed real runs on
ComfyUI 0.35.0 here. It is used both for an attached image (segment 1) and for
every continuation.

- One starting image (`video_one_image` for more). Documents and notes are
  refused in VIDEO. The attachment is a frozen source: preserved as its own
  original record; the engine gets an EXIF-oriented RGB PNG copy named by
  OLIVE (`<job>-reference.png`), never the peer's filename.
- Orientation follows the image: landscape 768 × 448, portrait 448 × 768,
  square 576 × 576 (latent sizes; ×2 output).
- Mobile Photo Library, Camera, Files images and OLIVE Draw PNGs are ordinary
  image attachments and reach the same path.
- A computer whose engine lacks the validated image workflow keeps refusing
  images truthfully (`video_image_unsupported` / `attachment_unsupported_mode`)
  and a long text-to-video there is labelled `continuation: independent`.

## Progress and Stop

Real states only: *Preparing video engine… · Starting video engine… ·
Generating segment 3 of 10… · Extracting continuation frame… · Stitching 10
segments… · Encoding final video… · Verifying output… · Saving video…* (plus
*Transferring…* on the phone). Stop at any point cancels the running ComfyUI
prompt (delete + interrupt), starts no further segment, kills FFmpeg if running,
removes the workspace, publishes nothing late and releases the GPU; text
inference works immediately after. Media stays serialized (one Chat media job at
a time behind the residency lock).

Desktop restart: a live VIDEO job does not survive a desktop process restart.
Remote jobs become `computer_stopped` / `outcome_unknown` as before, and a long
VIDEO is never silently regenerated. Completed videos persist in Chat and play
after a restart.

## Measured on this computer (RTX 3080 Ti Laptop, 16 GiB)

All durations below are ffprobe measurements of the published file (frame
counts with `-count_frames`), not metadata.

| Request | Mode | Segments | Target | Actual | Frames | Audio | Size | Wall time |
|---|---|---|---|---|---|---|---|---|
| default prompt | T2V | 1 (direct) | 2.0 s | 2.042 s | 49 | AAC 2.01 s | 0.58 MB | 63 s |
| explicit 1 s | T2V | 1 (trimmed) | 1.0 s | 1.000 s | 24 | AAC 1.00 s | 0.99 MB | 61 s |
| "5 second … clouds over mountains" | T2V | 3 | 5.0 s | 5.000 s | 120 | AAC 5.00 s | 1.57 MB | 138 s |
| "13 second … gentle waves" | T2V | 7 | 13.0 s | 13.000 s | 312 | AAC 13.00 s | 7.90 MB | 342 s |
| "20 second … futuristic city" | T2V | 10 | 20.0 s | 20.000 s | 480 | AAC 20.00 s | 9.65 MB | 457 s |
| synthetic image, 5 s | I2V | 3 | 5.0 s | 5.000 s | 120 | AAC 5.00 s | 1.42 MB | 161 s |
| synthetic image, 20 s | I2V | 10 | 20.0 s | 20.000 s | 480 | AAC 20.00 s | 5.86 MB | 472 s |
| portrait synthetic image, default | I2V | 1 | 2.0 s | 2.042 s (896 × 1536) | 49 | AAC 2.01 s | 0.31 MB | 47 s |
| desktop UI, image + Custom 3 s | I2V | 2 | 3.0 s | 3.0 s (player) | — | yes | — | ≈ 2 min |

Native segment ≈ 45 s warm (51–57 s for the first, up to 95 s on a cold
disk cache). Peak GPU ≈ 15.1–15.4 GiB of 16 GiB; after each job the OLIVE video
engine is back to ≈ 0.4 GiB (CUDA context) and text inference loads normally.
Boundary PSNR (segment N last frame vs N+1 first frame): 29.4–31.7 dB for text
continuations, 33.3–37.5 dB for image continuations.

## Known limitations

- Continuation is sequential image conditioning on the previous last frame.
  It gives one coherent scene rather than unrelated clips, but it is not
  seamless: motion can change direction at a boundary, objects can leave and
  re-enter (the red circle in the 20 s image test leaves the frame around 6 s
  and later jumps), and over many segments the image gradually drifts in style
  and sharpness (visible in the 20 s city test).
- Audio is generated per segment; there can be a small audible cut at each
  boundary.
- The 49-frame native segment is kept (validated VRAM on 16 GiB); longer native
  segments were not validated.
