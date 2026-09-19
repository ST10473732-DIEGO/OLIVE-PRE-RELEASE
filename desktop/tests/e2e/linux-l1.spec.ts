import { test, expect, _electron as electron } from "@playwright/test";
import { mkdtemp, writeFile, readFile } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { openSpace } from "./shell";

for (const display of ["auto", "wayland"]) test(`Linux ${display}: launcher, portable pages, persistence, security and owned shutdown`, async () => {
  test.skip(process.platform !== "linux", "Native Linux L1 acceptance");
  test.setTimeout(180000);
  const root = path.resolve(".."), profile = await mkdtemp(path.join(tmpdir(), "olive-linux-l1-"));
  const source = path.join(profile, "Linux-fixture.txt");
  await writeFile(source, "The synthetic Linux notebook is blue. Local retrieval must preserve this source.");
  const app = await electron.launch({
    executablePath: path.join(root, "run_olive.sh"),
    chromiumSandbox: true,
    args: display === "wayland" ? ["--ozone-platform=wayland"] : [],
    env: { ...process.env, OLIVE_DATA_DIR: profile, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1" },
    timeout: 60000,
  });
  const errors: string[] = [];
  let owned: { pid: number; created: number }[] = [];
  try {
    const page = await app.firstWindow();
    page.on("pageerror", e => errors.push(e.message));
    page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
    const security = await app.evaluate(({ BrowserWindow }) => {
      const preferences = (BrowserWindow.getAllWindows()[0].webContents as unknown as { getLastWebPreferences: () => Record<string, boolean> }).getLastWebPreferences();
      return { sandbox: preferences.sandbox, contextIsolation: preferences.contextIsolation, nodeIntegration: preferences.nodeIntegration, args: process.argv };
    });
    expect(security).toMatchObject({ sandbox: true, contextIsolation: true, nodeIntegration: false });
    expect(security.args).not.toContain("--no-sandbox");
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    for (const name of ["Chat", "Projects", "Knowledge", "Memory", "Tasks", "Calendar", "Reminders", "Agent", "Mail", "Settings", "Studio", "OLIVE GO", "Desktop Control"]) {
      await openSpace(page, name);
      if (name === "Chat") await expect(page.getByRole("textbox", { name: "Message OLIVE", exact: true })).toBeVisible();
      else if (name === "Studio") await expect(page.getByRole("heading", { name: "Your next idea starts here.", exact: true })).toBeVisible();
      else if (name === "OLIVE GO") await expect(page.locator(".go-field")).toBeVisible();
      else await expect(page.getByRole("heading", { name, exact: true }).first()).toBeVisible();
      await expect(page.getByRole("alert")).toHaveCount(0);
    }
    await expect(page.getByText("Desktop Control for Linux is not available in this build yet.", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "OLIVE activity", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Activity", exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
    await openSpace(page, "Projects");
    await page.getByRole("button", { name: "New project", exact: true }).click();
    await page.getByRole("textbox", { name: "Project title" }).fill("Linux L1 synthetic project");
    await page.getByRole("button", { name: "Create project", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Linux L1 synthetic project" })).toBeVisible();
    await openSpace(page, "Memory");
    await page.getByRole("button", { name: "Add memory", exact: true }).click();
    await page.getByRole("textbox", { name: "Memory", exact: true }).fill("Linux L1 synthetic memory");
    await page.getByRole("button", { name: "Save memory", exact: true }).click();
    await expect(page.getByText("Linux L1 synthetic memory", { exact: true })).toBeVisible();
    await openSpace(page, "Knowledge");
    // Control only the picker response; ingestion and retrieval use real services.
    await app.evaluate(({ dialog }, file) => { dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [file] }); }, source);
    await page.getByRole("button", { name: "Add source", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Linux-fixture.txt", exact: true })).toBeVisible({ timeout: 30000 });
    await page.getByRole("button", { name: "Retrieval inspector", exact: true }).click();
    await page.getByRole("textbox", { name: "Retrieval query" }).fill("synthetic blue notebook");
    await page.getByRole("button", { name: "Inspect retrieval", exact: true }).click();
    await expect(page.getByText("Score", { exact: false }).first()).toBeVisible({ timeout: 30000 });
    await page.keyboard.press("Escape");
    await openSpace(page, "Tasks");
    await page.getByRole("button", { name: "New Task", exact: true }).click();
    await page.getByRole("textbox", { name: "Task title", exact: true }).fill("Linux L1 synthetic task");
    await page.getByRole("button", { name: "Save Task", exact: true }).click();
    await expect(page.getByRole("button", { name: /Linux L1 synthetic task.*normal/ })).toBeVisible();
    await openSpace(page, "Calendar");
    await page.getByRole("button", { name: "New Event", exact: true }).click();
    await page.getByRole("textbox", { name: "Event title", exact: true }).fill("Linux L1 synthetic event");
    await page.getByRole("button", { name: "Save Event", exact: true }).click();
    await expect(page.getByRole("button", { name: /Linux L1 synthetic event/ })).toBeVisible();
    await openSpace(page, "Reminders");
    await page.getByRole("button", { name: "New Reminder", exact: true }).click();
    await page.getByLabel("Reminder domain", { exact: true }).selectOption("task");
    await page.getByLabel("Reminder target", { exact: true }).selectOption({ label: "Linux L1 synthetic task" });
    await page.getByLabel("Explicit reminder time", { exact: true }).fill("2030-01-01T10:00");
    await page.getByRole("button", { name: "Save Reminder", exact: true }).click();
    await openSpace(page, "Mail");
    await page.getByRole("button", { name: "Compose", exact: true }).click();
    await page.getByRole("textbox", { name: "Subject", exact: true }).fill("Linux L1 offline draft");
    await page.getByRole("button", { name: "Save draft", exact: true }).click();
    await expect(page.getByText("Saved locally", { exact: false }).first()).toBeVisible();
    await openSpace(page, "Chat");
    await page.screenshot({ path: test.info().outputPath("linux-chat.png") });
    await page.reload();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Memory");
    await expect(page.getByText("Linux L1 synthetic memory", { exact: true })).toBeVisible();
    expect(JSON.parse(await readFile(path.join(profile, "projects.json"), "utf8"))).toBeTruthy();
    expect(errors).toEqual([]);
    const pid = app.process().pid!;
    const probe = spawnSync(path.join(root, ".venv/bin/python"), ["-c", "import psutil,json,sys; p=psutil.Process(int(sys.argv[1])); print(json.dumps([dict(pid=c.pid,created=c.create_time()) for c in [p,*p.children(recursive=True)]]))", String(pid)], { encoding: "utf8" });
    expect(probe.status, probe.stderr).toBe(0);
    owned = JSON.parse(probe.stdout);
    expect(owned.length).toBeGreaterThan(2);
    await writeFile(test.info().outputPath("acceptance.json"), JSON.stringify({ display, security, ownedProcessCount: owned.length, rendererErrors: errors }, null, 2));
  } finally { await app.close(); }
  await expect.poll(() => {
    const probe = spawnSync(path.join(root, ".venv/bin/python"), ["-c", "import psutil,json,sys; alive=[]\nfor item in json.loads(sys.argv[1]):\n try:\n  p=psutil.Process(item['pid'])\n  if p.create_time()==item['created'] and p.status()!=psutil.STATUS_ZOMBIE: alive.append(item['pid'])\n except psutil.NoSuchProcess: pass\nprint(json.dumps(alive))", JSON.stringify(owned)], { encoding: "utf8" });
    expect(probe.status, probe.stderr).toBe(0);
    return JSON.parse(probe.stdout);
  }, { timeout: 15000 }).toEqual([]);
});
