import { test, expect, _electron as electron } from "@playwright/test";
import { mkdtemp, writeFile, access, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

test("target-only launch UI keeps disabled/deny state and Stop cancels real launch approval without executing", async () => {
  const profile = await mkdtemp(path.join(tmpdir(), "olive-owned-launch-fixture-"));
  const script = path.join(profile, "fixture.py");
  const marker = path.join(profile, "must-not-exist.txt");
  await writeFile(script, `from pathlib import Path\nPath(${JSON.stringify(marker)}).write_text('unexpected')\n`);
  const app = await electron.launch({ args: [path.resolve(".")], env: { ...process.env, OLIVE_DATA_DIR: profile, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1" } });
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    const openDesktop = async () => {
      await page.getByRole("button", { name: "Find anything", exact: true }).click();
      await page.getByRole("button", { name: "Open Desktop Control", exact: true }).click();
    };
    await openDesktop();
    if (!(await page.getByRole("combobox", { name: "Local launch type" }).isVisible()))
      await page.getByText("Developer Details", { exact: true }).click();
    await expect(page.getByRole("button", { name: "Choose and review launch" })).toBeDisabled();
    await expect(page.getByRole("region", { name: "Target-only launch" })).toContainText("Keyboard policy: deny");
    const rejected = await page.evaluate(async () => {
      try { await window.olive.call("desktop.launch_local" as never, { path: "untrusted.py", kind: "python" } as never); return false; }
      catch { return true; }
    });
    expect(rejected).toBe(true);
    // Isolated fixture UI enablement; keyboard and mouse DENY are not changed.
    await page.getByRole("button", { name: "Control permissions", exact: true }).click();
    await page.getByRole("navigation", { name: "Settings categories" }).getByRole("button", { name: "Desktop Control", exact: true }).click();
    await page.getByRole("checkbox", { name: "enabled", exact: true }).check();
    await page.getByRole("button", { name: "Save desktop policies", exact: true }).click();
    await expect(page.getByText("Desktop policies saved.", { exact: true })).toBeVisible();
    await openDesktop();
    if (!(await page.getByRole("combobox", { name: "Local launch type" }).isVisible()))
      await page.getByText("Developer Details", { exact: true }).click();
    await page.getByRole("combobox", { name: "Local launch type" }).selectOption("python");
    await app.evaluate(({ dialog }, selected) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [selected] }); }, script);
    await page.getByRole("button", { name: "Choose and review launch" }).click();
    await expect(page.getByRole("heading", { name: "Your approval is needed" })).toBeVisible();
    await expect(page.getByRole("dialog")).toContainText("Run this selected local script");
    expect((await page.getByRole("dialog").innerText()).toLowerCase()).toContain(script.toLowerCase());
    await expect(page.getByRole("dialog")).toContainText("not in an execution sandbox");
    const out = path.resolve("../artifacts/ui-review/M2-owned-launch");
    await mkdir(out, { recursive: true });
    await page.screenshot({ path: path.join(out, "controlled-launch-approval.png") });
    // Exercise the actual emergency preload path while approval is pending;
    // deliberately do not click any approval button or launch the fixture script.
    await page.evaluate(() => window.olive.stopControl());
    await expect(page.getByRole("heading", { name: "Your approval is needed" })).toBeHidden();
    const status = await page.evaluate(() => window.olive.call("desktop.status", {})) as { stopped: boolean; settings: { keyboard_policy: string; mouse_policy: string } };
    expect(status.stopped).toBe(true);
    expect(status.settings.keyboard_policy).toBe("deny");
    expect(status.settings.mouse_policy).toBe("deny");
    expect(await page.evaluate(() => window.olive.call("desktop.launches", {}))).toEqual([]);
    expect(await access(marker).then(() => true, () => false)).toBe(false);
    await writeFile(path.join(out, "controlled-result.json"), JSON.stringify({ classification: "Controlled fixture; actual Electron/Python approval cancellation, no desktop target launched or inspected", status, markerCreated: false }, null, 2));
  } finally { await app.close(); }
});
