import { test, expect, _electron as electron, type ElectronApplication, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

// Opt in: uses the locally installed image/video ComfyUI runtimes, the local
// VoiceStudio service and Ollama with an isolated temporary profile. Nothing
// is downloaded. Screenshots go to OLIVE_MEDIA_SHOTS (default: the profile).
const live = process.env.OLIVE_LIVE_MEDIA === "1";

async function launch(profile: string) {
  // Electron-as-Node from a Playwright shim must not leak into the launched app.
  const env = Object.fromEntries(Object.entries({ ...process.env, OLIVE_DATA_DIR: profile })
    .filter((entry): entry is [string, string] => entry[0] !== "ELECTRON_RUN_AS_NODE" && entry[1] !== undefined));
  const app = await electron.launch({ chromiumSandbox: true, args: [path.resolve(".")], env });
  const page = await app.firstWindow();
  await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
  await page.getByRole("button", { name: "Find anything", exact: true }).click();
  await page.getByRole("button", { name: "Open Chat", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "OLIVE preset", exact: true })).toBeEnabled({ timeout: 60000 });
  return { app, page };
}

async function send(page: Page, text: string) {
  await page.getByRole("textbox", { name: "Message OLIVE", exact: true }).fill(text);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
}

async function idle(page: Page, timeout: number) {
  await expect(page.getByRole("button", { name: "Stop response", exact: true })).toBeHidden({ timeout });
}

async function preset(page: Page, id: string) {
  await page.getByRole("combobox", { name: "OLIVE preset", exact: true }).selectOption(id);
}

async function shot(page: Page, dir: string, name: string) {
  await page.screenshot({ path: path.join(dir, `${name}.png`) });
}

async function noPaths(page: Page) {
  const text = await page.locator(".messages").innerText();
  expect(text).not.toMatch(/\/home\/|\.local\/share|\.safetensors|\.gguf|prompt_id|127\.0\.0\.1/);
}

