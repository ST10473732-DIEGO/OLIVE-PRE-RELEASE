import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { schemas } from "../electron/contracts";
import { RemoteAI, modeDetail } from "../src/features/devices/RemoteAI";
import { unavailableControls, type Device, type RemoteChatSummary } from "../src/features/devices/types";
import { VideoDurationView } from "../src/features/chat/VideoDuration";
import { mediaPlaceholder } from "../src/features/chat/MediaNotice";
import { artifactDetails, artifactSummary } from "../src/features/chat/MediaArtifacts";
import {
  durationLabel, estimateLabel, parseCustomDuration, planLine, videoInput, type VideoPlan,
} from "../src/features/chat/videoDurationModel";
import type { MediaArtifact } from "../src/services/api";

const MODES = ["fast", "normal", "max", "uncensored", "now", "deep", "reimagine", "audio", "video"];

function summary(unavailable: string[] = []): RemoteChatSummary {
  const group = (id: string, keys: string[]) => ({
    id, modes: keys.map((key) => ({ id: key, available: !unavailable.includes(key), reason: unavailable.includes(key) ? "needs_setup" : "", limitations: [] })),
  });
  return {
    protocol: "olive-chat/1",
    groups: [group("chat", MODES.slice(0, 4)), group("research", ["now", "deep"]), group("create", ["reimagine", "audio", "video"])],
    attachments: ["document", "image", "note"],
    video: { image_to_video: true, maximum_seconds: 180, long_form: true },
  };
}

const phone = (decision: "allow" | "ask" | "deny"): Device => ({
  device_id: crypto.randomUUID(), display_name: "Test iPhone", platform: "ios", device_class: "phone",
  permissions: [{ capability: "models.remote", decision, scope: null }],
  remote_ai: { presets: { fast: true, normal: true, max: true }, jobs: [] },
});

const render = (device: Device, value: RemoteChatSummary | null) =>
  renderToStaticMarkup(createElement(RemoteAI, { device, summary: value, refresh: async () => undefined }));

describe("Remote AI card", () => {
  it("no longer describes Remote AI as text-only", () => {
    const html = render(phone("allow"), summary());
    expect(html).not.toMatch(/text-only/i);
    expect(html).not.toContain("unavailable remotely");
    expect(html).toContain("approved Chat modes, research, attachments and local media generation");
  });
  it("lists every mode the computer serves, grouped, from the backend matrix", () => {
    const html = render(phone("allow"), summary());
    for (const mode of MODES) expect(html).toContain(`>${mode.toUpperCase()}<`);
    for (const group of ["Chat", "Research", "Create", "Content"]) expect(html).toContain(`>${group}</h4>`);
    expect(html).toContain("Attachments");
    expect(html).toContain("Image → Video · up to 3 min");
    expect(html.match(/ · Available/g)?.length).toBe(10);  // nine modes + attachments
  });
  it("shows missing modes as needing setup, never green", () => {
    const html = render(phone("allow"), summary(["video", "audio"]));
    expect(html).toMatch(/data-available="false" data-tone="warning"[^>]*>.*?VIDEO<small>Needs setup<\/small>/);
    expect(html.match(/ · Needs setup/g)?.length).toBe(2);
  });
  it("keeps permission separate from capability visibility", () => {
    expect(render(phone("deny"), summary())).toContain("Permission · Off");
    expect(render(phone("ask"), summary())).toContain("Permission · Ask");
    expect(render(phone("allow"), summary())).toContain("Permission · Allow");
    // Capabilities stay visible while Off, so the person knows what Allow would offer.
    expect(render(phone("deny"), summary())).toContain(">VIDEO<");
    expect(render(phone("allow"), summary())).toContain("never grants terminal, desktop control");
  });
  it("says so when the matrix is unavailable instead of guessing", () => {
    expect(render(phone("allow"), null)).toContain("capabilities are unavailable right now");
    expect(modeDetail("fast", summary())).toBe("");
  });
});

describe("Additional mobile controls", () => {
  const capabilities = ["chat", "tasks", "calendar", "reminders", "notifications", "files.shared", "filesystem.full", "terminal",
    "apps.launch", "desktop_control", "software.install"].map((capability) => ({ capability, supported: false, policy_disabled: false }));
  it("uses the backend's authoritative list and never lists Chat", () => {
    const labels = unavailableControls({ capabilities, mobile_controls: { unavailable: ["chat", "tasks", "terminal", "desktop_control"], provided_by: { chat: "models.remote" } } });
    expect(labels).toEqual(["Tasks", "Terminal", "Desktop Control"]);
  });
  it("still excludes Chat when talking to an older backend without the list", () => {
    const labels = unavailableControls({ capabilities });
    expect(labels).not.toContain("Chat");
    expect(labels).toEqual(["Tasks", "Calendar", "Reminders", "Notifications", "Shared folders", "Full filesystem", "Terminal",
      "Launch apps", "Desktop Control", "Install software"]);
  });
});

const plan = (extra: Partial<VideoPlan> = {}, capability: Partial<VideoPlan["capability"]> = {}): VideoPlan => ({
  policy: { default_seconds: 2, maximum_seconds: 180, minimum_seconds: 0.5, long_video_warning_seconds: 30, setting: "media_video.max_duration_seconds" },
  capability: { supports_text_to_video: true, supports_image_to_video: true, native_segment_seconds: 2.0417, max_images: 1,
    duration: { configurable: true, maximum_seconds: 180, minimum_seconds: 0.5, default_seconds: 2 }, ...capability },
  error: null, message: "", ...extra,
});

