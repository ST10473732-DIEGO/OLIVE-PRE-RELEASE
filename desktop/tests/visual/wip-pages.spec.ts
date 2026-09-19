import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { openSpace, openHistory } from "../e2e/shell";

// After-evidence for the recomposed pages: Chat (conversation-first, on-demand
// history), Mail (two-pane reading + full-width compose), and a light-theme
// Home. Isolated seeded profile; not part of the ordinary suite.
test("wip recomposed pages", async () => {
  test.setTimeout(300000);
  const root = path.resolve("..");
  const evidence = path.resolve(path.join(root, "artifacts/ui-review/redesign", "wip-pages"));
  await mkdir(evidence, { recursive: true });
  const profile = await mkdtemp(path.join(tmpdir(), "olive-wip-pages-"));
  const seed = spawnSync(
    path.join(root, ".venv/Scripts/python.exe"),
    [path.join(root, "scripts/seed_visual_fixture.py"), profile],
    { cwd: root, encoding: "utf8", windowsHide: true },
  );
  expect(seed.status, seed.stderr).toBe(0);
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: { ...process.env, OLIVE_DATA_DIR: profile, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1" },
  });
  const errors: string[] = [];
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(20000);
    page.on("pageerror", (error) => errors.push(error.message));
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1440, 900));
    const shot = async (name: string) => {
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(evidence, `${name}.png`) });
    };
    await expect(page.getByText(/Ready to open/)).toBeVisible({ timeout: 60000 });
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();

    // Chat: conversation fills the width; history is on demand.
    await openSpace(page, "Chat");
    await expect(page.locator(".messages")).toBeVisible();
    await shot("01-chat-conversation");
    await openHistory(page);
    await shot("02-chat-history-open");
    await page.getByRole("button", { name: "Close conversation history", exact: true }).click();

    // Mail: two-pane reading, then a message, then full-width compose.
    await openSpace(page, "Mail");
    await expect(page.locator(".mail-list")).toBeVisible();
    await shot("03-mail-two-pane");
    const firstMessage = page.locator(".mail-list-item").first();
    if (await firstMessage.count()) {
      await firstMessage.click();
      await expect(page.locator(".mail-detail")).toBeVisible();
      await shot("04-mail-reading");
    }
    await page.getByRole("button", { name: "Compose", exact: true }).click();
    await expect(page.locator(".mail-layout.composing")).toBeVisible();
    await shot("05-mail-compose-fullwidth");

    // Home in the light theme.
    await page.getByRole("button", { name: "Home", exact: true }).click();
    await page.getByRole("button", { name: "OLIVE activity", exact: true }).click();
    await page.getByRole("button", { name: "Toggle theme", exact: true }).click();
    await page.keyboard.press("Escape");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await shot("06-home-light");
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1920, 1080));
    await shot("07-home-light-1920");
  } finally {
    await app.close();
  }
  expect(errors).toEqual([]);
});
