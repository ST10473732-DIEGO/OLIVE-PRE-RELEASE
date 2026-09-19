import type { ElectronApplication, Page } from "@playwright/test";
import { writeFile } from "node:fs/promises";

// Capture the actual app compositor after layout/paint, including Chromium zoom.
// Playwright's screenshot viewport can otherwise crop an enlarged Electron UI.
export async function captureMail(
  page: Page,
  app: ElectronApplication,
  file: string,
) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(
      document
        .getAnimations()
        .filter((a) => Number.isFinite(a.effect?.getComputedTiming().endTime))
        .map((a) => a.finished.catch(() => undefined)),
    );
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
  });
  const png = await app.evaluate(async ({ BrowserWindow }) =>
    (await BrowserWindow.getAllWindows()[0].capturePage())
      .toPNG()
      .toString("base64"),
  );
  await writeFile(file, Buffer.from(png, "base64"));
}
