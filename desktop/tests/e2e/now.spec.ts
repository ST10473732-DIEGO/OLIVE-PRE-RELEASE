import { test, expect, _electron as electron } from "@playwright/test";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

test("LIVE NOW weather stays local with inspectable source attribution", async () => {
  test.skip(process.env.OLIVE_LIVE_AI !== "1", "Opt-in installed local model and public weather");
  test.setTimeout(240000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-now-gui-"));
  const app = await electron.launch({chromiumSandbox: true, args: [path.resolve(".")], env: {...process.env, OLIVE_DATA_DIR: profile}});
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", {name: "Enter OLIVE", exact: true}).click();
    await expect.poll(() => page.evaluate(async () => {
      const s = await window.olive.call("runtime.snapshot", {}) as {presets: {id:string; available:boolean}[]};
      return s.presets.some(p => p.id === "now" && p.available);
    }), {timeout: 30000}).toBe(true);
    await page.getByRole("button", {name: "Find anything", exact: true}).click();
    await page.getByRole("button", {name: "Open Chat", exact: true}).click();
    await page.getByRole("combobox", {name: "OLIVE preset", exact: true}).selectOption("now");
    await page.getByRole("textbox", {name: "Message OLIVE", exact: true}).fill("What is the weather in Cape Town right now?");
    await page.getByRole("button", {name: "Send message", exact: true}).click();
    await expect(page.getByText("NOW · LIVE · This device", {exact: true}).last()).toBeVisible({timeout:180000});
    await expect(page.getByRole("button", {name: "S1 · Open-Meteo", exact:true})).toBeVisible();
    await page.getByRole("button", {name: "S1 · Open-Meteo", exact:true}).click();
    await expect(page.getByText("Source evidence", {exact:true}).first()).toBeVisible();
    await expect(page.locator(".messages")).not.toContainText("qwen3.5:9b");
    const s = await page.evaluate(async () => await window.olive.call("runtime.snapshot", {})) as {chat:{messages:{sources: {retrieved_at:string; weather: {conditions: unknown}}[];provider:{model:string}}[]}};
    const answer = s.chat.messages.at(-1)!;
    expect(answer.provider.model).toBe("qwen3.5:9b");
    expect(answer.sources[0].retrieved_at).toBeTruthy();
    console.log(JSON.stringify({acceptance: "NOW weather", answer}));
  } finally {await app.close();}
});
