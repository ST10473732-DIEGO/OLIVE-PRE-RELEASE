import { test, expect, _electron as electron } from "@playwright/test";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { record } from "./recording";
import type { CoreMetrics } from "../../src/components/olive-core/renderer";
import { openSpace } from "./shell";
test("dot olive renders depth, follows real validation, and stops when idle hidden or reduced", async () => {
  test.setTimeout(120000);
  const root = path.resolve(".."),
    profile = await mkdtemp(path.join(tmpdir(), "olive-dot-core-"));
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
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
    },
  });
  try {
    const page = await app.firstWindow();
    const metrics = () =>
      page
        .locator(".olive-core-canvas:visible")
        .first()
        .evaluate((el) => ({
          ...(el as HTMLCanvasElement & { oliveCoreMetrics: CoreMetrics })
            .oliveCoreMetrics,
          sampledAt: performance.now(),
          pixelRatio: devicePixelRatio,
          bitmapWidth: (el as HTMLCanvasElement).width,
        }));
    await expect(
      page.getByRole("button", { name: "Enter OLIVE", exact: true }),
    ).toBeEnabled();
    await expect.poll(async () => (await metrics()).frames).toBeGreaterThan(2);
    const stopRecording = await record(page, evidence, "olive-core.mp4");
    const angles = [];
    for (const angle of [0.5, 1.6, 3.1, 5.5]) {
      await expect
        .poll(async () => (await metrics()).angle, { timeout: 15000 })
        .toBeGreaterThan(angle);
      angles.push(await metrics());
      await page.screenshot({
        path: path.join(evidence, `welcome-${angle}.png`),
      });
    }
    await page
      .getByRole("button", { name: "Enter OLIVE", exact: true })
      .click();
    await expect.poll(async () => (await metrics()).running).toBe(false);
    await expect(page.locator("main.home")).toHaveCSS("opacity", "1");
    await expect
      .poll(() =>
        page
          .locator(".core-transit-stage .core")
          .evaluate((el) => el.getBoundingClientRect().width),
      )
      .toBeLessThan(50);
    await page.screenshot({ path: path.join(evidence, "compact-idle.png") });
    const idle = await metrics();
    await page.waitForTimeout(350);
    expect((await metrics()).frames).toBe(idle.frames);
    await openSpace(page, "Studio");
    await page
      .getByRole("button", { name: /Fixture.*local Python project/ })
      .click();
    await page.getByRole("button", { name: "Test", exact: true }).click();
    await expect(page.locator(".core-transit-stage .core")).toHaveAttribute(
      "data-state",
      "Working",
    );
    await expect.poll(async () => (await metrics()).running).toBe(true);
    await page.screenshot({
      path: path.join(evidence, "compact-live-working.png"),
    });
    const active = await metrics();
    await expect(page.locator(".output-terminal")).toContainText("OK", {
      timeout: 15000,
    });
    await expect(page.locator(".core-transit-stage .core")).toHaveAttribute(
      "data-state",
      "Ready",
    );
    await expect
      .poll(async () => (await metrics()).running, { timeout: 10000 })
      .toBe(false);
    await page.screenshot({
      path: path.join(evidence, "compact-completed.png"),
    });
    const recording = await stopRecording();
    // Real system preference changes apply without restarting the renderer.
    await page.emulateMedia({ reducedMotion: "reduce" });
    await expect.poll(async () => (await metrics()).reduced).toBe(true);
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await page
      .getByRole("button", { name: "OLIVE activity", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    expect(await page.locator(".olive-core-canvas:visible").count()).toBe(1);
    // Reopen Welcome to inspect the live decorative loop under native visibility.
    await page.reload();
    await expect(
      page.getByRole("button", { name: "Enter OLIVE", exact: true }),
    ).toBeVisible();
    await expect.poll(async () => (await metrics()).running).toBe(true);
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].minimize(),
    );
    await expect
      .poll(() =>
        app.evaluate(({ BrowserWindow }) =>
          BrowserWindow.getAllWindows()[0].isMinimized(),
        ),
      )
      .toBe(true);
    await expect
      .poll(
        async () =>
          await page
            .locator(".olive-core-canvas")
            .first()
            .evaluate(
              (el) =>
                (el as HTMLCanvasElement & { oliveCoreMetrics: CoreMetrics })
                  .oliveCoreMetrics.running,
            ),
      )
      .toBe(false);
    const hidden = await page
      .locator(".olive-core-canvas")
      .first()
      .evaluate((el) => ({
        ...(el as HTMLCanvasElement & { oliveCoreMetrics: CoreMetrics })
          .oliveCoreMetrics,
      }));
    await page.waitForTimeout(350);
    expect(
      await page
        .locator(".olive-core-canvas")
        .first()
        .evaluate(
          (el) =>
            (el as HTMLCanvasElement & { oliveCoreMetrics: CoreMetrics })
              .oliveCoreMetrics.frames,
        ),
    ).toBe(hidden.frames);
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].restore(),
    );
    await expect.poll(async () => (await metrics()).running).toBe(true);
    await page.evaluate(
      () => (document.documentElement.dataset.reduced = "true"),
    );
    // The user's Welcome exception keeps its display rotation always on.
    await expect.poll(async () => (await metrics()).running).toBe(true);
    for (const light of [false, true]) {
      await app.evaluate(({ BrowserWindow }) =>
        BrowserWindow.getAllWindows()[0].setSize(1366, 768),
      );
      await page.evaluate(
        (v) => (document.documentElement.dataset.theme = v ? "light" : "dark"),
        light,
      );
      await page.screenshot({
        path: path.join(evidence, `reduced-${light ? "light" : "dark"}.png`),
      });
    }
    const densitySession = await page.context().newCDPSession(page);
    await densitySession.send("Emulation.setDeviceMetricsOverride", {
      width: 1366,
      height: 768,
      deviceScaleFactor: 3,
      mobile: false,
    });
    await expect.poll(() => page.evaluate(() => devicePixelRatio)).toBe(3);
    await expect
      .poll(() =>
        page
          .locator(".olive-core-canvas")
          .first()
          .evaluate((el) => (el as HTMLCanvasElement).width),
      )
      .toBeLessThanOrEqual(600);
    await page.screenshot({
      path: path.join(evidence, "reduced-light-dpr3.png"),
    });
    await densitySession.send("Emulation.clearDeviceMetricsOverride");
    await densitySession.detach();
    await page.evaluate(
      () => (document.documentElement.dataset.reduced = "false"),
    );
    await page
      .getByRole("button", { name: "Enter OLIVE", exact: true })
      .click();
    // Explicit presentation fixtures through the existing event path, not live task evidence.
    const variants = [];
    for (const state of [
      "Thinking",
      "Researching",
      "Approval required",
      "Paused",
      "Error",
      "Degraded",
      "Ready",
    ]) {
      await app.evaluate(
        ({ BrowserWindow }, value) =>
          BrowserWindow.getAllWindows()[0].webContents.send("olive:event", {
            v: 1,
            kind: "event",
            seq: value.seq,
            topic: "runtime.activity",
            data: {
              state: value.state,
              items: [],
              count: 0,
              summary: "Synthetic Core presentation fixture; no task executed.",
            },
          }),
        { state, seq: 90000 + variants.length },
      );
      await expect(page.locator(".core-transit-stage .core")).toHaveAttribute(
        "data-state",
        state,
      );
      await expect
        .poll(async () => (await metrics()).running, { timeout: 10000 })
        .toBe(["Thinking", "Researching"].includes(state));
      await page.screenshot({
        path: path.join(
          evidence,
          `fixture-${state.toLowerCase().replaceAll(" ", "-")}.png`,
        ),
      });
      variants.push({
        state,
        ...(await metrics()),
        classification: "synthetic main-process presentation event",
      });
    }
    await page
      .getByRole("button", { name: "OLIVE activity", exact: true })
      .click();
    await page.evaluate(() => window.olive.setInterfaceScale(1.5));
    await expect.poll(() => page.evaluate(() => innerWidth)).toBeLessThan(950);
    await expect
      .poll(() =>
        page
          .locator(".sheet")
          .evaluate((el) => el.getBoundingClientRect().right <= innerWidth + 1),
      )
      .toBe(true);
    // Native capture retains physical window bounds after Chromium zoom/DPR changes.
    const enlarged = await app.evaluate(async ({ BrowserWindow }) =>
      (await BrowserWindow.getAllWindows()[0].capturePage()).toDataURL(),
    );
    await writeFile(
      path.join(evidence, "enlarged-activity.png"),
      Buffer.from(enlarged.split(",")[1], "base64"),
    );
    await page
      .getByRole("checkbox", { name: "Reduced motion", exact: true })
      .check();
    await expect.poll(async () => (await metrics()).reduced).toBe(true);
    await page
      .getByRole("checkbox", { name: "Reduced motion", exact: true })
      .uncheck();
    await page.keyboard.press("Escape");
    // Canvas failure substitution is confined to this isolated page; SVG must remain usable.
    await page.addInitScript(() =>
      Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
        value: () => null,
      }),
    );
    await page.reload();
    await expect(page.locator(".olive-core-fallback")).toBeVisible();
    await expect(page.locator(".olive-core-canvas")).not.toBeVisible();
    await page.screenshot({
      path: path.join(evidence, "fixture-canvas-unavailable.png"),
    });
    await page
      .getByRole("button", { name: "Enter OLIVE", exact: true })
      .click();
    await expect(
      page.getByRole("textbox", { name: "Ask OLIVE anything", exact: true }),
    ).toBeVisible();
    await writeFile(
      path.join(evidence, "result.json"),
      JSON.stringify(
        {
          classification:
            "real Electron renderer; actual Python unittest validation in synthetic workspace; no local model required",
          angles,
          idle,
          active,
          hidden,
          recording,
          variants,
          fallbackUsable: true,
        },
        null,
        2,
      ),
    );
  } finally {
    await app.close();
  }
});
