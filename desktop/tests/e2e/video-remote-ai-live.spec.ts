import { test, expect, _electron as electron, type ElectronApplication, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { openSpace } from "./shell";

// Opt in: OLIVE_LIVE_VIDEO=1 with the installed LTX runtime env (OLIVE_VIDEO_COMFY_*),
// Ollama env, OLIVE_VIDEO_PROFILE (a profile that already holds a generated 20 s
// VIDEO chat, for the restart check) and OLIVE_VIDEO_SOURCE (a synthetic image).
// Nothing is downloaded. Screenshots and results go to OLIVE_VIDEO_SHOTS.
const live = process.env.OLIVE_LIVE_VIDEO === "1";

function environment(extra: Record<string, string>) {
  return Object.fromEntries(Object.entries({ ...process.env, ...extra })
    .filter((entry): entry is [string, string] => !["ELECTRON_RUN_AS_NODE", "NODE_OPTIONS"].includes(entry[0]) && entry[1] !== undefined));
}

async function enterChat(app: ElectronApplication) {
  const page = await app.firstWindow();
  await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
  await openSpace(page, "Chat");
  await expect(page.getByRole("combobox", { name: "OLIVE preset", exact: true })).toBeEnabled({ timeout: 60000 });
  return page;
}

async function shot(page: Page, name: string) {
  await page.screenshot({ path: path.join(process.env.OLIVE_VIDEO_SHOTS || tmpdir(), `${name}.png`) });
}

test("LIVE VIDEO: restart keeps a 20 s video, duration control, custom length, image-to-video and text after", async () => {
  test.skip(!live, "Requires the installed LTX runtime (OLIVE_LIVE_VIDEO=1)");
  test.setTimeout(1_800_000);
  const profile = process.env.OLIVE_VIDEO_PROFILE!;
  const source = process.env.OLIVE_VIDEO_SOURCE!;
  const results: Record<string, unknown> = {};
  const app = await electron.launch({ chromiumSandbox: true, args: [path.resolve(".")], env: environment({ OLIVE_DATA_DIR: profile }) });
  try {
    const page = await enterChat(app);
    // 1. After a restart, the earlier 20 s VIDEO still opens and plays; nothing is regenerated.
    const search = page.getByLabel("Search conversations", { exact: true });
    if (!(await search.isVisible())) await page.getByRole("button", { name: "Conversation history", exact: true }).first().click();
    await search.fill("20 second cinematic");
    await page.getByRole("button", { name: /20 second cinematic/i }).first().click();
    const video = page.locator("video.media-video").last();
    await expect(video).toBeVisible({ timeout: 30000 });
    const facts = await video.evaluate(async (element: HTMLVideoElement) => {
      if (element.readyState < 1) await new Promise((resolve) => element.addEventListener("loadedmetadata", resolve, { once: true }));
      element.muted = true;
      await element.play();
      await new Promise((resolve) => setTimeout(resolve, 1500));
      element.pause();
      return { duration: element.duration, played: element.currentTime, width: element.videoWidth, height: element.videoHeight };
    });
    expect(facts.duration).toBeGreaterThan(19.9);
    expect(facts.duration).toBeLessThan(20.1);
    expect(facts.played).toBeGreaterThan(0.5);
    await expect(page.getByRole("button", { name: "Stop response", exact: true })).toBeHidden();
    await expect(page.locator(".media-meta").last()).toContainText("20.0 s");
    results.restart = facts;
    await shot(page, "1-restart-20s-video-plays");

    // 2. VIDEO composer: Auto reads the prompt, presets and a custom length.
    await page.getByRole("button", { name: "New chat", exact: true }).first().click();
    await page.getByRole("combobox", { name: "OLIVE preset", exact: true }).selectOption("video");
    await expect(page.getByText(/Optionally attach one image to animate/).first()).toBeVisible();
    const textbox = page.getByRole("textbox", { name: "Message OLIVE", exact: true });
    await textbox.fill("Generate a 20 second cinematic scene of clouds moving over a futuristic city.");
    const duration = page.getByRole("combobox", { name: "Video duration", exact: true });
    await expect(duration.locator("option[value=auto]")).toHaveText("Auto · 20 s", { timeout: 10000 });
    await expect(page.getByRole("status").filter({ hasText: "20 s target from your prompt · 10 generation segments" })).toBeVisible();
    await shot(page, "2-video-auto-reads-20s");
    await duration.selectOption("custom");
    await page.getByRole("textbox", { name: "Custom video length" }).fill("13");
    await page.getByRole("button", { name: "Set", exact: true }).click();
    await expect(duration.locator("option[value=custom]")).toHaveText("Custom · 13 s");
    await expect(page.getByRole("status").filter({ hasText: "13 s target · 7 generation segments" })).toBeVisible();
    await expect(page.getByRole("status").filter({ hasText: "your prompt says 20 s; the selected length is used" })).toBeVisible();
    await shot(page, "3-video-custom-13s-overrides-prompt");

    // 3. Real image-to-video from the desktop UI: one synthetic image, 3 s (two segments).
    const before = createHash("sha256").update(await readFile(source)).digest("hex");
    await app.evaluate(({ dialog }, file) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [file] }); }, source);
    await page.getByRole("button", { name: "Attach files to this message", exact: true }).click();
    await expect(page.getByText("Image → Video", { exact: true })).toBeVisible({ timeout: 30000 });
    await duration.selectOption("custom");
    await page.getByRole("textbox", { name: "Custom video length" }).fill("3");
    await page.getByRole("button", { name: "Set", exact: true }).click();
    await textbox.fill("Animate the clouds slowly and make the red circle drift to the right.");
    await shot(page, "4-image-to-video-ready");
    await page.getByRole("button", { name: "Send message", exact: true }).click();
    await expect(page.getByRole("status").filter({ hasText: /Generating segment 1 of 2/ }).first()).toBeVisible({ timeout: 180000 });
    await shot(page, "5-image-to-video-progress");
    const generated = page.locator("video.media-video").last();
    await expect(generated).toBeVisible({ timeout: 900000 });
    await expect(page.getByRole("button", { name: "Stop response", exact: true })).toBeHidden({ timeout: 60000 });
    await expect(page.locator(".media-meta").last()).toContainText("3.0 s");
    await expect(page.locator(".media-meta").last()).toContainText("from your image");
    results.i2v = await generated.evaluate(async (element: HTMLVideoElement) => {
      if (element.readyState < 1) await new Promise((resolve) => element.addEventListener("loadedmetadata", resolve, { once: true }));
      return { duration: element.duration, width: element.videoWidth, height: element.videoHeight };
    });
    expect(createHash("sha256").update(await readFile(source)).digest("hex")).toBe(before);
    expect(await page.locator(".messages").innerText()).not.toMatch(/\/home\/|\.local\/share|\.gguf|prompt_id|127\.0\.0\.1/);
    await shot(page, "6-image-to-video-result");

    // 4. Text inference after VIDEO in the same desktop session.
    await page.getByRole("button", { name: "New chat", exact: true }).first().click();
    await page.getByRole("combobox", { name: "OLIVE preset", exact: true }).selectOption("normal");
    await textbox.fill("Reply with exactly: video-ui-text-ready");
    await page.getByRole("button", { name: "Send message", exact: true }).click();
    await expect(page.locator(".messages").getByText("video-ui-text-ready", { exact: true }).last()).toBeVisible({ timeout: 300000 });
    results.text = "video-ui-text-ready";
  } finally {
    await writeFile(path.join(process.env.OLIVE_VIDEO_SHOTS || tmpdir(), "desktop-results.json"), JSON.stringify(results, null, 2));
    await app.close();
  }
});

