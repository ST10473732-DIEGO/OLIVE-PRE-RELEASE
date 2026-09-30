import { test, expect } from "@playwright/test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { openSpace } from "./shell";
import { INK, canvas, decode, drawLine, exportAs, launch, near, saved, screenPixel, toScreen } from "./draw-helpers";

test("OLIVE DrawNote: Notes intact, draw, erase, undo/redo, zoom, pan, restart, export PNG/JPEG", async () => {
  test.skip(process.platform !== "linux", "Linux desktop acceptance");
  test.setTimeout(600000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-drawnote-e2e-"));
  const out = await mkdtemp(path.join(tmpdir(), "olive-drawnote-export-"));
  let { app, page } = await launch(profile);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  try {
    // 1–2. The navigation says OLIVE DrawNote; it opens on Notes, which still works.
    const nav = page.getByRole("navigation", { name: "Main navigation" });
    await expect(nav.getByRole("button", { name: "OLIVE DrawNote", exact: true })).toBeVisible();
    await expect(nav.getByRole("button", { name: "OLIVE Notes", exact: true })).toHaveCount(0);
    await openSpace(page, "OLIVE DrawNote");
    await expect(page.locator(".shell")).toHaveAttribute("data-route", "notes");
    const tabs = page.getByRole("tablist", { name: "OLIVE DrawNote views" });
    await expect(tabs.getByRole("tab", { name: "Notes", exact: true })).toHaveAttribute("aria-selected", "true");
    await page.getByRole("button", { name: "New note", exact: true }).first().click();
    const editor = page.locator("textarea.notes-textarea");
    await editor.pressSequentially("DrawNote regression line");
    await expect(page.getByRole("status").filter({ hasText: "Saved locally" }).first()).toBeVisible();

    // 3–4. Draw: a new 1920 × 1080 drawing.
    await tabs.getByRole("tab", { name: "Draw", exact: true }).click();
    await expect(page.locator(".shell")).toHaveAttribute("data-route", "draw");
    await expect(page.getByRole("heading", { name: "No drawings yet" })).toBeVisible();
    await page.getByRole("button", { name: "New drawing", exact: true }).last().click();
    await expect(canvas(page)).toBeVisible();
    await expect(page.locator(".draw-statusbar")).toContainText("1920 × 1080 px");
    await page.getByRole("textbox", { name: "Drawing title" }).fill("DrawNote Acceptance");
    await page.getByRole("textbox", { name: "Drawing title" }).press("Enter");
    await expect(page.getByRole("list", { name: "Drawings" }).getByText("DrawNote Acceptance")).toBeVisible();
    expect(await canvas(page).getAttribute("aria-label")).toContain("1920 by 1080 pixels");

    // 5–7. Black line, red line (swatch), a large blue stroke (size 48).
    await drawLine(page, { x: 200, y: 200 }, { x: 900, y: 200 });
    await page.getByRole("button", { name: "Red", exact: true }).click();
    await drawLine(page, { x: 200, y: 400 }, { x: 900, y: 400 });
    await page.getByRole("button", { name: "Blue", exact: true }).click();
    await page.getByRole("spinbutton", { name: "Pen size in pixels" }).fill("48");
    await drawLine(page, { x: 300, y: 700 }, { x: 1500, y: 700 });
    await saved(page);
    expect(near(await screenPixel(page, { x: 550, y: 200 }), INK.black, 8)).toBe(true);
    expect(near(await screenPixel(page, { x: 550, y: 400 }), INK.red, 8)).toBe(true);
    expect(near(await screenPixel(page, { x: 550, y: 718 }), INK.blue, 8)).toBe(true);   // Inside the 48 px stroke.

    // 8. Erase a vertical band through all three.
    await page.keyboard.press("e");
    await expect(page.getByRole("button", { name: "Eraser", exact: true })).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("spinbutton", { name: "Pen size in pixels" }).fill("60");
    await canvas(page).focus();
    await drawLine(page, { x: 550, y: 100 }, { x: 550, y: 800 });
    await saved(page);
    for (const y of [200, 400, 700]) expect(near(await screenPixel(page, { x: 550, y }), INK.white, 2)).toBe(true);
    expect(near(await screenPixel(page, { x: 300, y: 200 }), INK.black, 8)).toBe(true);

    // 9–10. Undo restores the erased ink exactly; Redo erases it again.
    await canvas(page).focus();
    await page.keyboard.press("Control+z");
    expect(near(await screenPixel(page, { x: 550, y: 200 }), INK.black, 8)).toBe(true);
    await page.keyboard.press("Control+Shift+z");
    expect(near(await screenPixel(page, { x: 550, y: 200 }), INK.white, 2)).toBe(true);
    await saved(page);

    // 11. Zoom to 200% with the toolbar (100% then three steps). Electron's
    // own page zoom must not change.
    const pageZoom = () => app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.getZoomFactor());
    const zoomBefore = await pageZoom();
    await page.getByRole("button", { name: /^Zoom \d+%/ }).click();
    await canvas(page).focus();
    for (let i = 0; i < 3; i++) await page.keyboard.press("Control+=");
    await expect(page.getByRole("button", { name: /^Zoom 200%/ })).toBeVisible();
    expect(await pageZoom()).toBe(zoomBefore);
    expect(Number(await canvas(page).getAttribute("data-zoom"))).toBe(2);

    // 12. Pan with Space + drag so (1400, 300) sits near the centre.
    const box = (await canvas(page).boundingBox())!;
    const centre = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    for (let round = 0; round < 6; round++) {
      const at = await toScreen(page, { x: 1400, y: 300 });
      const dx = Math.max(-250, Math.min(250, centre.x - at.x)), dy = Math.max(-250, Math.min(250, centre.y - at.y));
      if (Math.abs(dx) < 2 && Math.abs(dy) < 2) break;
      await page.mouse.move(centre.x, centre.y);
      await page.keyboard.down("Space");
      await expect(canvas(page)).toHaveAttribute("data-cursor", "pan");
      await page.mouse.down();
      await page.mouse.move(centre.x + dx, centre.y + dy, { steps: 6 });
      await page.mouse.up();
      await page.keyboard.up("Space");
    }
    const panned = await toScreen(page, { x: 1400, y: 300 });
    expect(Math.abs(panned.x - centre.x)).toBeLessThan(6);
    // Panning drew nothing.
    expect(near(await screenPixel(page, { x: 1400, y: 300 }), INK.white, 2)).toBe(true);

    // 13. Draw while zoomed and panned: a green line at document y = 300.
    await page.keyboard.press("p");
    await page.getByRole("button", { name: "Green", exact: true }).click();
    await page.getByRole("spinbutton", { name: "Pen size in pixels" }).fill("16");
    await drawLine(page, { x: 1300, y: 300 }, { x: 1500, y: 300 });
    await saved(page);
    expect(near(await screenPixel(page, { x: 1400, y: 300 }), INK.green, 8)).toBe(true);

    // Ctrl + wheel zooms around the pointer: the document point under it stays.
    const anchor = await toScreen(page, { x: 1400, y: 300 });
    await page.mouse.move(anchor.x, anchor.y);
    await page.keyboard.down("Control");
    await page.mouse.wheel(0, -120);
    await page.keyboard.up("Control");
    await expect.poll(async () => Number(await canvas(page).getAttribute("data-zoom"))).toBeGreaterThan(2);
    const after = await toScreen(page, { x: 1400, y: 300 });
    expect(Math.abs(after.x - anchor.x)).toBeLessThan(1.5);
    expect(Math.abs(after.y - anchor.y)).toBeLessThan(1.5);
    expect(await pageZoom()).toBe(zoomBefore);

    // 14. Fit.
    await canvas(page).focus();
    await page.keyboard.press("Control+0");
    // The view is presented on the next animation frame.
    await expect.poll(async () => Number(await canvas(page).getAttribute("data-zoom"))).toBeLessThan(1);

    // Export before restart, for the determinism check.
    const before = path.join(out, "before.png");
    const dialogOptions = await exportAs(page, app, before, /^Export PNG/);
    expect(path.basename(dialogOptions.defaultPath)).toBe("DrawNote Acceptance.png");
    const samplesAt = [{ x: 550, y: 200 }, { x: 300, y: 200 }, { x: 300, y: 400 }, { x: 800, y: 718 }, { x: 1400, y: 300 }, { x: 1400, y: 330 }, { x: 50, y: 1000 }];
    const first = await decode(page, before, "image/png", samplesAt);

    // 15–16. Restart: the drawing reopens, still editable with its history.
    await app.close();
    ({ app, page } = await launch(profile));
    page.on("pageerror", (e) => errors.push(e.message));
    await openSpace(page, "OLIVE DrawNote");
    // DrawNote remembers the last section used on this device.
    await expect(page.locator(".shell")).toHaveAttribute("data-route", "draw");
    await expect(canvas(page)).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Drawing title" })).toHaveValue("DrawNote Acceptance");
    expect(near(await screenPixel(page, { x: 1400, y: 300 }), INK.green, 8)).toBe(true);
    await canvas(page).focus();
    await page.keyboard.press("Control+z");   // Undo history survived the restart.
    expect(near(await screenPixel(page, { x: 1400, y: 300 }), INK.white, 2)).toBe(true);
    await page.keyboard.press("Control+y");
    expect(near(await screenPixel(page, { x: 1400, y: 300 }), INK.green, 8)).toBe(true);
    await saved(page);

    // 17–18. PNG: signature, exact document size, the expected ink.
    const png = path.join(out, "drawing.png");
    await exportAs(page, app, png, /^Export PNG/);
    const pngBytes = await readFile(png);
    expect([...pngBytes.subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
    const decoded = await decode(page, png, "image/png", samplesAt);
    expect([decoded.width, decoded.height]).toEqual([1920, 1080]);
    expect(decoded.inked).toBeGreaterThan(10000);
    const [erased, black, red, blue, green, belowGreen, empty] = decoded.samples;
    expect(near(erased, INK.white, 0)).toBe(true);
    expect(near(black, INK.black, 0)).toBe(true);
    expect(near(red, INK.red, 0)).toBe(true);
    expect(near(blue, INK.blue, 0)).toBe(true);
    expect(near(green, INK.green, 0)).toBe(true);
    expect(near(belowGreen, INK.white, 0)).toBe(true);   // 16 px pen: no offset or scale error.
    expect(near(empty, INK.white, 0)).toBe(true);
    // Reloaded operations render the same pixels as before the restart.
    expect(decoded.hash).toBe(first.hash);

    // 19–20. JPEG: signature, size, colours within JPEG tolerance.
    const jpg = path.join(out, "drawing.jpg");
    await exportAs(page, app, jpg, /^Export JPEG/);
    const jpgBytes = await readFile(jpg);
    expect([...jpgBytes.subarray(0, 3)]).toEqual([0xff, 0xd8, 0xff]);
    const jpeg = await decode(page, jpg, "image/jpeg", samplesAt);
    expect([jpeg.width, jpeg.height]).toEqual([1920, 1080]);
    expect(near(jpeg.samples[1], INK.black, 24)).toBe(true);
    expect(near(jpeg.samples[3], INK.blue, 24)).toBe(true);
    expect(near(jpeg.samples[6], INK.white, 6)).toBe(true);

    // Transparent background: PNG keeps alpha; JPEG composites onto white, never black.
    await page.getByRole("button", { name: "More drawing actions", exact: true }).click();
    await page.getByRole("menuitem", { name: /^Transparent background/ }).click();
    await saved(page);
    const clear = path.join(out, "transparent.png");
    await exportAs(page, app, clear, /^Export PNG/);
    const alpha = await decode(page, clear, "image/png", [{ x: 50, y: 1000 }, { x: 300, y: 200 }]);
    expect(alpha.samples[0][3]).toBe(0);
    expect(near(alpha.samples[1], INK.black, 0)).toBe(true);
    const flat = path.join(out, "transparent.jpg");
    await exportAs(page, app, flat, /^Export JPEG/);
    const white = await decode(page, flat, "image/jpeg", [{ x: 50, y: 1000 }, { x: 550, y: 200 }]);
    expect(near(white.samples[0], INK.white, 4)).toBe(true);
    expect(near(white.samples[1], INK.white, 4)).toBe(true);
    await canvas(page).focus();
    await page.keyboard.press("Control+z");   // Background change is one undo step.
    await expect(page.locator(".draw-statusbar")).toContainText("White background");

    // Clear is one undoable operation.
    await page.getByRole("button", { name: "More drawing actions", exact: true }).click();
    await page.getByRole("menuitem", { name: /^Clear canvas/ }).click();
    expect(near(await screenPixel(page, { x: 300, y: 200 }), INK.white, 2)).toBe(true);
    await canvas(page).focus();
    await page.keyboard.press("Control+z");
    expect(near(await screenPixel(page, { x: 300, y: 200 }), INK.black, 8)).toBe(true);
    await saved(page);

    // Duplicate, delete to Recently Deleted, restore.
    await page.getByRole("button", { name: "More drawing actions", exact: true }).click();
    await page.getByRole("menuitem", { name: /^Duplicate drawing/ }).click();
    await expect(page.getByRole("textbox", { name: "Drawing title" })).toHaveValue("DrawNote Acceptance (copy)");
    await page.getByRole("button", { name: "More drawing actions", exact: true }).click();
    await page.getByRole("menuitem", { name: /^Move to Recently Deleted/ }).click();
    await page.getByRole("group", { name: "Drawings view" }).getByRole("button", { name: /Recently Deleted/ }).click();
    await page.getByRole("list", { name: "Recently deleted drawings" }).getByText("DrawNote Acceptance (copy)").click();
    await page.getByRole("button", { name: "Restore", exact: true }).click();
    await page.getByRole("group", { name: "Drawings view" }).getByRole("button", { name: /^Drawings/ }).click();
    await expect(page.getByRole("list", { name: "Drawings" }).getByText("DrawNote Acceptance (copy)")).toBeVisible();

    // 21–22. Back to Notes: the note is untouched.
    await page.getByRole("tablist", { name: "OLIVE DrawNote views" }).getByRole("tab", { name: "Notes", exact: true }).click();
    await expect(page.locator(".shell")).toHaveAttribute("data-route", "notes");
    await page.getByRole("list", { name: "Notes", exact: true }).getByText("DrawNote regression line").click();
    await expect(page.locator("textarea.notes-textarea")).toHaveValue("DrawNote regression line");

    // Navigation round trip keeps Notes and Draw mounted (no reload or data loss).
    await canvas(page).evaluate((el) => { (el as unknown as { marker: number }).marker = 7; }).catch(() => undefined);
    await page.locator("textarea.notes-textarea").evaluate((el) => { (el as unknown as { marker: number }).marker = 9; });
    for (const name of ["Chat", "Studio", "OLIVE GO", "OLIVE DrawNote"]) await openSpace(page, name);
    await expect(page.locator(".shell")).toHaveAttribute("data-route", "notes");
    expect(await page.locator("textarea.notes-textarea").evaluate((el) => (el as unknown as { marker: number }).marker)).toBe(9);
    await page.getByRole("tablist", { name: "OLIVE DrawNote views" }).getByRole("tab", { name: "Draw", exact: true }).click();
    await openSpace(page, "Chat");
    await openSpace(page, "OLIVE DrawNote");
    await expect(page.locator(".shell")).toHaveAttribute("data-route", "draw");
    expect(await canvas(page).evaluate((el) => (el as unknown as { marker: number }).marker)).toBe(7);

    // Chat routing: literal requests only, handled without a model.
    const chatId = await page.evaluate(async () => ((await window.olive.call("runtime.snapshot", {})) as { chat: { id: string } }).chat.id);
    const say = (text: string) => page.evaluate(async ([id, value]) => { await window.olive.call("interaction.submit", { chat_id: id, text: value }); }, [chatId, text]);
    await openSpace(page, "Chat");
    await say("Open OLIVE Draw");
    await expect(page.locator(".shell")).toHaveAttribute("data-route", "draw");
    await say("Open OLIVE Notes");
    await expect(page.locator(".shell")).toHaveAttribute("data-route", "notes");
    await say("Open DrawNote and go to Draw");
    await expect(page.locator(".shell")).toHaveAttribute("data-route", "draw");
    await say("Open my DrawNote regression line note");
    await expect(page.locator(".shell")).toHaveAttribute("data-route", "notes");
    await expect(page.locator("textarea.notes-textarea")).toHaveValue("DrawNote regression line");

    expect(errors).toEqual([]);
  } finally {
    await app.close().catch(() => undefined);
    await rm(profile, { recursive: true, force: true });
    await rm(out, { recursive: true, force: true });
  }
});

test("OLIVE Draw: a completed stroke survives killing the app", async () => {
  test.skip(process.platform !== "linux", "Linux desktop acceptance");
  test.setTimeout(300000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-draw-crash-"));
  let { app, page } = await launch(profile);
  try {
    await openSpace(page, "OLIVE DrawNote");
    await page.getByRole("tablist", { name: "OLIVE DrawNote views" }).getByRole("tab", { name: "Draw", exact: true }).click();
    await page.getByRole("button", { name: "New drawing", exact: true }).last().click();
    await expect(canvas(page)).toBeVisible();
    await drawLine(page, { x: 100, y: 540 }, { x: 1800, y: 540 });
    await drawLine(page, { x: 960, y: 100 }, { x: 960, y: 1000 });
    await saved(page);
    // Kill Electron and its backend without any shutdown path.
    // run_olive.sh execs Electron, so this is the Electron main process; the
    // Python backend loses its pipe and exits on its own.
    process.kill(app.process().pid!, "SIGKILL");
    await new Promise((resolve) => setTimeout(resolve, 3000));
    ({ app, page } = await launch(profile));
    // The remembered section and selection are UI conveniences in renderer
    // storage and may not reach disk before a SIGKILL; the drawing itself is
    // in SQLite. Open it from the list.
    await openSpace(page, "OLIVE Draw");
    if (!(await canvas(page).isVisible())) await page.getByRole("list", { name: "Drawings" }).getByText("Untitled drawing").click();
    await expect(canvas(page)).toBeVisible();
    expect(near(await screenPixel(page, { x: 500, y: 540 }), INK.black, 8)).toBe(true);
    expect(near(await screenPixel(page, { x: 960, y: 300 }), INK.black, 8)).toBe(true);
    await expect(canvas(page)).toHaveAttribute("aria-label", /2 edits/);
  } finally {
    await app.close().catch(() => undefined);
    await rm(profile, { recursive: true, force: true });
  }
});

for (const scale of [1, 1.25, 1.5, 2]) {
  test(`OLIVE Draw at display scale ${scale}: strokes land on document coordinates and export at document size`, async () => {
    test.skip(process.platform !== "linux", "Linux desktop acceptance");
    test.setTimeout(240000);
    const profile = await mkdtemp(path.join(tmpdir(), "olive-draw-dpi-"));
    const out = await mkdtemp(path.join(tmpdir(), "olive-draw-dpi-out-"));
    const { app, page } = await launch(profile, [`--force-device-scale-factor=${scale}`]);
    try {
      expect(await page.evaluate(() => window.devicePixelRatio)).toBeCloseTo(scale, 5);
      await openSpace(page, "OLIVE DrawNote");
      await page.getByRole("tablist", { name: "OLIVE DrawNote views" }).getByRole("tab", { name: "Draw", exact: true }).click();
      await page.getByRole("button", { name: "New drawing", exact: true }).last().click();
      await expect(canvas(page)).toBeVisible();
      await page.getByRole("spinbutton", { name: "Pen size in pixels" }).fill("10");
      await drawLine(page, { x: 100, y: 100 }, { x: 700, y: 100 });
      await drawLine(page, { x: 1600, y: 200 }, { x: 1600, y: 900 });
      await saved(page);
      // The backing store is device-sized, so the page is sharp.
      const backing = await canvas(page).evaluate((el) => [(el as HTMLCanvasElement).width, el.getBoundingClientRect().width]);
      expect(Math.abs(backing[0] - backing[1] * scale)).toBeLessThanOrEqual(1);
      const file = path.join(out, "dpi.png");
      await exportAs(page, app, file, /^Export PNG/);
      const decoded = await decode(page, file, "image/png", [{ x: 400, y: 100 }, { x: 400, y: 112 }, { x: 1600, y: 550 }, { x: 1612, y: 550 }, { x: 101, y: 100 }]);
      expect([decoded.width, decoded.height]).toEqual([1920, 1080]);
      const [on, off, onV, offV] = decoded.samples;
      expect(near(on, INK.black, 0)).toBe(true);
      expect(near(off, INK.white, 0)).toBe(true);
      expect(near(onV, INK.black, 0)).toBe(true);
      expect(near(offV, INK.white, 0)).toBe(true);
    } finally {
      await app.close().catch(() => undefined);
      await rm(profile, { recursive: true, force: true });
      await rm(out, { recursive: true, force: true });
    }
  });
}

test("OLIVE Draw: 5,000-stroke drawing opens, zooms and pans", async () => {
  test.skip(process.platform !== "linux", "Linux desktop acceptance");
  test.setTimeout(600000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-draw-large-"));
  const { app, page } = await launch(profile);
  try {
    const seeded = await page.evaluate(async () => {
      const call = window.olive.call as (m: string, a: unknown) => Promise<Record<string, unknown>>;
      const drawing = await call("draw.create", { title: "Five thousand strokes" });
      let count = 0;
      const started = performance.now();
      const id = () => { const bytes = new Uint8Array(16); crypto.getRandomValues(bytes); return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join(""); };
      const colors = ["#000000", "#e53935", "#1e63e9", "#43a047"];
      for (let batch = 0; batch < 625; batch++) {
        await Promise.all(Array.from({ length: 8 }, async (_, i) => {
          const n = batch * 8 + i, points: number[] = [];
          for (let s = 0; s < 80; s++) points.push(Math.round((100 + ((n * 7.31 + s * 3.17) % 1700)) * 100) / 100, Math.round((100 + ((n * 3.7 + s * 1.9) % 880)) * 100) / 100);
          await call("draw.append", { drawing_id: drawing.drawing_id, op: { type: "stroke", id: id(), tool: "pen", color: colors[n % 4], width: 2 + (n % 6), opacity: n % 10 === 0 ? 0.5 : 1, pressure: false, points } });
          count += 1;
        }));
      }
      return { id: drawing.drawing_id as string, count, ms: Math.round(performance.now() - started) };
    });
    expect(seeded.count).toBe(5000);
    await openSpace(page, "OLIVE DrawNote");
    await page.getByRole("tablist", { name: "OLIVE DrawNote views" }).getByRole("tab", { name: "Draw", exact: true }).click();
    const opened = Date.now();
    await page.getByRole("list", { name: "Drawings" }).getByText("Five thousand strokes").click();
    await expect(canvas(page)).toHaveAttribute("data-replay-ms", /\d+/, { timeout: 60000 });
    const openMs = Date.now() - opened;
    const fitReplay = Number(await canvas(page).getAttribute("data-replay-ms"));
    await canvas(page).focus();
    await page.keyboard.press("Control+1");
    await page.waitForTimeout(400);
    const actualReplay = Number(await canvas(page).getAttribute("data-replay-ms"));
    for (let i = 0; i < 3; i++) await page.keyboard.press("Control+=");
    await page.waitForTimeout(400);
    const zoomReplay = Number(await canvas(page).getAttribute("data-replay-ms"));
    // Pan frames: time 20 Space-drag moves.
    const box = (await canvas(page).boundingBox())!;
    const c = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    await page.mouse.move(c.x, c.y);
    await page.keyboard.down("Space");
    await page.mouse.down();
    const panStart = Date.now();
    for (let i = 1; i <= 20; i++) await page.mouse.move(c.x - i * 10, c.y - i * 6);
    const panMs = Date.now() - panStart;
    await page.mouse.up();
    await page.keyboard.up("Space");
    await page.waitForTimeout(300);
    const panReplay = Number(await canvas(page).getAttribute("data-replay-ms"));
    // Frame intervals measured in the page (GPU raster included): a wheel pan
    // per animation frame, then a live stroke of 120 moves.
    const frames = await canvas(page).evaluate(async (el) => {
      const r = el.getBoundingClientRect();
      const next = () => new Promise<number>((resolve) => requestAnimationFrame(resolve));
      const run = async (step: (i: number) => void, count: number) => {
        const times: number[] = [];
        let last = await next();
        for (let i = 0; i < count; i++) {
          step(i);
          const now = await next();
          times.push(now - last);
          last = now;
        }
        times.sort((a, b) => a - b);
        return { median: Math.round(times[times.length >> 1]), p95: Math.round(times[Math.floor(times.length * 0.95)]), max: Math.round(times[times.length - 1]) };
      };
      const pan = await run((i) => el.dispatchEvent(new WheelEvent("wheel", { deltaX: i % 20 < 10 ? 24 : -24, deltaY: 12, clientX: r.left + 200, clientY: r.top + 200, bubbles: true, cancelable: true })), 90);
      const point = (type: string, i: number) => new PointerEvent(type, { pointerId: 9, pointerType: "mouse", button: 0, buttons: type === "pointerup" ? 0 : 1, clientX: r.left + 100 + i * 4, clientY: r.top + 150 + Math.sin(i / 8) * 60, pressure: 0.5, bubbles: true, cancelable: true });
      el.dispatchEvent(point("pointerdown", 0));
      const stroke = await run((i) => el.dispatchEvent(point("pointermove", i + 1)), 120);
      el.dispatchEvent(point("pointerup", 121));
      return { pan, stroke };
    });
    // Undo of one stroke on a 5,000-stroke drawing (full replay).
    const undoStart = Date.now();
    await page.keyboard.press("Control+z");
    await expect(page.locator(".draw-save")).toHaveText("Saved locally", { timeout: 15000 });
    const undoMs = Date.now() - undoStart;
    await page.keyboard.press("Control+y");
    const metrics = { seedMs: seeded.ms, openMs, fitReplay, actualReplay, zoomReplay, panMs, panReplay, undoMs, frames };
    console.log(`Draw large-drawing metrics: ${JSON.stringify(metrics)}`);
    expect(openMs).toBeLessThan(30000);
  } finally {
    await app.close().catch(() => undefined);
    await rm(profile, { recursive: true, force: true });
  }
});

test("OLIVE Draw: the largest canvas exports at full size; oversized canvases are refused", async () => {
  test.skip(process.platform !== "linux", "Linux desktop acceptance");
  test.setTimeout(300000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-draw-max-"));
  const out = await mkdtemp(path.join(tmpdir(), "olive-draw-max-out-"));
  const { app, page } = await launch(profile);
  try {
    await openSpace(page, "OLIVE Draw");
    // Custom size dialog refuses a canvas that would exhaust memory.
    await page.getByRole("button", { name: "New drawing with another canvas size", exact: true }).click();
    await page.getByRole("menuitem", { name: /^Custom size/ }).click();
    const dialog = page.getByRole("dialog", { name: "New drawing" });
    await dialog.getByRole("spinbutton", { name: "Width" }).fill("100000");
    await dialog.getByRole("spinbutton", { name: "Height" }).fill("100000");
    await dialog.getByRole("button", { name: "Create", exact: true }).click();
    await expect(dialog.getByRole("alert")).toContainText("Canvas too large");
    await dialog.getByRole("spinbutton", { name: "Width" }).fill("8192");
    await dialog.getByRole("spinbutton", { name: "Height" }).fill("4096");
    await dialog.getByRole("button", { name: "Create", exact: true }).click();
    await expect(canvas(page)).toBeVisible();
    await expect(page.locator(".draw-statusbar")).toContainText("8192 × 4096 px");
    await page.getByRole("spinbutton", { name: "Pen size in pixels" }).fill("64");
    await drawLine(page, { x: 500, y: 2000 }, { x: 7700, y: 2000 });
    await saved(page);
    const started = Date.now();
    const file = path.join(out, "max.png");
    await exportAs(page, app, file, /^Export PNG/);
    const exportMs = Date.now() - started;
    const decoded = await decode(page, file, "image/png", [{ x: 4000, y: 2000 }, { x: 4000, y: 2100 }]);
    expect([decoded.width, decoded.height]).toEqual([8192, 4096]);
    expect(near(decoded.samples[0], INK.black, 0)).toBe(true);
    expect(near(decoded.samples[1], INK.white, 0)).toBe(true);
    const memory = await app.evaluate(async ({ app: electronApp }) =>
      electronApp.getAppMetrics().reduce((sum, metric) => sum + metric.memory.workingSetSize, 0));
    console.log(`Draw max canvas: export ${exportMs} ms, Electron working set after export ${Math.round(memory / 1024)} MB`);
  } finally {
    await app.close().catch(() => undefined);
    await rm(profile, { recursive: true, force: true });
    await rm(out, { recursive: true, force: true });
  }
});
