import { test, expect, _electron as electron, type Page } from "@playwright/test";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { openSpace } from "./shell";

// The Core is the OLIVE mark (the same drawing as the app icon) with its state:
// it draws itself in on Welcome, a ring turns only while OLIVE really works,
// attention states carry a badge, and every animation pauses while hidden and
// stops under Reduce Motion.
const animations = (page: Page, selector: string) =>
  page.locator(selector).first().evaluate((el) =>
    el.getAnimations({ subtree: true }).map((a) => ({
      name: (a as CSSAnimation).animationName,
      state: a.playState,
    })),
  );

test("the OLIVE mark draws in, turns only for real work, and pauses hidden or reduced", async () => {
  test.setTimeout(120000);
  const root = path.resolve(".."),
    profile = await mkdtemp(path.join(tmpdir(), "olive-logo-core-"));
  const seed = spawnSync(
    path.join(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"),
    [path.join(root, "scripts/seed_electron_fixture.py"), profile],
    { cwd: root, encoding: "utf8", windowsHide: true },
  );
  expect(seed.status, seed.stderr).toBe(0);
  await writeFile(
    path.join(profile, "fixture-workspace/tests/test_main.py"),
    "import unittest,time\nclass CoreLocalCheck(unittest.TestCase):\n def test_local(self):\n  time.sleep(3)\n  self.assertEqual(2+2,4)\n",
  );
  const evidence = path.join(root, "artifacts/core/acceptance");
  await mkdir(evidence, { recursive: true });
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: { ...process.env, OLIVE_DATA_DIR: profile, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1" },
  });
  try {
    const page = await app.firstWindow();
    const core = ".core-transit-stage .core";
    // Welcome: the mark draws itself in (olive, then pimento and shine).
    await expect(page.locator(".welcome-core .core-logo")).toBeVisible();
    const welcome = await animations(page, ".welcome-core .core");
    expect(welcome.map((a) => a.name)).toEqual(
      expect.arrayContaining(["grove-olive-grow", "grove-pim-pop"]),
    );
    await page.screenshot({ path: path.join(evidence, "welcome-mark.png") });
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await expect(page.locator("main.home")).toBeVisible();
    // At rest in the navigation brand: small, and nothing turns.
    await expect
      .poll(() => page.locator(core).evaluate((el) => el.getBoundingClientRect().width))
      .toBeLessThan(30);
    await expect(page.locator(`${core} .core-ring`)).toHaveCount(0);
    expect((await animations(page, core)).filter((a) => a.state === "running")).toEqual([]);
    await page.screenshot({ path: path.join(evidence, "compact-idle.png") });
    // Real work: a Python unittest run in Studio turns the ring, then it stops.
    await openSpace(page, "Studio");
    await page.getByRole("button", { name: /Fixture.*local Python project/ }).click();
    await page.getByRole("button", { name: "Test", exact: true }).click();
    await expect(page.locator(core)).toHaveAttribute("data-state", "Working");
    await expect(page.locator(`${core} .core-ring`)).toBeVisible();
    expect(await animations(page, core)).toContainEqual({ name: "grove-spin", state: "running" });
    await page.screenshot({ path: path.join(evidence, "compact-live-working.png") });
    await expect(page.locator(".output-terminal")).toContainText("OK", { timeout: 15000 });
    await expect(page.locator(core)).toHaveAttribute("data-state", "Ready", { timeout: 10000 });
    await expect(page.locator(`${core} .core-ring`)).toHaveCount(0);
    // Presentation fixtures through the real event path: only work turns;
    // approvals, pauses and errors carry a badge instead.
    const states = ["Thinking", "Researching", "Approval required", "Paused", "Error", "Degraded", "Ready"];
    for (const [index, state] of states.entries()) {
      await app.evaluate(
        ({ BrowserWindow }, value) =>
          BrowserWindow.getAllWindows()[0].webContents.send("olive:event", {
            v: 1,
            kind: "event",
            seq: value.seq,
            topic: "runtime.activity",
            data: { state: value.state, items: [], count: 0, summary: "Synthetic Core presentation fixture; no task executed." },
          }),
        { state, seq: 90000 + index },
      );
      await expect(page.locator(core)).toHaveAttribute("data-state", state);
      await expect(page.locator(`${core} .core-ring`)).toHaveCount(["Thinking", "Researching"].includes(state) ? 1 : 0);
      await expect(page.locator(`${core} .olive-core-status`)).toHaveCount(
        ["Approval required", "Paused", "Error", "Degraded"].includes(state) ? 1 : 0,
      );
      await page.screenshot({ path: path.join(evidence, `fixture-${state.toLowerCase().replaceAll(" ", "-")}.png`) });
    }
    // A hidden window pauses the turning ring; showing it again resumes it.
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].webContents.send("olive:event", {
        v: 1, kind: "event", seq: 90100, topic: "runtime.activity",
        data: { state: "Thinking", items: [], count: 0, summary: "Synthetic Core presentation fixture; no task executed." },
      }),
    );
    await expect(page.locator(`${core} .core-ring`)).toBeVisible();
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].minimize());
    await expect
      .poll(async () => (await animations(page, core)).find((a) => a.name === "grove-spin")?.state)
      .toBe("paused");
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].restore());
    await expect
      .poll(async () => (await animations(page, core)).find((a) => a.name === "grove-spin")?.state)
      .toBe("running");
    // Reduce Motion (the setting or the system preference) stops the ring.
    await page.evaluate(() => (document.documentElement.dataset.reduced = "true"));
    await expect.poll(async () => (await animations(page, core)).length).toBe(0);
    await page.evaluate(() => (document.documentElement.dataset.reduced = "false"));
    await page.emulateMedia({ reducedMotion: "reduce" });
    await expect.poll(async () => (await animations(page, core)).length).toBe(0);
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await expect.poll(async () => (await animations(page, core)).length).toBeGreaterThan(0);
    await writeFile(
      path.join(evidence, "result.json"),
      JSON.stringify({ classification: "real Electron renderer; actual Python unittest validation in synthetic workspace; no local model required", states }, null, 2),
    );
  } finally {
    await app.close();
  }
});
