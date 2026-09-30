import { expect, _electron as electron, type ElectronApplication, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";

// OLIVE DrawNote in the real Electron app with an isolated profile and no
// model (Ollama unreachable). Strokes are real pointer input; exports are read
// back and checked pixel by pixel at document coordinates.
export const root = path.resolve("..");
export type Point = { x: number; y: number };

export async function launch(profile: string, args: string[] = [], extra: Record<string, string> = {}): Promise<{ app: ElectronApplication; page: Page }> {
  const env = { ...process.env, OLIVE_DATA_DIR: profile, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1", OLIVE_START_OLLAMA: "0", ...extra };
  delete (env as Record<string, string | undefined>).ELECTRON_RUN_AS_NODE;
  const app = await electron.launch({ executablePath: path.join(root, "run_olive.sh"), args, chromiumSandbox: true, env, timeout: 120000 });
  const page = await app.firstWindow();
  await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
  return { app, page };
}

export const canvas = (page: Page) => page.locator("canvas.draw-canvas");

/** Viewport CSS position of a document point, from the canvas's own view. */
export async function toScreen(page: Page, p: Point): Promise<Point> {
  return canvas(page).evaluate((el, q) => {
    const r = el.getBoundingClientRect(), d = (el as HTMLCanvasElement).dataset;
    const zoom = Number(d.zoom), ox = Number(d.ox), oy = Number(d.oy), dpr = Number(d.dpr);
    return { x: r.left + (q.x * zoom * dpr + ox) / dpr, y: r.top + (q.y * zoom * dpr + oy) / dpr };
  }, p);
}

export async function drawLine(page: Page, from: Point, to: Point, steps = 24) {
  const a = await toScreen(page, from), b = await toScreen(page, to);
  await page.mouse.move(a.x, a.y);
  await page.mouse.down();
  await page.mouse.move(b.x, b.y, { steps });
  await page.mouse.up();
}

/** RGBA of the on-screen canvas at a document point (pointer moved away first). */
export async function screenPixel(page: Page, p: Point): Promise<number[]> {
  await page.mouse.move(5, 5);
  await page.waitForTimeout(80);
  return canvas(page).evaluate((el, q) => {
    const c = el as HTMLCanvasElement, d = c.dataset;
    const k = Number(d.zoom) * Number(d.dpr);
    const x = Math.round(q.x * k + Number(d.ox)), y = Math.round(q.y * k + Number(d.oy));
    return Array.from(c.getContext("2d")!.getImageData(x, y, 1, 1).data);
  }, p);
}

export async function saved(page: Page) {
  await expect(page.locator(".draw-save")).toHaveText("Saved locally", { timeout: 15000 });
}

/** Decode an exported file inside Chromium and sample document pixels. */
export async function decode(page: Page, file: string, mime: string, points: Point[]) {
  const data = (await readFile(file)).toString("base64");
  return page.evaluate(async ({ data, mime, points }) => {
    const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
    const bitmap = await createImageBitmap(new Blob([bytes], { type: mime }), { premultiplyAlpha: "none", colorSpaceConversion: "none" });
    const surface = new OffscreenCanvas(bitmap.width, bitmap.height);
    const ctx = surface.getContext("2d")!;
    ctx.drawImage(bitmap, 0, 0);
    const all = ctx.getImageData(0, 0, bitmap.width, bitmap.height).data;
    let inked = 0, hash = 0;
    for (let i = 0; i < all.length; i += 4) {
      if (all[i + 3] > 0 && (all[i] < 240 || all[i + 1] < 240 || all[i + 2] < 240)) inked += 1;
      hash = (hash * 31 + all[i] + all[i + 1] * 3 + all[i + 2] * 7 + all[i + 3] * 11) >>> 0;
    }
    return {
      width: bitmap.width, height: bitmap.height, inked, hash,
      samples: points.map((p) => Array.from(ctx.getImageData(p.x, p.y, 1, 1).data)),
    };
  }, { data, mime, points });
}

export async function stubSave(app: ElectronApplication, file: string) {
  await app.evaluate(({ dialog }, target) => {
    const g = globalThis as unknown as { lastSave?: unknown };
    dialog.showSaveDialog = (async (...args: unknown[]) => {
      g.lastSave = args[args.length - 1];
      return { canceled: false, filePath: target };
    }) as typeof dialog.showSaveDialog;
  }, file);
}

export async function exportAs(page: Page, app: ElectronApplication, file: string, item: RegExp) {
  await stubSave(app, file);
  await page.getByRole("button", { name: "Export", exact: true }).click();
  await page.getByRole("menuitem", { name: item }).click();
  await expect(page.locator(".draw-notice")).toContainText("Exported", { timeout: 30000 });
  return app.evaluate(() => (globalThis as unknown as { lastSave: { defaultPath: string } }).lastSave);
}

export const near = (actual: number[], expected: number[], tolerance: number) =>
  actual.slice(0, expected.length).every((v, i) => Math.abs(v - expected[i]) <= tolerance);

export const INK = { black: [0, 0, 0, 255], red: [229, 57, 53, 255], blue: [30, 99, 233, 255], green: [67, 160, 71, 255], white: [255, 255, 255, 255] };


/** The next system open dialog returns this file (the person's choice). */
export async function stubOpen(app: ElectronApplication, file: string) {
  await app.evaluate(({ dialog }, target) => {
    dialog.showOpenDialog = (async () => ({ canceled: false, filePaths: [target] })) as typeof dialog.showOpenDialog;
  }, file);
}

/** Synthetic fixtures made by Pillow at test time (see tests/fixtures/draw_images.py). */
export function makeImageFixtures(directory: string) {
  execFileSync(path.join(root, ".venv/bin/python"), [path.join(root, "tests/fixtures/draw_images.py"), directory]);
}
