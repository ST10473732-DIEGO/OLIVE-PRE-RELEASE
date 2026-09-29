import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { schemas } from "../electron/contracts";
import { MEDIA_PRESETS, PRESET_IDS } from "../electron/presets";
import { byteRange, mediaId } from "../electron/main/media-protocol";
import { fileActionSchema } from "../electron/file-actions";
import { messageAttribution, targetState, type ModelTarget } from "../src/features/chat/RemoteTarget";
import { MediaArtifacts, artifactDetails, artifactSummary, mediaUrl } from "../src/features/chat/MediaArtifacts";
import { mediaPlaceholder } from "../src/features/chat/MediaNotice";
import type { Chat, MediaArtifact } from "../src/services/api";

const id = "0123456789abcdef0123456789abcdef";
const chat = { id: crypto.randomUUID(), title: "t", model: "", draft: "", messages: [], partial: "", generating: false, documents: [] } as Chat;
const image: MediaArtifact = {
  id, kind: "image", filename: "olive-reimagine-2026-09-29-012345.png", mime_type: "image/png", created_at: "2026-09-29T12:00:00",
  mode: "reimagine", generator: { provider: "ComfyUI", family: "FLUX.2 Klein", workflow: "flux2-klein-9b" },
  parameters: { prompt: "an olive mascot", operation: "generate", seed: 1 }, width: 1024, height: 1024, available: true,
};

describe("Chat media presets", () => {
  it("adds REIMAGINE, AUDIO and VIDEO to the persisted preset contract", () => {
    expect(PRESET_IDS).toEqual(["fast", "normal", "max", "uncensored", "now", "deep", "reimagine", "audio", "video"]);
    for (const preset of PRESET_IDS)
      expect(schemas["chat.preset"].safeParse({ chat_id: chat.id, preset }).success).toBe(true);
    expect(schemas["chat.preset"].safeParse({ chat_id: chat.id, preset: "music" }).success).toBe(false);
  });
  it("labels finished media turns by mode and kind, never by checkpoint", () => {
    expect(messageAttribution({ runtime: "OLIVE Media", preset: "reimagine", tier: "IMAGE", model: "flux-2-klein-9b-fp8.safetensors" }))
      .toBe("REIMAGINE · IMAGE · This device");
    expect(messageAttribution({ runtime: "OLIVE Media", preset: "audio", tier: "SPEECH" })).toBe("AUDIO · SPEECH · This device");
    expect(messageAttribution({ runtime: "OLIVE Media", preset: "video", tier: "LTX" })).toBe("VIDEO · LTX · This device");
  });
  it("is This device only for every paired device", () => {
    const target: ModelTarget = { device_id: crypto.randomUUID(), display_name: "Peer", busy: false, state: "online",
      permission: "allow", presets: { fast: true, normal: true, max: true, reimagine: true } };
    for (const preset of MEDIA_PRESETS) expect(targetState(target, preset)).toBe("This device only");
  });
  it("gives each mode its own composer hint", () => {
    expect(mediaPlaceholder("reimagine")).toContain("attach one");
    expect(mediaPlaceholder("audio")).toMatch(/^Say:/);
    expect(mediaPlaceholder("video")).toContain("video");
    expect(mediaPlaceholder("normal")).toBe("");
  });
});

describe("artifact transport", () => {
  it("keeps artifact file resolution out of the renderer contract", () => {
    expect("media.artifact_file" in schemas).toBe(false);
    expect(schemas["media.reuse"].safeParse({ chat_id: chat.id, artifact_id: id }).success).toBe(true);
    expect(schemas["media.reuse"].safeParse({ chat_id: chat.id, artifact_id: "../../etc/passwd" }).success).toBe(false);
    expect(fileActionSchema.safeParse({ action: "media-open", artifact_id: id }).success).toBe(true);
    expect(fileActionSchema.safeParse({ action: "media-open", artifact_id: "/home/user/x.png" }).success).toBe(false);
  });
  it("serves only opaque ids on the app origin", () => {
    expect(mediaUrl(id)).toBe(`/__media/${id}`);
    expect(mediaUrl("../secret")).toBe("");
    expect(mediaId(`/__media/${id}`)).toBe(id);
    for (const bad of ["/__media/../index.html", `/__media/${id}/x`, `/__media/${id.toUpperCase()}`, "/index.html"])
      expect(mediaId(bad)).toBeNull();
  });
  it("parses byte ranges for video seeking and rejects invalid ones", () => {
    expect(byteRange(null, 100)).toBeNull();
    expect(byteRange("bytes=0-", 100)).toEqual([0, 99]);
    expect(byteRange("bytes=10-19", 100)).toEqual([10, 19]);
    expect(byteRange("bytes=90-500", 100)).toEqual([90, 99]);
    expect(byteRange("bytes=-10", 100)).toEqual([90, 99]);
    for (const bad of ["bytes=200-", "bytes=5-1", "bytes=-", "items=0-1", "bytes=0-1,4-5"]) expect(byteRange(bad, 100)).toBe("invalid");
  });
});

describe("inline media rendering", () => {
  const render = (artifacts: MediaArtifact[]) => renderToStaticMarkup(createElement(MediaArtifacts, {
    chat, artifacts, busy: false, changed: () => undefined, report: () => undefined }));
  it("renders real players for image, audio and video", () => {
    const html = render([image, { ...image, id: id.replace("0", "1"), kind: "audio", mime_type: "audio/wav", duration_seconds: 1.4 },
      { ...image, id: id.replace("0", "2"), kind: "video", mime_type: "video/mp4", duration_seconds: 2.04, has_audio: true, width: 1536, height: 896 }]);
    expect(html).toContain(`<img class="media-image" src="/__media/${id}"`);
    expect(html).toMatch(/<audio[^>]*controls/);
    expect(html).toMatch(/<video[^>]*controls/);
    expect(html).toContain("2.0 s · with sound");
    expect(html).toContain("Use generated image as reference");
  });
  it("reports a missing file truthfully instead of a broken player", () => {
    const html = render([{ ...image, available: false }]);
    expect(html).toContain("no longer available on this device");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("Save a copy");
  });
  it("never shows filesystem paths or checkpoint files in normal Chat", () => {
    const summary = artifactSummary({ ...image, parameters: { ...image.parameters, operation: "edit" } });
    expect(summary).toBe("1024 × 1024 · edited from your attachment · FLUX.2 Klein");
    const html = render([image]);
    expect(html).not.toMatch(/\/home\/|\.safetensors|\.gguf|prompt_id/);
    expect(JSON.stringify(artifactDetails(image))).not.toMatch(/\/home\/|path/);
  });
});
