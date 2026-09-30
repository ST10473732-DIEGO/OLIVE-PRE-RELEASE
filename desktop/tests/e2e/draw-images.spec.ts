import { test, expect, type ElectronApplication, type Page } from "@playwright/test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { openSpace } from "./shell";
import {
  INK, canvas, decode, drawLine, exportAs, launch, makeImageFixtures, near, saved, screenPixel, stubOpen,
} from "./draw-helpers";

// OLIVE Draw image import in the real app: synthetic PNG/JPEG fixtures only.
// The drawing keeps its own OLIVE copy, so deleting the source file changes nothing.

async function importFile(page: Page, app: ElectronApplication, file: string) {
  await stubOpen(app, file);
  await page.getByRole("button", { name: "Import image", exact: true }).click();
  // Wait for the outcome of THIS import (the notice names the file, or refuses).
  const notice = page.locator(".draw-notice");
  await expect(notice).toContainText(new RegExp(`Imported ${path.basename(file).replace(/[.]/g, "\\.")}|Could not import image`), { timeout: 30000 });
  return (await notice.textContent()) || "";
}

async function newDrawing(page: Page, preset?: RegExp) {
  const cards = page.getByRole("list", { name: "Drawings" }).getByRole("listitem");
  const before = await cards.count();
  if (preset) {
    await page.getByRole("button", { name: "New drawing with another canvas size", exact: true }).click();
    await page.getByRole("menuitem", { name: preset }).click();
  } else {
    await page.getByRole("button", { name: "New drawing", exact: true }).last().click();
  }
  // The new drawing is open (not the previous one still on screen).
  await expect(cards).toHaveCount(before + 1);
  await expect(page.getByRole("textbox", { name: "Drawing title" })).toHaveValue("Untitled drawing");
  await expect(canvas(page)).toHaveAttribute("aria-label", /, 0 edits,/);
}