describe("VIDEO duration", () => {
  it("labels and parses custom lengths in seconds or minutes", () => {
    expect([durationLabel(2), durationLabel(2.5), durationLabel(60), durationLabel(90), durationLabel(120)]).toEqual(["2 s", "2.5 s", "1 min", "1 min 30 s", "2 min"]);
    expect(parseCustomDuration("37", "s")).toBe(37);
    expect(parseCustomDuration("13", "s")).toBe(13);
    expect(parseCustomDuration("1.5", "min")).toBe(90);
    expect(parseCustomDuration("2", "min")).toBe(120);
    for (const bad of ["", "-3", "0", "abc", "1e9", "20s"]) expect(parseCustomDuration(bad, "s")).toBeNull();
  });
  it("shows the backend's resolution of a duration stated in the prompt", () => {
    const resolved = plan({ target_seconds: 20, source: "prompt", prompt_seconds: 20, segments: 10, long: false });
    expect(planLine(resolved)).toBe("20 s target from your prompt · 10 generation segments");
    const html = renderToStaticMarkup(createElement(VideoDurationView, { value: null, plan: resolved, images: 0, busy: false, onChange: () => undefined }));
    expect(html).toContain("Auto · 20 s");
    expect(html).toContain("20 s target from your prompt");
  });
  it("says when an explicit length overrides the prompt, and estimates only from measurements", () => {
    expect(planLine(plan({ target_seconds: 20, source: "explicit", prompt_seconds: 5, conflict: true, segments: 10 })))
      .toContain("your prompt says 5 s; the selected length is used");
    expect(planLine(plan({ target_seconds: 60, source: "explicit", segments: 30, long: true, estimate_seconds: null })))
      .toContain("This may take several minutes");
    expect(estimateLabel([400, 520])).toBe("About 7–9 min");
    expect(estimateLabel(null)).toBe("");
  });
  it("offers presets and a custom entry, not a fixed maximum of two seconds", () => {
    const html = renderToStaticMarkup(createElement(VideoDurationView, { value: 37, plan: plan({ target_seconds: 37, source: "explicit", segments: 19 }), images: 0, busy: false, onChange: () => undefined }));
    for (const option of ["Auto", "2 s", "5 s", "10 s", "20 s", "30 s", "1 min", "Custom · 37 s"]) expect(html).toContain(`>${option}`);
    expect(html).not.toMatch(/maximum video length/i);
  });
  it("reports configured limits truthfully", () => {
    const line = planLine(plan({ error: "video_duration_too_long", message: "OLIVE VIDEO on this computer is limited to 3 min per video." }));
    expect(line).toContain("limited to 3 min");
  });
  it("accepts one image only when the computer supports image-to-video", () => {
    expect(videoInput(0, true)).toBe("text");
    expect(videoInput(1, true)).toBe("image");
    expect(videoInput(2, true)).toBe("too_many");
    expect(videoInput(1, false)).toBe("unsupported");
    const view = (images: number, supports: boolean) => renderToStaticMarkup(createElement(VideoDurationView, {
      value: null, plan: plan({ target_seconds: 2, source: "default", segments: 1 }, { supports_image_to_video: supports }), images, busy: false, onChange: () => undefined }));
    expect(view(1, true)).toContain("Image → Video");
    expect(view(2, true)).toContain("accepts one starting image");
    expect(view(1, false)).toContain("supports text prompts only");
    expect(mediaPlaceholder("video", ["text-to-video", "image-to-video"])).toBe("Describe the video to generate. Optionally attach one image to animate.");
    expect(mediaPlaceholder("video", ["text-to-video"])).toBe("Describe the video to generate…");
  });
  it("sends an explicit length only through the strict contract", () => {
    const chat = crypto.randomUUID();
    expect(schemas["interaction.submit"].safeParse({ chat_id: chat, text: "x", video_duration_seconds: 20 }).success).toBe(true);
    expect(schemas["interaction.submit"].safeParse({ chat_id: chat, text: "x", video_duration_seconds: 37.5 }).success).toBe(true);
    for (const bad of [0, -1, "20", Number.POSITIVE_INFINITY, 1e9])
      expect(schemas["interaction.submit"].safeParse({ chat_id: chat, text: "x", video_duration_seconds: bad }).success).toBe(false);
    expect(schemas["media.video_plan"].safeParse({ text: "a 20 second video", images: 1 }).success).toBe(true);
    expect(schemas["media.video_plan"].safeParse({ text: "x", path: "/etc/passwd" }).success).toBe(false);
  });
  it("records target and measured length separately on the artifact", () => {
    const artifact: MediaArtifact = { id: "0".repeat(32), kind: "video", filename: "olive-video.mp4", mime_type: "video/mp4", created_at: "",
      mode: "video", width: 1536, height: 896, duration_seconds: 20.0, target_duration_seconds: 20, segment_count: 10,
      generation_mode: "image_to_video", continuation: "last_frame", has_audio: true, generator: { family: "LTX" } };
    expect(artifactSummary(artifact)).toBe("1536 × 896 · 20.0 s · with sound · from your image · LTX");
    expect(artifactDetails(artifact)).toMatchObject({ target_seconds: 20, measured_seconds: 20, segments: 10, continuation: "last_frame" });
  });
});
