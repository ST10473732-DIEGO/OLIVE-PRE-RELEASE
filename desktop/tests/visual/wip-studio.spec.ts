import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { openSpace } from "../e2e/shell";

// Work-in-progress Studio inspection on the seeded Python fixture: language
// server, terminal, structured tests and a real debugpy session.
test("wip studio python workflows", async () => {
  test.setTimeout(400000);
  const root = path.resolve("..");
  const evidence = path.resolve(path.join(root, "artifacts/ui-review/redesign", "wip-studio"));
  await mkdir(evidence, { recursive: true });
  const profile = await mkdtemp(path.join(tmpdir(), "olive-wip-studio-"));
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
    page.setDefaultTimeout(30000);
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error") errors.push("console: " + message.text());
    });
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1440, 900));
    const shot = async (name: string) => {
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(evidence, `${name}.png`) });
    };
    await expect(page.getByText(/Ready to open/)).toBeVisible({ timeout: 60000 });
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Studio");
    await page.getByRole("button", { name: "Fixture · local Python project" }).first().click();
    await page.getByRole("treeitem", { name: "main.py", exact: true }).click();
    const editor = page.getByRole("textbox", { name: "Source editor" });
    await expect(editor).toBeVisible();
    await shot("01-studio-editor");
    // Language server status appears in the strip; wait for it to be ready.
    const languageItem = page.locator(".strip-item.text-button[title*='Code intelligence']");
    await expect(languageItem).toContainText("ready", { timeout: 120000 });
    // Hover over the greeting call.
    await page.locator(".view-lines").getByText("greeting", { exact: true }).last().hover();
    await page.waitForTimeout(1200);
    await shot("02-hover");
    // Terminal.
    await page.keyboard.press("Control+`");
    await page.getByRole("button", { name: "New terminal", exact: true }).click();
    await page.getByRole("button", { name: "Open PowerShell", exact: true }).click();
    await expect(page.locator(".terminal-foot")).toContainText("Native powershell", { timeout: 30000 });
    await page.waitForTimeout(2500);
    await page.keyboard.type('Write-Output ("olive" + "-terminal-ok")');
    await page.keyboard.press("Enter");
    await expect(page.locator(".terminal-view .xterm-rows")).toContainText("olive-terminal-ok", { timeout: 30000 });
    await shot("03-terminal");
    // Structured tests.
    await page.getByRole("button", { name: /^Testing/ }).click();
    await page.getByRole("button", { name: "Run all", exact: true }).click();
    await expect(page.locator(".test-summary")).toBeVisible({ timeout: 90000 });
    await shot("04-tests");
    // Debugger: breakpoint on line 4 through the gutter, then launch.
    await page.getByRole("button", { name: "Show Debug", exact: true }).click();
    const gutter = page.locator(".margin-view-overlays .line-numbers", { hasText: /^4$/ }).first();
    const box = await gutter.boundingBox();
    expect(box).not.toBeNull();
    await page.mouse.click(box!.x - 16, box!.y + box!.height / 2);
    await expect(page.locator(".olive-breakpoint")).toHaveCount(1);
    await page.getByRole("button", { name: "Debug", exact: true }).click();
    await expect(page.locator(".debug-state")).toContainText("Paused", { timeout: 90000 });
    await expect(page.locator(".variable-leaf")).toContainText("name", { timeout: 30000 });
    await shot("05-debug-paused");
    await page.getByRole("button", { name: "Step over", exact: true }).click();
    await page.waitForTimeout(1200);
    await shot("06-debug-stepped");
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await expect(page.locator(".debug-state")).toContainText(/Ended|Stopped/, { timeout: 60000 });
    await shot("07-debug-ended");
    await page.keyboard.press("Control+Shift+M");
    await shot("08-problems");
    await page.getByRole("button", { name: "Ask OLIVE", exact: true }).click();
    await shot("09-assistant");
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1000, 700));
    await shot("10-narrow");
  } finally {
    await app.close();
  }
  expect(errors).toEqual([]);
});
