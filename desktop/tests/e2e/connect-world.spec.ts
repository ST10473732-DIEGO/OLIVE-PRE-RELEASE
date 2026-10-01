import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile, readFile, rename } from "node:fs/promises";
import { tmpdir } from "node:os";
import { openSpace } from "./shell";

// OLIVE Connect World in the real desktop app: a LOCAL development relay on loopback and a
// phone-role test peer forced onto World. This is not an internet or cellular acceptance.
test("OLIVE Connect World: Devices shows Ready and a peer Connected · World", async () => {
  test.setTimeout(180000);
  const root = path.resolve(".."),
    profile = await mkdtemp(path.join(tmpdir(), "olive-world-ui-")),
    shim = path.join(profile, "shim");
  await mkdir(shim);
  await writeFile(
    path.join(shim, "sitecustomize.py"),
    `import sys,runpy\nsys.path.insert(0,${JSON.stringify(root)})\nrunpy.run_path(${JSON.stringify(path.join(root, "tests/fixtures/connect_world_ui_runtime.py"))})\n`,
  );
  const evidence = process.env.OLIVE_WORLD_EVIDENCE || path.join(root, "artifacts/connect-world");
  await mkdir(evidence, { recursive: true });
  const env: Record<string, string> = { ...(process.env as Record<string, string>), OLIVE_DATA_DIR: profile,
    PYTHONPATH: shim, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1" };
  delete env.ELECTRON_RUN_AS_NODE;
  delete env.NODE_OPTIONS;
  const app = await electron.launch({ args: [path.resolve(".")], env });
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(20000);
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const shot = (name: string) => page.screenshot({ path: path.join(evidence, `${name}.png`) });
    const control = async (action: string) => {
      const id = crypto.randomUUID();
      await writeFile(path.join(profile, "fixture-command.tmp"), JSON.stringify({ id, action }));
      await rename(path.join(profile, "fixture-command.tmp"), path.join(profile, "fixture-command.json"));
      await expect.poll(async () => {
        try { return JSON.parse(await readFile(path.join(profile, "fixture-result.json"), "utf8")).id; }
        catch { return null; }
      }, { timeout: 90000 }).toBe(id);
      return JSON.parse(await readFile(path.join(profile, "fixture-result.json"), "utf8")).result;
    };
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1440, 900));
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Devices");
    // OLIVE Connect on (loopback), then World on with the local relay (Advanced › Relay URL).
    await page.getByRole("button", { name: /127\.0\.0\.1/ }).click();
    await page.getByRole("button", { name: "Turn Connect on", exact: true }).click();
    await expect(page.getByRole("button", { name: "Turn Connect off", exact: true }).last()).toBeVisible();
    const card = page.getByRole("region", { name: "OLIVE Connect World" });
    await expect(card).toBeVisible();
    await expect(card.getByRole("status")).toHaveText("Off");
    await shot("world-off");
    await card.getByText("Advanced", { exact: true }).click();
    await card.getByLabel("Relay URL").fill(await control("relay_url"));
    await card.getByRole("button", { name: "Use relay", exact: true }).click();
    await expect(card.locator(".devices-facts")).toContainText("127.0.0.1");   // Saved by the backend.
    const toggle = card.getByRole("checkbox", { name: "OLIVE Connect World" });
    await toggle.click();
    await expect(toggle).toBeChecked();
    await expect(card.getByRole("status")).toHaveText("Ready");
    await shot("world-ready-no-device");
    const peer = await control("world_peer");
    expect(peer.path).toBe("world");
    const row = page.locator(".devices-row", { hasText: "World test iPhone" });
    await expect(row).toContainText("Connected · World", { timeout: 30000 });
    await row.click();
    await expect(page.locator(".devices-detail-head")).toContainText("Connected · World");
    await expect(page.locator(".devices-facts").first()).toContainText("World");
    await page.getByText(/OLIVE Connect World · /).click();
    await expect(page.getByText("OLIVE Connect World · Connected · World")).toBeVisible();
    await shot("world-peer-connected");
    const html = await page.content();
    const status = await control("world_status");
    expect(status.relay).toBe("connected");
    expect(html).not.toMatch(/route_secret|relay_credential|credential/i);
    expect(errors).toEqual([]);
  } finally {
    await app.close();
  }
});
