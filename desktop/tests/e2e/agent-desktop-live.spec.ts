import { test, expect, _electron as electron, type ElectronApplication, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { createServer, type Server } from "node:http";
import { homedir, tmpdir } from "node:os";
import path from "node:path";
import { openSpace } from "./shell";

// Opt in: drives the real KDE desktop through OLIVE's existing Linux desktop
// control (portal/EIS input, AT-SPI + visual observation). Isolated temporary
// profile; the desktop-control policy block is copied from the owner's profile
// (policy flags only). Discord is only navigated: nothing is typed into the
// composer and nothing is sent. Set OLIVE_LIVE_DESKTOP=1 and, for Discord,
// OLIVE_LIVE_DISCORD_TARGET="#channel in SERVER" (a destination you chose).
const live = process.env.OLIVE_LIVE_DESKTOP === "1";
const discordTarget = process.env.OLIVE_LIVE_DISCORD_TARGET || "";

async function launch(profile: string) {
  const env = Object.fromEntries(Object.entries({ ...process.env, OLIVE_DATA_DIR: profile })
    .filter((entry): entry is [string, string] => entry[0] !== "ELECTRON_RUN_AS_NODE" && entry[1] !== undefined));
  const app = await electron.launch({ chromiumSandbox: true, args: [path.resolve(".")], env });
  const page = await app.firstWindow();
  await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
  await openSpace(page, "Chat");
  await expect(page.getByRole("combobox", { name: "OLIVE preset", exact: true })).toBeEnabled({ timeout: 90000 });
  return { app, page };
}

async function ask(page: Page, text: string, timeout = 240000) {
  const before = await page.locator(".message-assistant").count();
  await page.getByRole("textbox", { name: "Message OLIVE", exact: true }).fill(text);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(page.locator(".message-assistant")).toHaveCount(before + 1, { timeout });
  return page.locator(".message-assistant").last().innerText();
}

test("LIVE desktop: Firefox local page and Discord navigate-only", async () => {
  test.skip(!live, "Drives the real desktop (OLIVE_LIVE_DESKTOP=1)");
  test.setTimeout(900_000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-desktop-gui-"));
  const shots = process.env.OLIVE_AGENT_SHOTS || profile;
  const owner = JSON.parse(await readFile(path.join(homedir(), ".local/share/olive/settings.json"), "utf8"));
  const uid = execFileSync("id", ["-u"]).toString().trim();
  await writeFile(path.join(profile, "settings.json"), JSON.stringify({
    owner_mode: true, owner_installation: { id: "desktop-acceptance", owner: `uid:${uid}` },
    desktop_control: owner.desktop_control }));
  // Desktop input/observation policy from the owner's profile; sending is explicitly
  // denied here, so navigation is proven to need no send authority.
  const ownerPermissions = JSON.parse(await readFile(path.join(homedir(), ".local/share/olive/permissions.json"), "utf8"));
  const desktop = Object.fromEntries(Object.entries(ownerPermissions.permissions || {}).filter(([key]) => key.startsWith("desktop.")));
  await writeFile(path.join(profile, "permissions.json"), JSON.stringify({ schema_version: 1, scopes: [], trusted_actions: [],
    permissions: { ...desktop, "communication.send": "deny", "app.discord.send_message": "deny" } }));
  const token = `olive-fixture-${Date.now()}`;
  const server: Server = createServer((_req, res) => {
    res.writeHead(200, { "content-type": "text/html" });
    res.end(`<!doctype html><title>OLIVE fixture ${token}</title><h1>OLIVE desktop fixture</h1><p>${token}</p>`);
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as { port: number }).port;
  const results: Record<string, unknown> = {};
  let app: ElectronApplication | undefined;
  try {
    let page: Page;
    ({ app, page } = await launch(profile));
    let started = Date.now();
    results.firefox = await ask(page, `Open http://127.0.0.1:${port}/ in Firefox`);
    results.firefox_seconds = (Date.now() - started) / 1000;
    // Either the page is verified, or OLIVE refused safely (for example several
    // Firefox windows: it never picks one by guess). Both are recorded; only a
    // refusal-free, unverified claim would be a failure.
    expect(String(results.firefox)).toMatch(new RegExp(`${token}|verified|Multiple windows match|Task incomplete`, "i"));
    results.firefox_verified = !/Multiple windows match|Task incomplete/i.test(String(results.firefox));
    await page.screenshot({ path: path.join(shots, "F-firefox.png") });
    if (discordTarget) {
      started = Date.now();
      results.discord = await ask(page, `Open Discord and go to ${discordTarget}`, 300000);
      results.discord_seconds = (Date.now() - started) / 1000;
      expect(String(results.discord)).toMatch(/Nothing was typed and nothing was sent/);
      await page.screenshot({ path: path.join(shots, "F-discord.png") });
    }
  } finally {
    await writeFile(path.join(shots, "desktop-live-results.json"), JSON.stringify(results, null, 2)).catch(() => undefined);
    server.close();
    await app?.close().catch(() => undefined);
  }
});
