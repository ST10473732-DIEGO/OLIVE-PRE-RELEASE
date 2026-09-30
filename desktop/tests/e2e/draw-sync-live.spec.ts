import { test, expect, _electron as electron, type ElectronApplication, type Page } from "@playwright/test";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { openSpace } from "./shell";
import { INK, canvas, decode, drawLine, exportAs, makeImageFixtures, near, root, saved, screenPixel, stubOpen } from "./draw-helpers";

// Two real OLIVE desktops (isolated profiles, real Electron UI, real Python
// backends) paired with the product's desktop pairing and connected over real
// OLIVE Connect TLS on loopback. The only test change: Connect identity keys
// live in an in-memory vault (tests/fixtures/draw_live_runtime.py), so the run
// never touches the OS keyring. No phone is involved in this test.

async function start(profile: string, shim: string) {
  const env = { ...process.env, OLIVE_DATA_DIR: profile, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1", OLIVE_START_OLLAMA: "0", PYTHONPATH: shim };
  delete (env as Record<string, string | undefined>).ELECTRON_RUN_AS_NODE;
  const app = await electron.launch({ args: [path.resolve(".")], env, timeout: 120000 });
  const page = await app.firstWindow();
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1400, 900));
  await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
  return { app, page };
}

const call = async <T,>(page: Page, method: string, args: Record<string, unknown>): Promise<T> => {
  try {
    return await page.evaluate(async ([m, a]) => (await window.olive.call(m as never, a as never)) as unknown, [method, args] as const) as T;
  } catch (failure) {
    throw new Error(`${method} failed: ${failure instanceof Error ? failure.message : failure}`, { cause: failure });
  }
};

type Snapshot = { local: { device_id: string }; network: { port: number | null }; devices: { device_id: string; trust_state: string; draw_sync?: { state: string } | null }[] };

/** The colour picker is always in the toolbar (quick swatches hide on narrow windows). */
async function setColor(page: Page, hex: string) {
  await page.getByLabel("Pen colour", { exact: true }).fill(hex);
}

async function pixel(page: Page, x: number, y: number) {
  return screenPixel(page, { x, y });
}

