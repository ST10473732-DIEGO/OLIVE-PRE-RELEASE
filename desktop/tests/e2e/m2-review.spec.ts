import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { record } from "./recording";
import { goHome, openSpace } from "./shell";

test("M2 actual cross-feature review recording and retained local Studio validation", async () => {
  const root = path.resolve("..");
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m2-review-"));
  const seed = spawnSync(
    path.join(root, ".venv/Scripts/python.exe"),
    [path.join(root, "scripts/seed_m2_handoff_fixture.py"), profile],
    { cwd: root, encoding: "utf8", windowsHide: true },
  );
  expect(seed.status, seed.stderr).toBe(0);
  const evidence = path.join(root, "artifacts/ui-review/M2/cross-feature");
  await mkdir(evidence, { recursive: true });
  const started = performance.now();
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
    },
  });
  try {
    const page = await app.firstWindow();
    await expect(
      page.getByRole("button", { name: "Enter OLIVE", exact: true }),
    ).toBeVisible();
    const welcomeVisibleMs = performance.now() - started;
    const dimensions = await app.evaluate(({ BrowserWindow }) => {
      const window = BrowserWindow.getAllWindows()[0];
      return {
        outer: window.getSize(),
        content: window.getContentSize(),
        zoom: window.webContents.getZoomFactor(),
      };
    });
    const finish = await record(
      page,
      evidence,
      "m2-cross-feature-navigation.mp4",
    );
    const navigation: { route: string; observedMs: number }[] = [];
    const shot = async (name: string) => {
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(evidence, `${name}.png`) });
    };
    const go = async (name: string) => {
      const before = performance.now();
      await page
        .getByRole("button", { name: "Find anything", exact: true })
        .click();
      await page
        .getByRole("button", { name: `Open ${name}`, exact: true })
        .click();
      if (name === "Chat")
        await expect(page.locator(".conversation")).toBeVisible();
      else
        await expect(
          page.getByRole("heading", { name, exact: true }).first(),
        ).toBeVisible();
      navigation.push({ route: name, observedMs: performance.now() - before });
      await page.waitForTimeout(1200);
    };
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).hover();
    await page.waitForTimeout(800);
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await shot("home-fixture");
    await goHome(page);
    await shot("home-launcher");
    await go("Chat");
    await shot("chat-fixture");
    await go("Agent");
    await page.getByRole("button", { name: /Fixture linked task/ }).click();
    await shot("agent-fixture");
    await go("Research");
    await expect(
      page.getByRole("heading", { name: "Fixture report", exact: true }),
    ).toBeVisible();
    await shot("research-fixture");
    await go("Projects");
    await page.getByRole("button", { name: /Fixture linked project/ }).click();
    await shot("projects-fixture");
    await go("Knowledge");
    await shot("knowledge-fixture");
    await go("Memory");
    await shot("memory-fixture");
    await go("Settings");
    await shot("settings");
    await go("Desktop Control");
    await shot("desktop-empty");
    await openSpace(page, "Studio");
    await page
      .getByRole("button", { name: "Fixture review workspace", exact: true })
      .click();
    await page.getByRole("treeitem", { name: "main.py", exact: true }).click();
    const editor = page.getByRole("textbox", { name: "Source editor" });
    await editor.press("Control+End");
    await editor.press("Enter");
    await editor.pressSequentially("# Fixture review: actual edit and save");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await page.getByRole("button", { name: "Test", exact: true }).click();
    await expect(page.locator(".output-terminal")).toContainText("OK", {
      timeout: 30000,
    });
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.locator(".output-terminal")).toContainText("OK");
    await shot("studio-real-test-after-save");
    await goHome(page);
    await page.waitForTimeout(1200);
    await openSpace(page, "Studio");
    await expect(page.locator(".output-terminal")).toContainText("OK");
    await expect(page.locator(".monaco-editor .view-lines")).toContainText(
      "Fixture review: actual edit and save",
    );
    await page.waitForTimeout(1800);
    const recording = await finish();
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setSize(1366, 768),
    );
    await shot("studio-1366-retained");
    for (const name of ["Agent", "Research", "Projects", "Knowledge", "Memory", "Settings", "Desktop Control"]) {
      await go(name);
      expect(await page.evaluate(() => document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
      await shot(`${name.toLowerCase().replaceAll(" ","-")}-1366`);
    }
    const metrics = await app.evaluate(({ app }) =>
      app
        .getAppMetrics()
        .map((process) => ({
          type: process.type,
          memory: process.memory,
          cpu: process.cpu,
        })),
    );
    await writeFile(
      path.join(evidence, "measurements.json"),
      JSON.stringify(
        {
          fixture: true,
          dimensions,
          welcomeVisibleMs,
          navigation,
          recording,
          metrics,
          limitations:
            "Warm developer environment; automated interaction timings include test overhead. Event-driven capture is not a frame-rate measurement. These are Electron process metrics, not combined Ollama/GPU or a Qt comparison.",
        },
        null,
        2,
      ),
    );
  } finally {
    await app.close();
  }
});
