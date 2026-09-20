import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile, readFile, rename } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { openSpace } from "./shell";

test("C4 actual Devices UI with a second C2/C3 process and exact local Ask", async () => {
  test.setTimeout(180000);
  const root = path.resolve(".."),
    profile = await mkdtemp(path.join(tmpdir(), "olive-c4-ui-")),
    shim = path.join(profile, "shim");
  await mkdir(shim);
  await writeFile(
    path.join(shim, "sitecustomize.py"),
    `import sys,runpy\nsys.path.insert(0,${JSON.stringify(root)})\nrunpy.run_path(${JSON.stringify(path.join(root, "tests/fixtures/connect_ui_runtime.py"))})\n`,
  );
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      PYTHONPATH: shim,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
    },
  });
  const python = path.join(
    root,
    process.platform === "win32"
      ? ".venv/Scripts/python.exe"
      : ".venv/bin/python",
  );
  let owned: { pid: number; created: number }[] = [];
  const evidence = path.join(root, "artifacts/connect-c4");
  await mkdir(evidence, { recursive: true });
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(20000);
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const size = async (w: number, h: number) => {
      await app.evaluate(
        ({ BrowserWindow }, s) =>
          BrowserWindow.getAllWindows()[0].setContentSize(s[0], s[1]),
        [w, h],
      );
    };
    const shot = async (name: string) => {
      await page.screenshot({ path: path.join(evidence, `${name}.png`) });
    };
    const control = async (
      action: string,
      extra: Record<string, string> = {},
    ) => {
      const id = crypto.randomUUID();
      await writeFile(
        path.join(profile, "fixture-command.tmp"),
        JSON.stringify({ id, action, ...extra }),
      );
      await rename(
        path.join(profile, "fixture-command.tmp"),
        path.join(profile, "fixture-command.json"),
      );
      await expect
        .poll(async () => {
          try {
            return JSON.parse(
              await readFile(path.join(profile, "fixture-result.json"), "utf8"),
            ).id;
          } catch {
            return null;
          }
        })
        .toBe(id);
      return JSON.parse(
        await readFile(path.join(profile, "fixture-result.json"), "utf8"),
      ).result;
    };
    await size(1440, 900);
    await page
      .getByRole("button", { name: "Enter OLIVE", exact: true })
      .click();
    await openSpace(page, "Devices");
    await expect(
      page.getByRole("button", { name: "Turn Connect on", exact: true }),
    ).toBeDisabled();
    await expect(
      page.getByText("No paired devices yet.", { exact: false }),
    ).toBeVisible();
    await shot("this-device-off");
    await shot("nearby-empty");
    await page.getByRole("button", { name: /127\.0\.0\.1/ }).click();
    await page
      .getByRole("button", { name: "Turn Connect on", exact: true })
      .click();
    await expect(
      page
        .getByRole("button", { name: "Turn Connect off", exact: true })
        .last(),
    ).toBeVisible();
    await shot("this-device-on");
    await page
      .getByRole("button", { name: "Connect a device", exact: true })
      .click();
    await expect(page.locator(".devices-qr svg")).toBeVisible();
    await shot("pairing-qr");
    for (let i = 0; i < 5; i++) await page.keyboard.press("Tab");
    expect(
      await page.evaluate(() =>
        Boolean(document.activeElement?.closest('[role="dialog"]')),
      ),
    ).toBe(true);
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    expect(await control("listener")).toBe(false);
    const remoteOffer = await control("responder_offer");
    await page
      .getByRole("button", { name: "Pair device", exact: true })
      .click();
    await page
      .getByLabel("Pairing code", { exact: true })
      .fill(remoteOffer.offer);
    await page
      .getByRole("button", { name: "Use pairing code", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Compare both devices" }),
    ).toBeVisible();
    const paired = await control("comparison");
    await expect(
      page.getByRole("heading", { name: "Compare both devices" }),
    ).toBeVisible();
    await shot("pairing-comparison");
    await page
      .getByLabel("Value observed on the other device")
      .fill(paired.comparison);
    await page
      .getByRole("button", { name: "Values match", exact: true })
      .click();
    await expect(
      page.getByText("Waiting for the other device’s confirmation…"),
    ).toBeVisible();
    await control("finish_pair");
    await expect(
      page.getByRole("heading", { name: "Device paired", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Done", exact: true }).click();
    await page.getByRole("button", { name: /^Paired device.*Offline/ }).click();
    await shot("paired-offline");
    await page
      .getByRole("button", { name: "Permissions", exact: true })
      .click();
    const ping = page.getByRole("group", { name: "Connect ping", exact: true });
    await expect(
      ping.getByRole("button", { name: "Off", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await expect(
      page.getByText("Unavailable", { exact: true }).first(),
    ).toBeVisible();
    await shot("permissions");
    const peerEndpoint = await control("connect");
    await page.getByRole("button", { name: "Status", exact: true }).click();
    await expect(page.locator(".devices-tls")).toBeVisible();
    await page
      .getByRole("button", { name: "Measure latency", exact: true })
      .click();
    await expect(page.locator(".devices-detail-head")).toContainText(/ms/);
    await shot("paired-online");
    expect((await control("request", { key: "off" })).error).toBe(
      "permission_off",
    );
    await page
      .getByRole("button", { name: "Permissions", exact: true })
      .click();
    await ping.getByRole("button", { name: "Ask", exact: true }).click();
    expect((await control("request", { key: "denied" })).error).toBe(
      "confirmation_required",
    );
    await expect(
      page.getByRole("button", { name: "Deny", exact: true }),
    ).toBeVisible();
    await shot("ask-approval");
    await page.getByRole("button", { name: "Deny", exact: true }).click();
    expect((await control("request", { key: "denied" })).error).toBe(
      "request_denied",
    );
    expect((await control("request", { key: "approved" })).error).toBe(
      "confirmation_required",
    );
    await page.getByRole("button", { name: "Allow once", exact: true }).click();
    expect((await control("request", { key: "approved" })).state).toBe(
      "completed",
    );
    await expect(
      ping.getByRole("button", { name: "Ask", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("button", { name: "Activity", exact: true }).click();
    await expect(
      page.getByText("request approved · connect.ping"),
    ).toBeVisible();
    await shot("activity");
    // C5 uses the ordinary UI, native repositories and this already-authenticated
    // C3 channel. Fixture commands represent only local edits on each desktop.
    await page.getByRole("button", { name: "Status", exact: true }).click();
    const syncPanel = page.getByRole("region", { name: "Sync", exact: true });
    const tasksSync = syncPanel.getByRole("group", {
      name: "Tasks sync",
      exact: true,
    });
    await expect(
      tasksSync.getByRole("button", { name: "Off", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await control("sync_setup");
    await tasksSync.getByRole("button", { name: "Allow", exact: true }).click();
    await syncPanel
      .getByRole("button", { name: "Sync now", exact: true })
      .click();
    await expect(syncPanel.getByRole("status")).toContainText("completed");
    await expect(syncPanel.getByRole("status")).toContainText("1 received");
    await control("sync_conflict");
    await syncPanel
      .getByRole("button", { name: "Sync now", exact: true })
      .click();
    await expect(syncPanel.getByRole("status")).toContainText("1 conflicts");
    await syncPanel
      .getByRole("button", { name: "Review conflicts", exact: true })
      .click();
    await expect(
      syncPanel.getByText("This device changed task", { exact: true }),
    ).toBeVisible();
    await expect(
      syncPanel.getByText("Peer changed task", { exact: true }),
    ).toBeVisible();
    await syncPanel
      .getByRole("button", { name: "Keep this device", exact: true })
      .click();
    await expect(
      syncPanel.getByText("No conflicts require review."),
    ).toBeVisible();
    await shot("c5-sync-conflict-resolved");
    await control("nearby");
    await expect(
      page.getByRole("button", { name: /OLIVE device.*Discovered/ }),
    ).toBeVisible();
    await shot("nearby-discovered");
    for (const [w, h] of [
      [1920, 1080],
      [1440, 900],
      [1366, 768],
      [1100, 760],
    ]) {
      await size(w, h);
      await page
        .getByRole("button", { name: "Permissions", exact: true })
        .click();
      await expect
        .poll(() =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        )
        .toBe(true);
      await shot(`permissions-${w}`);
    }
    await page
      .getByRole("button", { name: "Back to devices", exact: true })
      .click();
    await shot("narrow-list");
    await page.getByRole("button", { name: /^Paired device.*Online/ }).click();
    await shot("narrow-detail");
    await size(1440, 900);
    await page.evaluate(
      () => (document.documentElement.dataset.theme = "light"),
    );
    await shot("light-mode");
    await page.evaluate(
      () => (document.documentElement.dataset.theme = "dark"),
    );
    await page.getByRole("button", { name: "Status", exact: true }).click();
    await control("stop_reconnect");
    await page.getByRole("button", { name: "Disconnect", exact: true }).click();
    await page.getByLabel("Local address", { exact: true }).fill("127.0.0.1");
    await page.getByLabel("Connect port", { exact: true }).fill("1");
    await page.getByRole("button", { name: "Connect", exact: true }).click();
    await expect(page.locator(".devices-detail-head")).toContainText(
      "Connection failed",
    );
    await shot("connection-failed");
    await page
      .getByLabel("Connect port", { exact: true })
      .fill(String(peerEndpoint.port));
    await page.getByRole("button", { name: "Connect", exact: true }).click();
    await expect(page.locator(".devices-tls")).toBeVisible();
    await page
      .getByRole("button", { name: "Revoke device", exact: true })
      .click();
    await shot("revoke-confirmation");
    expect((await control("peer_status")).encrypted).toBe(true);
    await page.getByRole("button", { name: "Revoke", exact: true }).click();
    await expect(page.locator(".devices-detail-head")).toContainText("Revoked");
    await shot("revoked");
    expect(await control("peer_status")).toMatchObject({
      encrypted: false,
      latency_ms: null,
    });
    await expect(
      page.getByRole("button", { name: "Connect", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: /^This device/ }).click();
    await page
      .getByRole("button", { name: "Turn Connect off", exact: true })
      .last()
      .click();
    await expect(
      page.getByRole("button", { name: "Turn Connect on", exact: true }),
    ).toBeVisible();
    expect(errors).toEqual([]);
    const probe = spawnSync(
      python,
      [
        "-c",
        "import psutil,json,sys; p=psutil.Process(int(sys.argv[1])); print(json.dumps([dict(pid=c.pid,created=c.create_time()) for c in [p,*p.children(recursive=True)]]))",
        String(app.process().pid),
      ],
      { encoding: "utf8" },
    );
    expect(probe.status, probe.stderr).toBe(0);
    owned = JSON.parse(probe.stdout);
    expect(owned.length).toBeGreaterThan(3);
  } finally {
    await app.close();
  }
  await expect
    .poll(
      () => {
        const probe = spawnSync(
          python,
          [
            "-c",
            "import psutil,json,sys; alive=[]\nfor item in json.loads(sys.argv[1]):\n try:\n  p=psutil.Process(item['pid'])\n  if p.create_time()==item['created'] and p.status()!=psutil.STATUS_ZOMBIE: alive.append(item['pid'])\n except psutil.NoSuchProcess: pass\nprint(json.dumps(alive))",
            JSON.stringify(owned),
          ],
          { encoding: "utf8" },
        );
        expect(probe.status, probe.stderr).toBe(0);
        return JSON.parse(probe.stdout);
      },
      { timeout: 10000 },
    )
    .toEqual([]);
});

test("C4 expiry, regeneration and mismatched comparison never pair", async () => {
  test.setTimeout(60000);
  const root = path.resolve(".."),
    profile = await mkdtemp(path.join(tmpdir(), "olive-c4-expiry-")),
    shim = path.join(profile, "shim");
  await mkdir(shim);
  await writeFile(
    path.join(shim, "sitecustomize.py"),
    `import sys,runpy\nsys.path.insert(0,${JSON.stringify(root)})\nrunpy.run_path(${JSON.stringify(path.join(root, "tests/fixtures/connect_ui_runtime.py"))})\n`,
  );
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      PYTHONPATH: shim,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
    },
  });
  try {
    const page = await app.firstWindow();
    await page
      .getByRole("button", { name: "Enter OLIVE", exact: true })
      .click();
    await openSpace(page, "Devices");
    const command = async (action: string) => {
      const id = crypto.randomUUID();
      await writeFile(
        path.join(profile, "fixture-command.tmp"),
        JSON.stringify({ id, action }),
      );
      await rename(
        path.join(profile, "fixture-command.tmp"),
        path.join(profile, "fixture-command.json"),
      );
      await expect
        .poll(async () => {
          try {
            return JSON.parse(
              await readFile(path.join(profile, "fixture-result.json"), "utf8"),
            ).id;
          } catch {
            return null;
          }
        })
        .toBe(id);
      return JSON.parse(
        await readFile(path.join(profile, "fixture-result.json"), "utf8"),
      ).result;
    };
    await page.getByRole("button", { name: /127\.0\.0\.1/ }).click();
    await page
      .getByRole("button", { name: "Turn Connect on", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Connect a device", exact: true })
      .click();
    await expect(page.locator(".devices-qr svg")).toBeVisible();
    await command("expire");
    await expect(
      page.getByRole("heading", { name: "Pairing expired", exact: true }),
    ).toBeVisible();
    await expect(page.locator(".devices-qr svg")).toHaveCount(0);
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    expect(await command("listener")).toBe(false);
    const unreachable = await command("responder_unreachable");
    await page
      .getByRole("button", { name: "Pair device", exact: true })
      .click();
    await page
      .getByLabel("Pairing code", { exact: true })
      .fill(unreachable.offer);
    await page
      .getByRole("button", { name: "Use pairing code", exact: true })
      .click();
    await expect(
      page.getByText(/Could not reach pairing device/),
    ).toBeVisible();
    await page.getByRole("button", { name: "Cancel", exact: true }).click();

    await page
      .getByRole("button", { name: "Connect a device", exact: true })
      .click();
    await expect(page.locator(".devices-qr svg")).toBeVisible();
    await command("pair");
    await page
      .getByLabel("Value observed on the other device")
      .fill("C2/1:incorrect");
    await page
      .getByRole("button", { name: "Values match", exact: true })
      .click();
    await expect(
      page.getByText("Pairing failed. A new session is required."),
    ).toBeVisible();
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(
      page.getByText("No paired devices yet.", { exact: false }),
    ).toBeVisible();
  } finally {
    await app.close();
  }
});
