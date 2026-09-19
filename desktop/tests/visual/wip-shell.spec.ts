import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";

// Work-in-progress shell inspection: isolated seeded profile, a handful of
// screens, no assertions beyond page errors. Not part of the ordinary suite.
test("wip shell screens", async () => {
  test.setTimeout(300000);
  const root = path.resolve("..");
  const evidence = path.resolve(
    process.env.OLIVE_CAPTURE_DIR ||
      path.join(root, "artifacts/ui-review/redesign", "wip-shell"),
  );
  await mkdir(evidence, { recursive: true });
  const profile = await mkdtemp(path.join(tmpdir(), "olive-wip-shell-"));
  const seed = spawnSync(
    path.join(root, ".venv/Scripts/python.exe"),
    [path.join(root, "scripts/seed_visual_fixture.py"), profile],
    { cwd: root, encoding: "utf8", windowsHide: true },
  );
  expect(seed.status, seed.stderr).toBe(0);
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
    },
  });
  const errors: string[] = [];
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(20000);
    page.on("pageerror", (error) => errors.push(error.message));
    const size = async (w: number, h: number) => {
      await app.evaluate(
        ({ BrowserWindow }, s) =>
          BrowserWindow.getAllWindows()[0].setContentSize(s[0], s[1]),
        [w, h],
      );
      await page.waitForTimeout(350);
    };
    const shot = async (name: string) => {
      await page.waitForTimeout(250);
      await page.screenshot({ path: path.join(evidence, `${name}.png`) });
    };
    await size(1440, 900);
    await expect(
      page.getByText(/Ready to open/),
    ).toBeVisible({ timeout: 60000 });
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await expect(page.locator("main.home")).toBeVisible();
    await page.waitForTimeout(800);
    await shot("01-home-empty-1440");
    const nav = page.getByRole("navigation", { name: "Main navigation" });
    await nav.getByRole("button", { name: "All Spaces", exact: true }).click();
    await shot("02-launcher-1440");
    await page
      .getByRole("dialog", { name: "Spaces" })
      .getByRole("button", { name: "Chat", exact: true })
      .click();
    await expect(page.locator(".messages")).toBeVisible();
    await shot("03-chat-tab-1440");
    await nav.getByRole("button", { name: "All Spaces", exact: true }).click();
    await page
      .getByRole("dialog", { name: "Spaces" })
      .getByRole("button", { name: "Studio", exact: true })
      .click();
    await page.getByRole("button", { name: "Fixture · local Python project" }).first().click();
    await page.getByRole("treeitem", { name: "main.py", exact: true }).click();
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 30000 });
    await shot("04-studio-tab-1440");
    for (const name of ["Mail", "Calendar", "Research", "Agent", "Projects", "Knowledge"]) {
      await nav.getByRole("button", { name: "All Spaces", exact: true }).click();
      await page
        .getByRole("dialog", { name: "Spaces" })
        .getByRole("button", { name, exact: true })
        .click();
      await page.waitForTimeout(400);
    }
    await shot("05-many-tabs-1440");
    await nav.getByRole("button", { name: /^Open work/ }).click();
    await shot("06-switcher-1440");
    await page.keyboard.press("Escape");
    await nav.getByRole("button", { name: "Home", exact: true }).click();
    await page.waitForTimeout(400);
    await shot("07-home-with-tabs-1440");
    await size(1366, 768);
    await shot("08-home-1366");
    await size(1000, 700);
    await shot("09-home-1000");
    await nav.getByRole("button", { name: "Find anything", exact: true }).click();
    await shot("10-palette-1000");
    await page.keyboard.press("Escape");
    await size(1920, 1080);
    await nav.getByRole("button", { name: "Home", exact: true }).click();
    await shot("11-home-1920");
  } finally {
    await app.close();
  }
  expect(errors).toEqual([]);
});
