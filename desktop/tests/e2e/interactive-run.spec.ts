import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { openSpace } from "./shell";

for (const language of ["Python", "C#"]) test(`${language} ordinary Run connects real keyboard input to ConPTY and survives route churn`, async () => {
  const root = path.resolve("..");
  const profile = await mkdtemp(path.join(tmpdir(), "olive-interactive-run-"));
  const seed = spawnSync(path.join(root, ".venv/Scripts/python.exe"),
    [path.join(root, "scripts/seed_electron_fixture.py"), profile],
    { cwd: root, encoding: "utf8", windowsHide: true });
  expect(seed.status, seed.stderr).toBe(0);
  await writeFile(path.join(profile, "fixture-workspace/main.py"),
    'for _ in range(3):\n    name = input("Enter a word: ")\n    print("Received: " + name, flush=True)\n');
  if (language === "C#") {
    const sdk = spawnSync("dotnet", ["--version"], { encoding: "utf8", windowsHide: true });
    expect(sdk.status, sdk.stderr).toBe(0);
    const major = sdk.stdout.trim().split(".")[0];
    await writeFile(path.join(profile, "fixture-workspace/Fixture.csproj"),
      `<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net${major}.0</TargetFramework></PropertyGroup></Project>`);
    await writeFile(path.join(profile, "fixture-workspace/Program.cs"),
      'for (var i = 0; i < 3; i++) { System.Console.Write("Enter a word: "); var value = System.Console.ReadLine(); System.Console.WriteLine("Received: " + value); }');
  }
  const app = await electron.launch({ args: [path.resolve(".")], env: {
    ...process.env, OLIVE_DATA_DIR: profile, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
  } });
  const errors: string[] = [];
  let stderr = "";
  app.process().stderr?.on("data", (chunk) => { stderr += String(chunk); });
  try {
    const page = await app.firstWindow();
    page.on("pageerror", (error) => errors.push(error.message));
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Studio");
    await page.getByRole("button", { name: "Fixture · local Python project", exact: true }).click();
    await page.getByRole("button", { name: "Run", exact: true }).click();
    const terminal = page.locator('.terminal-view:not([hidden])');
    await expect(terminal).toBeVisible();
    await expect(terminal).toContainText("Enter a word:", { timeout: 20000 });
    const input = terminal.locator("textarea");
    await input.pressSequentially("leveX");
    await input.press("Backspace");
    await input.pressSequentially("l");
    await input.press("Enter");
    await expect(terminal).toContainText("Received: level");
    await input.pressSequentially("hello");
    await input.press("Enter");
    await expect(terminal).toContainText("Received: hello");
    // Synthetic DOM paste follows xterm's actual paste handler, without touching
    // the person's OS clipboard or writing to the backend input pipe.
    await input.evaluate((element) => {
      const data = new DataTransfer(); data.setData("text/plain", "radar");
      element.dispatchEvent(new ClipboardEvent("paste", { clipboardData: data, bubbles: true }));
    });
    await input.press("Enter");
    await expect(terminal).toContainText("Received: radar");
    await expect(page.getByRole("tab", { name: /Run program.*exited/ })).toBeVisible();
    const runState = () => page.evaluate(() => window.olive.call("runtime.snapshot", {})) as Promise<{
      runs: { id: string; workspace_id: string; state: string; terminal_session_id: string; stdout: string }[];
    }>;
    const first = (await runState()).runs.at(-1)!;
    expect(first.state).toBe("completed");
    expect(first.stdout.match(/Received: /g)).toHaveLength(3);
    await expect(page.evaluate((id) => window.olive.call("terminal.write", { session_id: id, data: "stale" }), first.terminal_session_id)).rejects.toThrow();
    for (let round = 0; round < 2; round++) {
      for (const feature of ["Chat", "OLIVE GO", "Studio", "Mail", "Agent", "Desktop Control", "Chat", "OLIVE GO", "Studio"])
        await openSpace(page, feature);
    }
    await expect(terminal).toContainText("Received: radar");
    await page.getByRole("button", { name: "Run", exact: true }).click();
    await expect.poll(async () => (await runState()).runs.length).toBe(2);
    await expect(terminal).toHaveAttribute("data-session-id", (await runState()).runs.at(-1)!.terminal_session_id);
    await expect(terminal).toContainText("Enter a word:");
    await terminal.locator("textarea").press("Control+c");
    await expect.poll(async () => (await runState()).runs.at(-1)?.state).not.toBe("running");
    await page.getByRole("button", { name: "Run", exact: true }).click();
    await expect.poll(async () => (await runState()).runs.length).toBe(3);
    await expect(terminal).toHaveAttribute("data-session-id", (await runState()).runs.at(-1)!.terminal_session_id);
    await expect(terminal).toContainText("Enter a word:");
    await page.getByRole("button", { name: "Stop program", exact: true }).click();
    await expect.poll(async () => (await runState()).runs.at(-1)?.state).toBe("stopped");
    expect(errors).toEqual([]);
    // The one explicit post-exit write above must fail; route churn must not
    // repeatedly issue it or generate any other rejected requests.
    expect((stderr.match(/Error occurred in handler for 'olive:call'/g) || []).length).toBe(1);
  } finally { await app.close(); }
});
