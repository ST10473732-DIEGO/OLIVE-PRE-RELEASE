import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile, readFile, rename } from "node:fs/promises";
import { tmpdir } from "node:os";
import { openSpace } from "./shell";

test("C7 actual Chat target, trusted Ask, streaming, Stop and local interoperability", async () => {
  test.setTimeout(180000);
  const root = path.resolve(".."), profile = await mkdtemp(path.join(tmpdir(), "olive-c7-ui-")), shim = path.join(profile, "shim");
  await mkdir(shim);
  await writeFile(path.join(shim, "sitecustomize.py"),
    `import sys,runpy\nsys.path.insert(0,${JSON.stringify(root)})\nrunpy.run_path(${JSON.stringify(path.join(root, "tests/fixtures/connect_inference_ui_runtime.py"))})\n`);
  const app = await electron.launch({ args: [path.resolve(".")], env: {
    ...process.env, OLIVE_DATA_DIR: profile, PYTHONPATH: shim, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
  } });
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
      }).toBe(id);
      return JSON.parse(await readFile(path.join(profile, "fixture-result.json"), "utf8")).result;
    };
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Devices");
    await page.getByRole("button", { name: /127\.0\.0\.1/ }).click();
    await page.getByRole("button", { name: "Turn Connect on", exact: true }).click();
    const peer = await control("connect");
    await page.getByRole("button", { name: /^C7 paired desktop.*Online/ }).click();
    await page.getByRole("button", { name: "Permissions", exact: true }).click();
    const permission = page.getByRole("group", { name: "Remote AI", exact: true });
    await expect(permission.getByRole("button", { name: "Off", exact: true })).toHaveAttribute("aria-pressed", "true");
    await permission.getByRole("button", { name: "Ask", exact: true }).click();
    await control("incoming");
    await expect(page.getByText("Tool-free text inference only.", { exact: false })).toBeVisible();
    await page.getByRole("button", { name: "Deny", exact: true }).click();
    expect((await control("incoming_done")).error).toContain("denied");
    expect((await control("counts")).local).toBe(0);
    await control("incoming");
    await page.getByRole("button", { name: "Allow once", exact: true }).click();
    expect((await control("incoming_done")).error).toBeNull();
    await expect(permission.getByRole("button", { name: "Ask", exact: true })).toHaveAttribute("aria-pressed", "true");
    await permission.getByRole("button", { name: "Allow", exact: true }).click();
    await control("local_mode", "long");
    await control("incoming");
    await page.getByRole("button", { name: "Status", exact: true }).click();
    await page.getByRole("button", { name: "Stop remote inference", exact: true }).click();
    expect((await control("incoming_done")).error).toContain("stopped");
    await control("local_mode", "normal");
    await control("permission", "allow");
    await openSpace(page, "Chat");
    await page.getByLabel("OLIVE preset").selectOption("fast");
    await expect(page.getByLabel("Run on").locator(`option[value="${peer}"]`)).toContainText("Online");
    await page.getByLabel("Run on").selectOption(peer);
    const send = async () => {
      await page.getByRole("textbox", { name: "Message OLIVE" }).fill("Give me code for a calculator.");
      await page.getByRole("button", { name: "Send message", exact: true }).click();
    };
    await send();
    await expect(page.getByText("Answered by C7 paired desktop · OLIVE FAST").last()).toBeVisible();
    await control("mode", "long");
    await send();
    await expect(page.getByText("Thinking on C7 paired desktop · OLIVE FAST")).toBeVisible();
    await expect(page.locator(".message-writing")).toBeVisible();
    await page.getByRole("button", { name: "Stop response", exact: true }).click();
    await expect(page.getByText("Incomplete response", { exact: false }).last()).toBeVisible();
    await expect.poll(async () => (await control("counts")).peer.active).toBe(false);
    await page.getByLabel("Run on").selectOption("");
    await send();
    await expect.poll(async () => (await control("counts")).local).toBe(3);
    await expect(page.getByRole("button", { name: "Send message", exact: true })).toBeVisible();
    await page.getByLabel("Run on").selectOption(peer);
    await control("disconnect");
    await send();
    await expect(page.getByText("The selected device is offline or Connect is Off.", { exact: false })).toBeVisible();
    expect((await control("counts")).local).toBe(3);
    const evidence = path.join(root, "artifacts/connect-c7");
    await mkdir(evidence, { recursive: true });
    await page.screenshot({ path: path.join(evidence, "chat-remote-partial-no-fallback.png") });
    expect(errors).toEqual([]);
  } finally {
    await app.close();
  }
});