test("OLIVE Draw live sync: two real desktops over OLIVE Connect TLS", async () => {
  test.skip(process.platform !== "linux", "Linux desktop acceptance");
  test.setTimeout(600000);
  const base = await mkdtemp(path.join(tmpdir(), "olive-draw-live-"));
  const shim = path.join(base, "shim");
  await mkdir(shim);
  await writeFile(path.join(shim, "sitecustomize.py"),
    `import sys,runpy\nsys.path.insert(0,${JSON.stringify(root)})\nrunpy.run_path(${JSON.stringify(path.join(root, "tests/fixtures/draw_live_runtime.py"))})\n`);
  const fixtures = path.join(base, "fixtures");
  makeImageFixtures(fixtures);
  let a: { app: ElectronApplication; page: Page } | null = null;
  let b: { app: ElectronApplication; page: Page } | null = null;
  try {
    a = await start(path.join(base, "a"), shim);
    b = await start(path.join(base, "b"), shim);
    const A = a.page, B = b.page;
    // Connect on loopback, then the product's desktop pairing (compare the code on both).
    await call(A, "connect.enable", { address: "127.0.0.1", discovery: false });
    await call(B, "connect.enable", { address: "127.0.0.1", discovery: false });
    const offer = await call<{ session_id: string; offer: string }>(A, "connect.pair_create", {});
    await call(B, "connect.pair_accept", { offer: offer.offer });
    const status = (page: Page) => call<{ state: string; comparison?: string }>(page, "connect.pair_status", { session_id: offer.session_id });
    await expect.poll(async () => Boolean((await status(A)).comparison && (await status(B)).comparison), { timeout: 20000 }).toBe(true);
    const code = (await status(A)).comparison!;
    expect((await status(B)).comparison).toBe(code);
    await call(A, "connect.pair_confirm", { session_id: offer.session_id, compared_value: code });
    await call(B, "connect.pair_confirm", { session_id: offer.session_id, compared_value: code });
    const idA = (await call<Snapshot>(A, "connect.snapshot", {})).local.device_id;
    const idB = (await call<Snapshot>(B, "connect.snapshot", {})).local.device_id;
    const paired = async (page: Page, peer: string) =>
      (await call<Snapshot>(page, "connect.snapshot", {})).devices.find((d) => d.device_id === peer)?.trust_state;
    await expect.poll(() => paired(A, idB), { timeout: 20000 }).toBe("paired");
    await expect.poll(() => paired(B, idA), { timeout: 20000 }).toBe("paired");
    const snapB = await call<Snapshot>(B, "connect.snapshot", {});
    // Draw sync is Off by default and separate from Notes; allow it on both.
    await call(A, "connect.permission", { device_id: idB, capability: "sync.draw", decision: "allow" });
    await call(B, "connect.permission", { device_id: idA, capability: "sync.draw", decision: "allow" });
    await call(A, "connect.open", { device_id: idB, address: "127.0.0.1", port: snapB.network.port });
    await expect.poll(async () => (await call<Snapshot>(A, "connect.snapshot", {})).devices.find((d) => d.device_id === idB)?.draw_sync?.state,
      { timeout: 20000 }).toMatch(/synced|syncing|idle/);

    // A draws; B receives the drawing and the stroke.
    await openSpace(A, "OLIVE Draw");
    await A.getByRole("button", { name: "New drawing", exact: true }).last().click();
    await expect(canvas(A)).toBeVisible();
    await A.getByRole("textbox", { name: "Drawing title" }).fill("Live sync");
    await A.getByRole("textbox", { name: "Drawing title" }).press("Enter");
    await setColor(A, "#e53935");
    await A.getByRole("spinbutton", { name: "Pen size in pixels" }).fill("12");
    await drawLine(A, { x: 200, y: 200 }, { x: 900, y: 200 });
    await saved(A);
    await openSpace(B, "OLIVE Draw");
    await expect(B.getByRole("list", { name: "Drawings" }).getByText("Live sync", { exact: true })).toBeVisible({ timeout: 20000 });
    await B.getByRole("list", { name: "Drawings" }).getByText("Live sync", { exact: true }).click();
    await expect.poll(async () => near(await pixel(B, 500, 200), INK.red, 10), { timeout: 20000 }).toBe(true);

    // B draws; A's open canvas updates live, without reopening or losing its view.
    const zoomA = await canvas(A).getAttribute("data-zoom");
    await setColor(B, "#1e63e9");
    await B.getByRole("spinbutton", { name: "Pen size in pixels" }).fill("12");
    const started = Date.now();
    await drawLine(B, { x: 200, y: 300 }, { x: 900, y: 300 });
    await expect.poll(async () => near(await pixel(A, 500, 300), INK.blue, 10), { timeout: 20000 }).toBe(true);
    const liveMs = Date.now() - started;
    expect(await canvas(A).getAttribute("data-zoom")).toBe(zoomA);

    // Offline on both sides, each draws; reconnect converges with both edits.
    await call(A, "connect.disconnect", { device_id: idB });
    await expect.poll(async () => (await call<Snapshot>(B, "connect.snapshot", {})).devices.find((d) => d.device_id === idA)?.draw_sync?.state,
      { timeout: 20000 }).toBe("offline");
    await setColor(A, "#43a047");
    await drawLine(A, { x: 200, y: 400 }, { x: 900, y: 400 });
    await setColor(B, "#8e24aa");
    await drawLine(B, { x: 200, y: 500 }, { x: 900, y: 500 });
    await saved(A);
    await saved(B);
    await A.waitForTimeout(800);
    expect(near(await pixel(A, 500, 500), INK.white, 3)).toBe(true);   // Not delivered while offline.
    expect(near(await pixel(B, 500, 400), INK.white, 3)).toBe(true);
    await call(A, "connect.open", { device_id: idB, address: "127.0.0.1", port: snapB.network.port });
    await expect.poll(async () => near(await pixel(A, 500, 500), [142, 36, 170, 255], 12), { timeout: 20000 }).toBe(true);
    await expect.poll(async () => near(await pixel(B, 500, 400), INK.green, 12), { timeout: 20000 }).toBe(true);

    // An imported image on A arrives on B: the operation, then the asset by hash.
    await stubOpen(a.app, path.join(fixtures, "transparent.png"));
    await A.getByRole("button", { name: "Import image", exact: true }).click();
    await expect(A.locator(".draw-notice")).toContainText("Imported transparent.png");
    await saved(A);
    await expect.poll(async () => near(await pixel(B, 850, 450), INK.red, 12), { timeout: 30000 }).toBe(true);

    // Local-origin Undo on A removes A's import on both, never B's strokes.
    await canvas(A).focus();
    await A.keyboard.press("Control+z");
    await expect.poll(async () => near(await pixel(B, 850, 450), INK.white, 3), { timeout: 20000 }).toBe(true);
    expect(near(await pixel(A, 500, 300), INK.blue, 10)).toBe(true);
    expect(near(await pixel(A, 500, 500), [142, 36, 170, 255], 12)).toBe(true);

    // Both replicas export the same pixels.
    await saved(A);
    await expect.poll(async () => (await call<Snapshot>(A, "connect.snapshot", {})).devices.find((d) => d.device_id === idB)?.draw_sync?.state,
      { timeout: 20000 }).toBe("synced");
    const fileA = path.join(base, "a.png"), fileB = path.join(base, "b.png");
    await exportAs(A, a.app, fileA, /^Export PNG/);
    await exportAs(B, b.app, fileB, /^Export PNG/);
    const samples = [{ x: 500, y: 200 }, { x: 500, y: 300 }, { x: 500, y: 400 }, { x: 500, y: 500 }, { x: 850, y: 450 }];
    const pa = await decode(A, fileA, "image/png", samples), pb = await decode(B, fileB, "image/png", samples);
    expect(pa.hash).toBe(pb.hash);
    expect([pa.width, pa.height]).toEqual([1920, 1080]);
    // The Devices page shows Draw sync with this device.
    await openSpace(A, "Devices");
    console.log(`Draw live sync (two desktops, Connect TLS loopback): B stroke visible on A after ${liveMs} ms (includes pointer input)`);
  } finally {
    await a?.app.close().catch(() => undefined);
    await b?.app.close().catch(() => undefined);
    await rm(base, { recursive: true, force: true });
  }
});
