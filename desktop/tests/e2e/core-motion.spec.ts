import { test, expect, _electron as electron } from "@playwright/test";
import { mkdtemp } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";

test("the Welcome mark draws in with motion allowed, holds still when reduced, and offers no playback controls", async () => {
  const profile = await mkdtemp(path.join(tmpdir(), "olive-core-motion-"));
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: { ...process.env, OLIVE_DATA_DIR: profile, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1" },
  });
  try {
    const page = await app.firstWindow();
    const names = () =>
      page.locator(".welcome-core .core").evaluate((el) =>
        el.getAnimations({ subtree: true }).map((a) => (a as CSSAnimation).animationName),
      );
    await expect(page.locator(".welcome-core .core-logo")).toBeVisible();
    await expect.poll(names).toContain("grove-olive-grow");
    await expect(page.getByRole("button", { name: /(?:Play|Pause) Core animation/ })).toHaveCount(0);
    // The system preference removes the motion but never the mark.
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.reload();
    await expect(page.locator(".welcome-core .core-logo")).toBeVisible();
    await expect.poll(names).toEqual([]);
    await page.emulateMedia({ reducedMotion: "no-preference" });
    // OLIVE's own Reduce Motion setting does the same, and disables the Core option.
    await page.evaluate(() => localStorage.setItem("reducedMotion", "true"));
    await page.reload();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await page.getByRole("button", { name: "OLIVE activity", exact: true }).click();
    await expect(page.getByLabel("Core animation", { exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: /(?:Play|Pause) Core animation/ })).toHaveCount(0);
  } finally {
    await app.close();
  }
});
