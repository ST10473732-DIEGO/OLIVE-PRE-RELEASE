import { test, expect, _electron as electron } from "@playwright/test";
import { mkdtemp } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import type { CoreMetrics } from "../../src/components/olive-core/renderer";

test("Welcome always spins without playback controls while compact motion keeps its preferences", async () => {
  const profile = await mkdtemp(path.join(tmpdir(), "olive-core-motion-"));
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
    await page.emulateMedia({ reducedMotion: "reduce" });
    const stats = () =>
      page
        .locator(".olive-core-canvas")
        .first()
        .evaluate((el) => ({
          ...(el as HTMLCanvasElement & { oliveCoreMetrics: CoreMetrics })
            .oliveCoreMetrics,
        }));
    await expect(
      page.getByRole("button", { name: /(?:Play|Pause) Core animation/ }),
    ).toHaveCount(0);
    await expect.poll(async () => (await stats()).running).toBe(true);
    const angle = (await stats()).angle;
    await expect
      .poll(async () => (await stats()).angle)
      .toBeGreaterThan(angle + 0.1);
    expect(
      await page.evaluate(
        () => matchMedia("(prefers-reduced-motion: reduce)").matches,
      ),
    ).toBe(true);
    await page.evaluate(() => {
      localStorage.setItem("coreMotion", "pause");
      localStorage.setItem("reducedMotion", "true");
    });
    await page.reload();
    await expect.poll(async () => (await stats()).running).toBe(true);
    await expect(
      page.getByRole("button", { name: /(?:Play|Pause) Core animation/ }),
    ).toHaveCount(0);
    await page
      .getByRole("button", { name: "Enter OLIVE", exact: true })
      .click();
    await page
      .getByRole("button", { name: "OLIVE activity", exact: true })
      .click();
    await expect.poll(async () => (await stats()).reduced).toBe(true);
    await expect(
      page.getByLabel("Core animation", { exact: true }),
    ).toBeDisabled();
  } finally {
    await app.close();
  }
});
