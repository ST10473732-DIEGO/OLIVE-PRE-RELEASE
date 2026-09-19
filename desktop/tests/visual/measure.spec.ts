import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";

// Identical procedure to the baseline measurement (run against the baseline
// worktree) so the numbers compare like for like.
test("baseline measurements", async () => {
  const root = path.resolve("..");
  const evidence = path.resolve(process.env.OLIVE_CAPTURE_DIR!);
  await mkdir(evidence, { recursive: true });
  const profile = await mkdtemp(path.join(tmpdir(), "olive-baseline-measure-"));
  const seed = spawnSync(
    process.env.OLIVE_PYTHON!,
    [path.join(root, "scripts/seed_electron_fixture.py"), profile],
    { cwd: root, encoding: "utf8", windowsHide: true },
  );
  expect(seed.status, seed.stderr).toBe(0);
  const startedAt = performance.now();
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
    },
  });
  const timings: Record<string, number> = {};
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(20000);
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setContentSize(1440, 900),
    );
    await expect(
      page.getByText(/Ready to open/),
    ).toBeVisible({ timeout: 60000 });
    timings.startupToReadyMs = Math.round(performance.now() - startedAt);
    const button = (name: string) =>
      page.getByRole("button", { name, exact: true }).first();
    await button("Enter OLIVE").click();
    await expect(page.locator("main.home")).toBeVisible();
    const go = async (name: string) => {
      const started = performance.now();
      await button("Find anything").click();
      await button("Open " + name).click();
      await page.waitForTimeout(200);
      timings["navigate:" + name] = Math.round(performance.now() - started);
    };
    for (const name of ["Chat", "Agent", "Studio", "Mail", "Calendar", "Settings", "Home"])
      await go(name);
    const rail = page.getByRole("navigation", { name: "Main navigation" });
    for (const [name, heading] of [
      ["Agent", "Agent"],
      ["Research", "Research"],
      ["Studio", "Your next idea starts here."],
    ] as const) {
      const started = performance.now();
      await rail.getByRole("button", { name, exact: true }).click();
      await expect(
        page.getByRole("heading", { name: heading, exact: true }),
      ).toBeVisible();
      timings["rail:" + name] = Math.round(performance.now() - started);
    }
    await button("Fixture · local Python project").click();
    await page.getByRole("treeitem", { name: "main.py", exact: true }).click();
    const editor = page.getByRole("textbox", { name: "Source editor" });
    await expect(editor).toBeVisible();
    const t = performance.now();
    await button("Test").click();
    await expect(
      page.locator('.task-result[data-task-state="completed"]'),
    ).toBeVisible({ timeout: 60000 });
    timings.studioTestToCompletedMs = Math.round(performance.now() - t);
    await editor.press("Control+End");
    await editor.press("Enter");
    const typingStarted = performance.now();
    await editor.pressSequentially(
      "# capture: sixty characters typed into the real editor here",
      { delay: 0 },
    );
    timings.monacoType60CharsMs = Math.round(performance.now() - typingStarted);
    await expect(page.locator(".monaco-editor")).toContainText("sixty characters");
    await go("Home");
    // Idle sample: percentCPUUsage is measured since the previous call, so
    // prime once, wait, then read a genuine idle interval.
    await app.evaluate(({ app }) => app.getAppMetrics());
    await page.waitForTimeout(3000);
    const memory = await app.evaluate(({ app }) =>
      app.getAppMetrics().map((m) => ({
        type: m.type,
        mb: Math.round(m.memory.workingSetSize / 1024),
        cpu: Math.round(m.cpu.percentCPUUsage * 100) / 100,
      })),
    );
    await writeFile(
      path.join(evidence, "measurements.json"),
      JSON.stringify(
        { label: process.env.OLIVE_CAPTURE_LABEL || "after", capturedAt: new Date().toISOString(), timings, memory },
        null,
        2,
      ),
    );
  } finally {
    await app.close();
  }
});
