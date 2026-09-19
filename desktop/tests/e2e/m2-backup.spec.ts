import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, stat, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { openSpace } from "./shell";
test("Settings backup export and isolated restore retain records and require restart", async () => {
  const root = path.resolve("..");
  const source = await mkdtemp(path.join(tmpdir(), "olive-m2-backup-source-"));
  const target = await mkdtemp(path.join(tmpdir(), "olive-m2-backup-target-"));
  const archive = path.join(target, "fixture-backup.zip");
  const exported = path.join(target, "fixture-memory-export.json");
  const seed = spawnSync(
    path.join(root, ".venv/Scripts/python.exe"),
    [path.join(root, "scripts/seed_m2_handoff_fixture.py"), source],
    { cwd: root, encoding: "utf8", windowsHide: true },
  );
  expect(seed.status, seed.stderr).toBe(0);
  const ids = JSON.parse(seed.stdout);
  await writeFile(
    path.join(source, "fixture-credentials.json"),
    '{"fixture_only":"excluded from portable backup"}',
  );
  const launch = (profile: string) =>
    electron.launch({
      args: [path.resolve(".")],
      env: {
        ...process.env,
        OLIVE_DATA_DIR: profile,
        OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
      },
    });
  const settings = async (app: Awaited<ReturnType<typeof launch>>) => {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Settings");
    await page
      .getByRole("navigation", { name: "Settings categories" })
      .getByRole("button", { name: "Backup & Data", exact: true })
      .click();
    return page;
  };
  const first = await launch(source);
  try {
    const page = await settings(first);
    await first.evaluate(({ dialog }, file) => {
      dialog.showSaveDialog = async () => ({ canceled: false, filePath: file });
    }, archive);
    await page
      .getByRole("button", { name: "Create backup", exact: true })
      .click();
    await expect
      .poll(async () => {
        try {
          return (await stat(archive)).size;
        } catch {
          return 0;
        }
      })
      .toBeGreaterThan(100);
    await first.evaluate(({ dialog }, file) => {
      dialog.showSaveDialog = async () => ({ canceled: false, filePath: file });
    }, exported);
    await page
      .getByRole("button", { name: "Export memories", exact: true })
      .click();
    await expect
      .poll(async () => {
        try {
          return await readFile(exported, "utf8");
        } catch {
          return "";
        }
      })
      .toContain("Fixture project prefers outcome-based tests");
  } finally {
    await first.close();
  }
  const inspect = spawnSync(
    path.join(root, ".venv/Scripts/python.exe"),
    [
      "-c",
      "import zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); assert not any('credential' in n or 'vault' in n for n in z.namelist()); print('Credential files excluded')",
      archive,
    ],
    { encoding: "utf8", windowsHide: true },
  );
  expect(inspect.status, inspect.stderr).toBe(0);
  const second = await launch(target);
  try {
    const page = await settings(second);
    await second.evaluate(({ dialog }, file) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [file],
      });
      dialog.showMessageBox = async () => ({
        response: 1,
        checkboxChecked: false,
      });
    }, archive);
    await page
      .getByRole("button", { name: "Restore backup", exact: true })
      .click();
    await expect(
      page.getByText(/Restore complete. Restart OLIVE to reload all services/),
    ).toBeVisible();
    expect(
      await page.evaluate(async () => {
        try {
          await window.olive.call("data.create_project", {
            title: "must not create",
          });
          return false;
        } catch {
          return true;
        }
      }),
    ).toBe(true);
  } finally {
    await second.close();
  }
  const restored = await launch(target);
  try {
    const page = await restored.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    const snapshot = (await page.evaluate(() =>
      window.olive.call("runtime.snapshot", {}),
    )) as {
      chat: { id: string };
      approvals: unknown[];
      activity: { count: number };
    };
    expect(snapshot.chat.id).toBe(ids.chat_id);
    expect(snapshot.approvals).toEqual([]);
    expect(snapshot.activity.count).toBe(0);
    const memories = (await page.evaluate(() =>
      window.olive.call("data.memories", {}),
    )) as { id: string }[];
    expect(memories.some((memory) => memory.id === ids.memory_id)).toBe(true);
    const projects = (await page.evaluate(() =>
      window.olive.call("data.projects", {}),
    )) as { id: string }[];
    expect(projects.some((project) => project.id === ids.project_id)).toBe(
      true,
    );
  } finally {
    await restored.close();
  }
});
