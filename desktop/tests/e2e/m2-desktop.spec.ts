import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { openSpace } from "./shell";

test("Chat replaces the control workspace; status is inert and shared Stop invalidates input", async () => {
  const profile = await mkdtemp(path.join(tmpdir(), "olive-unified-inert-"));
  const app = await electron.launch({ args: [path.resolve(".")], env: { ...process.env, OLIVE_DATA_DIR: profile, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1" } });
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Chat");
    await expect(page.getByRole("textbox", { name: "Message OLIVE", exact: true })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Desktop Control", exact: true })).toHaveCount(0);
    await page.getByRole("button", {name:"Find anything",exact:true}).click();
    await page.getByRole("button", {name:"Open Desktop tasks",exact:true}).click();
    await expect(page.getByRole("textbox", {name:"Message OLIVE",exact:true})).toBeVisible();
    const state = await page.evaluate(() => window.olive.call("desktop.status", {}));
    expect(state).toMatchObject({ active: false, session: null, settings: { enabled: false } });
    await page.getByRole("button", { name: "OLIVE activity", exact: true }).click();
    await page.getByRole("button", { name: "Stop desktop control", exact: true }).click();
    await expect.poll(async () => (await page.evaluate(() => window.olive.call("desktop.status", {})) as {stopped:boolean}).stopped).toBe(true);
    const cancellation = await page.evaluate(async () => {
      try { await window.olive.call("desktop.open_application", { application_id: "fixture-never-opened" }); return "unexpected success"; }
      catch (error) { return String(error); }
    });
    expect(cancellation).toContain("cancelled");
    await expect(page.getByRole("button", { name: "Reset Stop", exact: true })).toHaveCount(0);
  } finally { await app.close(); }
});
