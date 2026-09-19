import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { goHome, mainNav, openSpace } from "./shell";

// The Core hand-off from Welcome lands in the workbench bar; the bar must not
// scroll, spill or shift while the projection travels, at any window size.
for (const reduced of [false, true])
  test(`Core handoff keeps the navigation pane stable, reduced motion ${reduced}`, async () => {
    const profile = await mkdtemp(path.join(tmpdir(), "olive-m2-core-"));
    const app = await electron.launch({
      args: [path.resolve(".")],
      env: { ...process.env, OLIVE_DATA_DIR: profile },
    });
    try {
      const page = await app.firstWindow();
      for (const [width, height] of [
        [1440, 920],
        [1366, 768],
        [640, 480],
      ]) {
        await app.evaluate(
          ({ BrowserWindow }, size) =>
            BrowserWindow.getAllWindows()[0].setSize(size[0], size[1]),
          [width, height],
        );
        await page.evaluate((r) => {
          localStorage.setItem("reducedMotion", String(r));
          localStorage.removeItem("skipWelcome");
          localStorage.removeItem("workbenchItems");
        }, reduced);
        await page.reload();
        await expect(
          page.getByRole("button", { name: "Enter OLIVE", exact: true }),
        ).toBeVisible();
        const measurement = page.evaluate(
          () =>
            new Promise<{ overflow: number; heights: number[] }>((resolve) => {
              let overflow = 0;
              const heights = new Set<number>();
              const end = performance.now() + 1200;
              function check() {
                const pane = document.querySelector(".navigation");
                if (pane) {
                  // The pane scrolls vertically by design; it must never
                  // scroll horizontally or change width while the Core lands.
                  overflow = Math.max(overflow, pane.scrollWidth - pane.clientWidth);
                  heights.add(Math.round(pane.getBoundingClientRect().width));
                }
                if (performance.now() < end) requestAnimationFrame(check);
                else resolve({ overflow, heights: [...heights] });
              }
              requestAnimationFrame(check);
              (
                document.querySelector(
                  ".welcome button.primary",
                ) as HTMLButtonElement | null
              )?.click();
            }),
        );
        // Keyboard entry also works regardless of how the Welcome button is styled.
        await page.keyboard.press("Enter");
        const measured = await measurement;
        expect(measured.overflow).toBeLessThanOrEqual(1);
        expect(measured.heights.length).toBeLessThanOrEqual(1);
        // The Core lands inside the bar's identity control, not beside it.
        const anchor = await page.locator(".core-anchor").boundingBox();
        const core = await page.locator(".core-transit-stage .core").boundingBox();
        expect(anchor).not.toBeNull();
        expect(core).not.toBeNull();
        expect(Math.abs(core!.x - anchor!.x)).toBeLessThanOrEqual(2);
        expect(Math.abs(core!.y - anchor!.y)).toBeLessThanOrEqual(2);
        // Navigation is a stable labelled pane, not a growing tab row.
        await openSpace(page, "Chat");
        await expect(page.locator(".messages")).toBeVisible();
        await goHome(page);
        await openSpace(page, "Mail");
        await goHome(page);
        // Opening features never adds rows: one row per feature, always.
        if (await mainNav(page).isVisible()) {
          const rows = await mainNav(page).getByRole("button").count();
          await openSpace(page, "Calendar");
          await goHome(page);
          expect(await mainNav(page).getByRole("button").count()).toBe(rows);
          await expect(
            mainNav(page).getByRole("button", { name: "Home", exact: true }),
          ).toHaveAttribute("aria-current", "page");
        }
        if (await mainNav(page).isVisible())
          expect(
            await page
              .locator(".navigation")
              .evaluate((el) => el.scrollWidth - el.clientWidth),
          ).toBeLessThanOrEqual(1);
      }
    } finally {
      await app.close();
    }
  });
