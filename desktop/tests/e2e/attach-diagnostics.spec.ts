import { test, expect, _electron as electron } from "@playwright/test";
import { mkdtemp, readdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

test("real attach rejection retains request ID and safe stage without reaching a provider", async () => {
  const profile = await mkdtemp(path.join(tmpdir(), "olive-attach-diagnostic-fixture-"));
  const app = await electron.launch({ args: [path.resolve(".")], env: { ...process.env, OLIVE_DATA_DIR: profile, OLIVE_ATTACH_DIAGNOSTICS: "1", OLIVE_OLLAMA_HOST: "http://127.0.0.1:1" } });
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await page.getByRole("button", { name: "Find anything", exact: true }).click();
    await page.getByRole("button", { name: "Open Desktop Control", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Desktop Control", exact: true })).toBeVisible();
    const result = await page.evaluate(async () => {
      let receive!: (value:unknown)=>void;
      const detail = new Promise<unknown>(resolve=>{receive=resolve;});
      const unsubscribe = window.olive.subscribe(event => {
        if (event.topic === "request.failure" && (event.data as {method?:string}).method === 'desktop.attach_launch') receive(event.data);
      });
      try {
        await window.olive.call("desktop.attach_launch", { launch_id: "nonexistent-fixture-reference" });
        return { message: "unexpected success", detail: null };
      } catch (error) {
        // The event and invoke rejection cross different Electron IPC channels.
        // Wait for the actual subscribed event, never assume delivery ordering.
        return { message: String(error), detail: await detail };
      } finally { unsubscribe(); }
    });
    expect(result.detail).toMatchObject({ method: "desktop.attach_launch", provider_reached: false, category: "PermissionError", diagnostic_saved: true });
    const detail = result.detail as { error_id: string; request_id: string; stage: string };
    expect(detail.request_id).toMatch(/^[a-f0-9-]{36}$/);
    expect(result.message).toContain(detail.error_id);
    await page.getByText("Attachment error details", { exact: true }).click();
    await expect(page.locator("details").filter({ hasText: "Attachment error details" })).toContainText(detail.request_id);
    expect(await readdir(path.join(profile, "developer-diagnostics"))).toEqual([`${detail.error_id}.${process.platform==='win32'?'dpapi':'json'}`]);
    const state = await page.evaluate(() => window.olive.call("desktop.status", {}));
    expect(state).toMatchObject({ session: null, observation: {}, settings: { enabled: false, keyboard_policy: "deny", mouse_policy: "deny" } });
  } finally { await app.close(); }
});
