import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile, readFile, rename } from "node:fs/promises";
import { tmpdir } from "node:os";
import { openSpace } from "./shell";

test("C7 LIVE remote FAST, real cancellation and local Chat afterward", async () => {
  test.skip(process.env.OLIVE_C7_LIVE !== "1", "Opt-in existing local models; no downloads.");
  test.setTimeout(300000);
  const root = path.resolve(".."), profile = await mkdtemp(path.join(tmpdir(), "olive-c7-live-ui-")), shim = path.join(profile, "shim");
  await mkdir(shim);
  await writeFile(path.join(shim, "sitecustomize.py"),
    `import sys,runpy\nsys.path.insert(0,${JSON.stringify(root)})\nrunpy.run_path(${JSON.stringify(path.join(root, "tests/fixtures/connect_inference_ui_runtime.py"))})\n`);
  const app = await electron.launch({ args: [path.resolve(".")], env: {
    ...process.env, OLIVE_DATA_DIR: profile, PYTHONPATH: shim, OLIVE_OLLAMA_HOST: "http://127.0.0.1:11434",
  }, timeout: 90000 });
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(20000);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const control = async (action: string, value = "") => {
      const id = crypto.randomUUID();
      await writeFile(path.join(profile, "fixture-command.tmp"), JSON.stringify({ id, action, value }));
      await rename(path.join(profile, "fixture-command.tmp"), path.join(profile, "fixture-command.json"));
      await expect.poll(async () => {
        try { return JSON.parse(await readFile(path.join(profile, "fixture-result.json"), "utf8")).id; }
        catch { return null; }
      }, { timeout: 90000 }).toBe(id);
      return JSON.parse(await readFile(path.join(profile, "fixture-result.json"), "utf8")).result;
    };
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Devices");
    await page.getByRole("button", { name: /127\.0\.0\.1/ }).click();
    await page.getByRole("button", { name: "Turn Connect on", exact: true }).click();
    const peer = await control("connect");
    await control("permission", "allow");
    await openSpace(page, "Chat");
    await page.getByLabel("OLIVE preset").selectOption("fast");
    await expect(page.getByLabel("Run on").locator(`option[value="${peer}"]`)).toContainText("Online");
    await page.getByLabel("Run on").selectOption(peer);
    const send = async (prompt: string) => {
      await page.getByRole("textbox", { name: "Message OLIVE", exact: true }).fill(prompt);
      await page.getByRole("button", { name: "Send message", exact: true }).click();
    };
    await send("Explain how local text inference works in one short sentence.");
    await expect(page.getByText("Answered by C7 paired desktop · OLIVE FAST").last()).toBeVisible({ timeout: 140000 });
    expect((await control("counts")).peer.models).toEqual(["qwen3:8b"]);
    await send("Give me code for a Python calculator with fifty documented arithmetic functions and examples.");
    await expect(page.locator(".message-writing")).toBeVisible({ timeout: 90000 });
    await page.getByRole("button", { name: "Stop response", exact: true }).click();
    await expect(page.getByText("Incomplete response", { exact: false }).last()).toBeVisible();
    await expect.poll(async () => (await control("counts")).peer.active).toBe(false);
    await page.getByLabel("Run on").selectOption("");
    await send("Explain how a Python function returns a value in one short sentence.");
    await expect(page.getByRole("button", { name: "Send message", exact: true })).toBeVisible({ timeout: 90000 });
    const text = await page.locator(".message-assistant").last().innerText();
    expect(text.length).toBeGreaterThan(20);
    expect(text).not.toContain("Incomplete response");
    const evidence = path.join(root, "artifacts/connect-c7");
    await mkdir(evidence, { recursive: true });
    await page.screenshot({ path: path.join(evidence, "live-fast-cancel-local.png") });
    expect(errors).toEqual([]);
  } finally {
    await app.close();
  }
});