test("OLIVE Draw images: import, draw over, restart without the source, export, duplicate, backup and restore", async () => {
  test.skip(process.platform !== "linux", "Linux desktop acceptance");
  test.setTimeout(600000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-draw-images-"));
  const fixtures = await mkdtemp(path.join(tmpdir(), "olive-draw-fixtures-"));
  const out = await mkdtemp(path.join(tmpdir(), "olive-draw-images-out-"));
  makeImageFixtures(fixtures);
  let { app, page } = await launch(profile);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  try {
    await openSpace(page, "OLIVE Draw");
    await newDrawing(page);
    await page.getByRole("textbox", { name: "Drawing title" }).fill("Image acceptance");
    await page.getByRole("textbox", { name: "Drawing title" }).press("Enter");

    // PNG with transparency: 400 x 300 at natural size, centred at (760, 390).
    expect(await importFile(page, app, path.join(fixtures, "transparent.png"))).toContain("Imported transparent.png (400 × 300)");
    await saved(page);
    expect(near(await screenPixel(page, { x: 800, y: 420 }), INK.red, 10)).toBe(true);
    expect(near(await screenPixel(page, { x: 1060, y: 420 }), INK.white, 3)).toBe(true);    // Transparent part: page shows.
    expect(near(await screenPixel(page, { x: 1060, y: 540 }), INK.green, 10)).toBe(true);
    // Draw over it, then erase through image and ink (the image is part of the drawing layer).
    await drawLine(page, { x: 700, y: 640 }, { x: 1200, y: 640 });
    await page.keyboard.press("e");
    await page.getByRole("spinbutton", { name: "Pen size in pixels" }).fill("30");
    await drawLine(page, { x: 850, y: 380 }, { x: 850, y: 700 });
    await page.keyboard.press("p");
    await saved(page);
    const samples = [{ x: 800, y: 420 }, { x: 1060, y: 420 }, { x: 1060, y: 540 }, { x: 900, y: 640 }, { x: 850, y: 420 }, { x: 850, y: 640 }];
    const first = path.join(out, "before.png");
    await exportAs(page, app, first, /^Export PNG/);
    const before = await decode(page, first, "image/png", samples);
    expect([before.width, before.height]).toEqual([1920, 1080]);
    const [red, clear, green, ink, erasedImage, erasedInk] = before.samples;
    expect(near(red, INK.red, 0)).toBe(true);           // 1:1 placement: exact colours.
    expect(near(clear, INK.white, 0)).toBe(true);
    expect(near(green, INK.green, 0)).toBe(true);
    expect(near(ink, INK.black, 0)).toBe(true);
    expect(near(erasedImage, INK.white, 0)).toBe(true);
    expect(near(erasedInk, INK.white, 0)).toBe(true);

    // The source file is gone; OLIVE's own copy is authoritative.
    await rm(path.join(fixtures, "transparent.png"));
    await app.close();
    ({ app, page } = await launch(profile));
    page.on("pageerror", (e) => errors.push(e.message));
    await openSpace(page, "OLIVE Draw");
    await expect(page.getByRole("textbox", { name: "Drawing title" })).toHaveValue("Image acceptance");
    await expect.poll(async () => near(await screenPixel(page, { x: 800, y: 420 }), INK.red, 10), { timeout: 10000 }).toBe(true);
    const after = path.join(out, "after.png");
    await exportAs(page, app, after, /^Export PNG/);
    expect((await decode(page, after, "image/png", samples)).hash).toBe(before.hash);

    // JPEG keeps the image; transparency becomes white, never black.
    const jpg = path.join(out, "image.jpg");
    await exportAs(page, app, jpg, /^Export JPEG/);
    const jpeg = await decode(page, jpg, "image/jpeg", samples);
    expect(near(jpeg.samples[0], INK.red, 24)).toBe(true);
    expect(near(jpeg.samples[1], INK.white, 8)).toBe(true);
    // Transparent background: PNG keeps the image's own transparency.
    await page.getByRole("button", { name: "More drawing actions", exact: true }).click();
    await page.getByRole("menuitem", { name: /^Transparent background/ }).click();
    await saved(page);
    const alpha = path.join(out, "alpha.png");
    await exportAs(page, app, alpha, /^Export PNG/);
    const transparent = await decode(page, alpha, "image/png", [{ x: 1060, y: 420 }, { x: 800, y: 420 }]);
    expect(transparent.samples[0][3]).toBe(0);
    expect(near(transparent.samples[1], INK.red, 0)).toBe(true);
    await canvas(page).focus();
    await page.keyboard.press("Control+z");

    // Duplicate: the copy shows the image (same asset, no new bytes).
    await page.getByRole("button", { name: "More drawing actions", exact: true }).click();
    await page.getByRole("menuitem", { name: /^Duplicate drawing/ }).click();
    await expect(page.getByRole("textbox", { name: "Drawing title" })).toHaveValue("Image acceptance (copy)");
    await expect.poll(async () => near(await screenPixel(page, { x: 800, y: 420 }), INK.red, 10), { timeout: 10000 }).toBe(true);

    // EXIF orientation 6: stored upright (the blue band ends up on top), metadata removed.
    await newDrawing(page, /^800 × 600/);
    expect(await importFile(page, app, path.join(fixtures, "rotated.jpg"))).toContain("(200 × 300)");
    await saved(page);
    await expect.poll(async () => near(await screenPixel(page, { x: 400, y: 170 }), [20, 20, 220, 255], 40), { timeout: 10000 }).toBe(true);
    expect(near(await screenPixel(page, { x: 400, y: 400 }), [220, 40, 40, 255], 40)).toBe(true);
    const stored = await page.evaluate(async () => {
      const call = window.olive.call as (m: string, a: unknown) => Promise<Record<string, unknown>>;
      const list = await call("draw.list", {}) as { drawings: { drawing_id: string }[] };
      const opened = await call("draw.open", { drawing_id: list.drawings[0].drawing_id }) as { records: { kind: string; body: { type?: string; asset_id?: string } }[] };
      const image = opened.records.find((r) => r.kind === "op" && r.body.type === "image")!;
      const chunk = await call("draw.asset_chunk", { asset_id: image.body.asset_id, index: 0 }) as { data: string; mime: string; width: number; height: number };
      const bytes = atob(chunk.data);
      return { mime: chunk.mime, width: chunk.width, height: chunk.height, exif: bytes.includes("Exif\u0000\u0000"), gps: bytes.includes("GPS") };
    });
    expect(stored).toEqual({ mime: "image/jpeg", width: 200, height: 300, exif: false, gps: false });

    // Larger than the canvas: scaled down (aspect kept) to fit with margins.
    await newDrawing(page);
    expect(await importFile(page, app, path.join(fixtures, "large.jpg"))).toContain("(1458 × 972)");
    await saved(page);
    await expect.poll(async () => near(await screenPixel(page, { x: 300, y: 100 }), INK.blue, 12), { timeout: 10000 }).toBe(true);
    expect(near(await screenPixel(page, { x: 1700, y: 540 }), INK.white, 3)).toBe(true);
    // Content decides the type; absurd or fake images are refused before decoding.
    expect(await importFile(page, app, path.join(fixtures, "really-a-png.jpg"))).toContain("Imported really-a-png.jpg");
    expect(await importFile(page, app, path.join(fixtures, "absurd.png"))).toContain("dimensions are too large");
    expect(await importFile(page, app, path.join(fixtures, "not-an-image.png"))).toContain("only PNG and JPEG");

    // Backup and restore bring back the drawing and its imported image.
    const archive = path.join(out, "backup.zip");
    await app.evaluate(({ dialog }, file) => {
      dialog.showSaveDialog = (async () => ({ canceled: false, filePath: file })) as typeof dialog.showSaveDialog;
    }, archive);
    await page.evaluate(async () => { await window.olive.fileAction({ action: "backup" }); });
    const original = await page.evaluate(async () => {
      const call = window.olive.call as (m: string, a: unknown) => Promise<Record<string, unknown>>;
      const list = await call("draw.list", {}) as { drawings: { drawing_id: string; title: string }[] };
      const target = list.drawings.find((d) => d.title === "Image acceptance")!;
      await call("draw.trash", { drawing_id: target.drawing_id });
      await call("draw.purge", { drawing_id: target.drawing_id, confirmed: true });
      return target.drawing_id;
    });
    await app.evaluate(({ dialog }, file) => {
      dialog.showOpenDialog = (async () => ({ canceled: false, filePaths: [file] })) as typeof dialog.showOpenDialog;
      dialog.showMessageBox = (async () => ({ response: 1, checkboxChecked: false })) as typeof dialog.showMessageBox;
    }, archive);
    const restored = await page.evaluate(async () => String(await window.olive.fileAction({ action: "restore" })));
    expect(restored).toContain("Restore complete");
    await app.close();
    ({ app, page } = await launch(profile));
    await openSpace(page, "OLIVE Draw");
    await page.getByRole("list", { name: "Drawings" }).getByText("Image acceptance", { exact: true }).click();
    await expect.poll(async () => near(await screenPixel(page, { x: 800, y: 420 }), INK.red, 10), { timeout: 10000 }).toBe(true);
    expect(await page.evaluate(async (id) => ((await window.olive.call("draw.get" as never, { drawing_id: id } as never)) as { title: string }).title, original)).toBe("Image acceptance");
    expect(errors).toEqual([]);
  } finally {
    await app.close().catch(() => undefined);
    await rm(profile, { recursive: true, force: true });
    await rm(fixtures, { recursive: true, force: true });
    await rm(out, { recursive: true, force: true });
  }
});

test("OLIVE Draw images: the asset store dedupes identical imports", async () => {
  test.skip(process.platform !== "linux", "Linux desktop acceptance");
  test.setTimeout(300000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-draw-dedupe-"));
  const fixtures = await mkdtemp(path.join(tmpdir(), "olive-draw-fixtures-"));
  makeImageFixtures(fixtures);
  const { app, page } = await launch(profile);
  try {
    await openSpace(page, "OLIVE Draw");
    await newDrawing(page);
    await importFile(page, app, path.join(fixtures, "transparent.png"));
    await importFile(page, app, path.join(fixtures, "transparent.png"));
    await saved(page);
    const ids = await page.evaluate(async () => {
      const call = window.olive.call as (m: string, a: unknown) => Promise<Record<string, unknown>>;
      const list = await call("draw.list", {}) as { drawings: { drawing_id: string }[] };
      const opened = await call("draw.open", { drawing_id: list.drawings[0].drawing_id }) as { records: { kind: string; body: { type?: string; asset_id?: string } }[] };
      return opened.records.filter((r) => r.kind === "op" && r.body.type === "image").map((r) => r.body.asset_id);
    });
    expect(ids).toHaveLength(2);
    expect(ids[0]).toBe(ids[1]);     // Same bytes, same content address: stored once.
    const data = await readFile(path.join(profile, "drawings.sqlite3"));
    expect(data.length).toBeGreaterThan(0);
  } finally {
    await app.close().catch(() => undefined);
    await rm(profile, { recursive: true, force: true });
    await rm(fixtures, { recursive: true, force: true });
  }
});
