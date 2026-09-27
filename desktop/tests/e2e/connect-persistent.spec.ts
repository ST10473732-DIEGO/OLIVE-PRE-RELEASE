import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { openSpace } from "./shell";

test("persistent Connect is explicit, reports exact ports, and Off persists", async () => {
  const root = path.resolve("..");
  const profile = await mkdtemp(path.join(tmpdir(), "olive-persistent-ui-"));
  const shim = path.join(profile, "shim");
  await mkdir(shim);
  await writeFile(path.join(shim, "sitecustomize.py"),
    `import sys,runpy\nsys.path.insert(0,${JSON.stringify(root)})\nrunpy.run_path(${JSON.stringify(path.join(root, "tests/fixtures/connect_ui_runtime.py"))})\n`);
  const env = { ...process.env, OLIVE_DATA_DIR: profile, PYTHONPATH: shim, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1" };
  const settings = async () => JSON.parse(await readFile(path.join(profile, "connect/network-v1.json"), "utf8"));
  const app = await electron.launch({ args: [path.resolve(".")], env });
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Devices");
    const remember = page.getByRole("checkbox", { name: /Keep Connect available after restart/ });
    await expect(remember).not.toBeChecked();
    await page.getByRole("button", { name: /127\.0\.0\.1/ }).click();
    await remember.check();
    await page.getByRole("button", { name: "Turn Connect on", exact: true }).click();
    await expect(remember).toBeDisabled();
    await expect.poll(async () => {
      try { return (await settings()).enabled; } catch { return false; }
    }).toBe(true);
    const saved = await settings();
    expect(saved.interface.address).toBe("127.0.0.1");
    expect(saved.port).toBeGreaterThanOrEqual(1024);
    expect(saved.pairing_port).toBeGreaterThanOrEqual(1024);
    expect(saved.port).not.toBe(saved.pairing_port);
    await expect(page.getByText(`Connect port ${saved.port}. Pairing port ${saved.pairing_port} opens only during pairing.`)).toBeVisible();
    await page.getByRole("button", { name: "Pair a device", exact: true }).click();
    await expect(page.locator(".devices-qr svg")).toBeVisible();
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("button", { name: "Turn Connect off", exact: true }).last().click();
    await expect.poll(async () => (await settings()).enabled).toBe(false);
    expect((await settings()).port).toBe(saved.port);
    expect((await settings()).pairing_port).toBe(saved.pairing_port);
  } finally { await app.close(); }
  const restarted = await electron.launch({ args: [path.resolve(".")], env });
  try {
    const page = await restarted.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Devices");
    await expect(page.getByRole("button", { name: "Turn Connect on", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Turn Connect off", exact: true })).toHaveCount(0);
  } finally { await restarted.close(); }
});
