import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";

test("wip clarity screens", async () => {
  test.setTimeout(300000);
  const root = path.resolve("..");
  const evidence = path.resolve(path.join(root, "artifacts/ui-review/clarity", "wip"));
  await mkdir(evidence, { recursive: true });
  const profile = await mkdtemp(path.join(tmpdir(), "olive-clarity-"));
  const seed = spawnSync(path.join(root, ".venv/Scripts/python.exe"), [path.join(root, "scripts/seed_visual_fixture.py"), profile], { cwd: root, encoding: "utf8", windowsHide: true });
  expect(seed.status, seed.stderr).toBe(0);
  const app = await electron.launch({ args: [path.resolve(".")], env: { ...process.env, OLIVE_DATA_DIR: profile, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1" } });
  const errors: string[] = [];
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(30000);
    page.on("pageerror", (e) => errors.push(e.message));
    const size = async (w: number, h: number) => {
      await app.evaluate(({ BrowserWindow }, s) => BrowserWindow.getAllWindows()[0].setContentSize(s[0], s[1]), [w, h]);
      await page.waitForTimeout(350);
    };
    const shot = async (n: string) => { await page.waitForTimeout(250); await page.screenshot({ path: path.join(evidence, `${n}.png`) }); };
    await size(1440, 900);
    await expect(page.getByRole("button", { name: "Enter OLIVE", exact: true })).toBeVisible({ timeout: 60000 });
    await shot("01-welcome");
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await expect(page.locator("main.home")).toBeVisible();
    await page.waitForTimeout(900);
    await shot("02-home");
    await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Studio", exact: true }).click();
    await page.waitForTimeout(900);
    await shot("03-studio-empty");
    await size(1920, 1080);
    await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Home", exact: true }).click();
    await shot("04-home-1920");
    await size(1366, 768);
    await shot("05-home-1366");
  } finally {
    await app.close();
  }
  expect(errors).toEqual([]);
});