test("LIVE Devices: Remote AI card shows the real phone matrix; Chat is not listed as unavailable", async () => {
  test.skip(!live, "Requires the installed local engines (OLIVE_LIVE_VIDEO=1)");
  test.setTimeout(300_000);
  const root = path.resolve(".."), profile = await mkdtemp(path.join(tmpdir(), "olive-remote-ai-ui-")), shim = path.join(profile, "shim");
  await mkdir(shim);
  // The existing C7 fixture pairs a synthetic peer with in-memory keys; real presets and media engines.
  await writeFile(path.join(shim, "sitecustomize.py"),
    `import sys,runpy\nsys.path.insert(0,${JSON.stringify(root)})\nrunpy.run_path(${JSON.stringify(path.join(root, "tests/fixtures/connect_inference_ui_runtime.py"))})\n`);
  const app = await electron.launch({ args: [path.resolve(".")], env: environment({ OLIVE_DATA_DIR: profile, PYTHONPATH: shim, OLIVE_C7_LIVE: "1" }) });
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Devices");
    await page.getByRole("button", { name: /^C7 paired desktop/ }).click();
    const card = page.getByRole("region", { name: "Remote AI activity" });
    await expect(card).toBeVisible({ timeout: 30000 });
    await expect(card).toContainText("approved Chat modes, research, attachments and local media generation");
    await expect(card).not.toContainText("text-only");
    for (const mode of ["FAST", "NORMAL", "MAX", "UNCENSORED", "NOW", "DEEP", "REIMAGINE", "AUDIO", "VIDEO"])
      await expect(card.getByRole("listitem").filter({ hasText: new RegExp(`^${mode}`) })).toContainText("Available");
    await expect(card).toContainText("Attachments");
    await expect(card).toContainText("Permission · Off");
    await expect.poll(async () => await card.innerText(), { timeout: 60000 }).toContain("Image → Video");
    await card.scrollIntoViewIfNeeded();
    await shot(page, "7-remote-ai-card");
    await page.getByRole("button", { name: "Permissions", exact: true }).click();
    const line = page.locator(".devices-unavailable-line");
    await expect(line).toContainText("Additional mobile controls");
    await expect(line).toContainText("Tasks · Calendar · Reminders · Notifications · Shared folders · Full filesystem · Terminal · Launch apps · Desktop Control · Install software");
    await expect(line).not.toContainText("Chat");
    await line.scrollIntoViewIfNeeded();
    await shot(page, "8-additional-mobile-controls");
  } finally {
    await app.close();
  }
});