test("LIVE LOCAL media Chat: REIMAGINE, edit, AUDIO, VIDEO and text recovery", async () => {
  test.skip(!live, "Requires installed local media engines (OLIVE_LIVE_MEDIA=1)");
  test.setTimeout(1_200_000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-media-gui-"));
  const shots = process.env.OLIVE_MEDIA_SHOTS || profile;
  const results: Record<string, unknown> = {};
  let app: ElectronApplication | undefined;
  try {
    let page: Page;
    ({ app, page } = await launch(profile));

    // 1. REIMAGINE text → image, inline in Chat.
    await preset(page, "reimagine");
    await expect(page.getByText(/REIMAGINE creates images on this device/)).toBeVisible();
    await send(page, "Generate a simple cinematic olive mascot on a dark background.");
    await expect(page.getByRole("status").filter({ hasText: /engine|image/i }).first()).toBeVisible({ timeout: 60000 });
    const firstImage = page.locator("img.media-image").first();
    await expect(firstImage).toBeVisible({ timeout: 300000 });
    await expect.poll(() => firstImage.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth), { timeout: 30000 }).toBeGreaterThan(0);
    await expect(page.getByText("REIMAGINE · IMAGE · This device", { exact: true }).last()).toBeVisible();
    await idle(page, 60000);
    await noPaths(page);
    results.image = await firstImage.evaluate((img: HTMLImageElement) => [img.naturalWidth, img.naturalHeight]);
    await shot(page, shots, "1-reimagine-image");

    // 2. REIMAGINE edit with an attached synthetic image; the original stays unchanged.
    const source = process.env.OLIVE_MEDIA_EDIT_SOURCE!;
    const before = createHash("sha256").update(await readFile(source)).digest("hex");
    await app.evaluate(({ dialog }, file) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [file] }); }, source);
    await page.getByRole("button", { name: "Attach files to this message", exact: true }).click();
    await expect(page.getByRole("button", { name: /Remove image/ })).toBeVisible({ timeout: 30000 });
    await send(page, "Change the red square to bright green. Keep everything else the same.");
    await expect(page.locator("img.media-image")).toHaveCount(2, { timeout: 300000 });
    await expect(page.locator(".messages").getByText("Image edited from your attachment.", { exact: true })).toBeVisible();
    await idle(page, 60000);
    const after = createHash("sha256").update(await readFile(source)).digest("hex");
    expect(after).toBe(before);
    results.edit = { original_unchanged: after === before };
    await shot(page, shots, "2-reimagine-edit");

    // 3. AUDIO: real speech when a voice model is installed, otherwise the exact setup item.
    await preset(page, "audio");
    const snapshot = await page.evaluate(async () => {
      const state = await window.olive.call("runtime.snapshot", {}) as { presets: { id: string; available: boolean; status: string }[] };
      return state.presets.find((p) => p.id === "audio")!;
    });
    results.audio_preset = snapshot;
    await send(page, "Create a calm voice saying: Welcome to OLIVE.");
    if (process.env.OLIVE_LIVE_AUDIO === "1") expect(snapshot.available).toBe(true);
    if (snapshot.available) {
      // Only voices VoiceStudio lists; the first is its documented default.
      const picker = page.getByRole("combobox", { name: "AUDIO voice", exact: true });
      await expect(picker).toBeVisible({ timeout: 30000 });
      results.voices = await picker.locator("option").allTextContents();
      const audio = page.locator("audio.media-audio").last();
      await expect(audio).toBeVisible({ timeout: 300000 });
      await expect(page.getByText("AUDIO · SPEECH · This device", { exact: true }).last()).toBeVisible();
      await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => a.readyState), { timeout: 30000 }).toBeGreaterThan(0);
      const played = await audio.evaluate(async (a: HTMLAudioElement) => {
        a.muted = true;
        await a.play();
        await new Promise((resolve) => setTimeout(resolve, 600));
        a.pause();
        return { duration: a.duration, currentTime: a.currentTime };
      });
      expect(played.duration).toBeGreaterThan(0.3);
      expect(played.currentTime).toBeGreaterThan(0.2);
      results.audio = played;
    } else {
      const alert = page.getByRole("alert").filter({ hasText: /AUDIO needs setup/ });
      await expect(alert).toBeVisible({ timeout: 60000 });
      results.audio = { needs_setup: await alert.innerText() };
      await expect(page.locator("audio.media-audio")).toHaveCount(0);
    }
    await idle(page, 60000);
    await shot(page, shots, "3-audio");

    // 4. VIDEO: conservative LTX text-to-video with synchronized audio.
    await preset(page, "video");
    await send(page, "Generate a short cinematic video of a futuristic city in the rain.");
    const video = page.locator("video.media-video").last();
    await expect(video).toBeVisible({ timeout: 900000 });
    await expect(page.getByText("VIDEO · LTX · This device", { exact: true }).last()).toBeVisible();
    await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState), { timeout: 60000 }).toBeGreaterThan(0);
    const playback = await video.evaluate(async (v: HTMLVideoElement) => {
      v.muted = true;
      await v.play();
      await new Promise((resolve) => setTimeout(resolve, 900));
      v.pause();
      return { duration: v.duration, currentTime: v.currentTime, width: v.videoWidth, height: v.videoHeight };
    });
    expect(playback.currentTime).toBeGreaterThan(0.2);
    results.video = playback;
    await idle(page, 60000);
    await noPaths(page);
    await shot(page, shots, "4-video");

    // 5. Ollama reacquires the GPU after VIDEO.
    await preset(page, "normal");
    await send(page, "Reply with only: text inference recovered");
    await expect(page.locator(".message-assistant .message-body").last()).toContainText(/text inference recovered/i, { timeout: 240000 });
    await idle(page, 120000);
    results.text = await page.locator(".message-assistant .message-body").last().innerText();
    await shot(page, shots, "5-text-recovered");

    // Reload: a restarted app reopens the same Chat with its media rendered from disk.
    await app.close();
    ({ app, page } = await launch(profile));
    await expect(page.locator("img.media-image")).toHaveCount(2, { timeout: 60000 });
    await expect(page.locator("video.media-video")).toHaveCount(1);
    if (snapshot.available) await expect(page.locator("audio.media-audio")).toHaveCount(1);
    await expect.poll(() => page.locator("img.media-image").first().evaluate((img: HTMLImageElement) => img.naturalWidth), { timeout: 30000 }).toBeGreaterThan(0);
    results.reload = "media rendered after restart";
    await shot(page, shots, "6-reload");
  } finally {
    await writeFile(path.join(shots, "media-chat-live.json"), JSON.stringify(results, null, 1));
    await app?.close();
  }
});
