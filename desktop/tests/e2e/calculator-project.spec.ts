import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { openSpace, showPanel } from "./shell";

test("LIVE LOCAL Chat creates and runs a calculator with scoped fixture approvals", async () => {
  test.skip(process.env.OLIVE_LIVE_AI !== "1", "Requires local Ollama inference");
  test.setTimeout(600000);
  const root = path.resolve("..");
  const profile = await mkdtemp(path.join(tmpdir(), "olive-calculator-project-ui-"));
  const evidence = path.join(root, "artifacts/core/functionality/project");
  await mkdir(evidence, { recursive: true });
  const app = await electron.launch({ chromiumSandbox: true, args: [path.resolve(".")], env: { ...process.env, OLIVE_DATA_DIR: profile } });
  const fixtureServer = createServer((_request, response) => response.end("OLIVE baseline browser fixture"));
  await new Promise<void>(resolve => fixtureServer.listen(0, "127.0.0.1", resolve));
  let closed = false;
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await expect.poll(() => page.evaluate(async () => {
      const state = await window.olive.call("runtime.snapshot", {}) as { presets: { id: string; available: boolean }[] };
      return state.presets.find(preset => preset.id === "normal")?.available;
    }), { timeout: 30000 }).toBe(true);
    const snapshot = () => page.evaluate(() => window.olive.call("runtime.snapshot", {})) as Promise<{
      chat: { id: string; messages: { role: string; content: string }[] }; activity: { items: { method: string }[] };
      workspaces: { id: string; root_path: string }[];
      runs: { id: string; accepts_input: boolean; state: string; stdout: string }[];
      approvals: { id: string; tool_name: string; arguments: Record<string, unknown> }[];
    }>;
    await openSpace(page, "Chat");
    await page.getByRole("combobox", { name: "OLIVE preset", exact: true }).selectOption("fast");
    for (const question of ["What is recursion? Answer briefly.", "Give me Python code for a small calculator. Show the code here."]) {
      const before = (await snapshot()).chat.messages.length;
      await page.getByRole("textbox", { name: "Message OLIVE", exact: true }).fill(question);
      await page.getByRole("button", { name: "Send message", exact: true }).click();
      await expect.poll(async () => {
        const state = await snapshot();
        return state.chat.messages.length > before && !state.activity.items.length && state.chat.messages.at(-1)?.role === "assistant";
      }, { timeout: 150000 }).toBe(true);
      expect((await snapshot()).workspaces).toHaveLength(0);
      expect((await snapshot()).runs).toHaveLength(0);
    }
    await expect(page.locator('.message-assistant').last().locator('pre').first()).toBeVisible();
    const answerMessages = (await snapshot()).chat.messages.length;
    await page.getByRole("textbox", { name: "Message OLIVE", exact: true }).fill("Create a Python calculator project in Studio and run it. The console must repeatedly accept a complete expression on one input line, such as 2 + 3 or 8 / 2, print Result: followed by the answer, and exit when I enter quit. Include addition, subtraction, multiplication and division. For this acceptance fixture only import unittest, math, operator, sys or main; test the pure calculation function without mocking stdin or stdout. Preserve the existing greeting function and its existing tests. Only spaced three-token expressions are required; do not add tests for parentheses or other unsupported syntax.");
    await page.getByRole("button", { name: "Send message", exact: true }).click();
    const reviewFixtureActions = async (minimumMessages = answerMessages + 2) => {
      const deadline = Date.now() + 240000;
      const seen = new Set<string>();
      while (Date.now() < deadline) {
        const s = await snapshot();
        const approval = s.approvals[0];
        if (approval && !seen.has(approval.id)) {
          expect(seen.size).toBeLessThan(20);
          expect(["studio.new_project", "studio.tree", "studio.open", "studio.save", "code.create_file", "workspace.run_validation", "studio.run"]).toContain(approval.tool_name);
          const args = approval.arguments;
          const target = path.resolve(String(args.workspace || args.location));
          const relative = path.relative(profile, target);
          expect(relative.startsWith("..")).toBe(false);
          expect(path.isAbsolute(relative)).toBe(false);
          if (approval.tool_name === "studio.new_project") {
            expect(args.language).toBe("python"); expect(args.template).toBe("console"); expect(path.relative(profile, target)).toBe("");
          }
          if (args.text) {
            expect(String(args.path)).toMatch(/\.py$/);
            const parsed = spawnSync(path.join(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"), [path.join(root, "scripts/coding_project_acceptance.py"), "--check-source"], { input: String(args.text), encoding: "utf8", cwd: root });
            expect(parsed.status, parsed.stderr).toBe(0);
          }
          if (approval.tool_name === "workspace.run_validation") {
            for (const command of args.commands as { executable: string; arguments: string[] }[]) {
              const expectedPython = spawnSync(path.join(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"), ["-c", "import sys; print(sys.executable if sys.platform == 'win32' else sys._base_executable)"], { encoding: "utf8" }).stdout.trim();
              expect(path.resolve(command.executable)).toBe(expectedPython);
              expect(["compileall", "unittest"]).toContain(command.arguments[1]);
            }
          }
          seen.add(approval.id);
          await page.getByRole("dialog").getByRole("button", { name: "Approve this action", exact: true }).click();
        }
        if (!s.activity.items.some((item) => item.method.startsWith("interaction.")) && !s.approvals.length && s.chat.messages.length >= minimumMessages) return s;
        await page.waitForTimeout(250);
      }
      throw new Error("The real coding workflow did not complete within its bounded deadline");
    };
    const created = await reviewFixtureActions();
    const creationTrace = await page.evaluate((chat_id) => window.olive.call("interaction.inspect", { chat_id }), created.chat.id);
    await writeFile(path.join(evidence, "creation-trace.json"), JSON.stringify(creationTrace, null, 2));
    expect(created.workspaces, JSON.stringify(creationTrace)).toHaveLength(1);
    expect(created.chat.messages.at(-1)?.content).toContain("checks passed");
    const workspace = created.workspaces[0];
    const run = created.runs.find((r) => r.accepts_input && r.state === "running");
    expect(run).toBeTruthy();
    await openSpace(page, "Studio");
    const showOutput = () => showPanel(page, "Output");
    await showOutput();
    await page.getByRole("combobox", { name: "Output channel" }).selectOption(run!.id);
    await page.getByRole("textbox", { name: "Program input" }).fill("2 + 3");
    await page.getByRole("button", { name: "Send input", exact: true }).click();
    await expect(page.locator(".output-terminal")).toContainText("Result: 5", { timeout: 15000 });
    await page.getByRole("textbox", { name: "Program input" }).fill("8 / 2");
    await page.getByRole("button", { name: "Send input", exact: true }).click();
    await expect(page.locator(".output-terminal")).toContainText("Result: 4");
    await page.getByRole("textbox", { name: "Program input" }).fill("quit");
    await page.getByRole("button", { name: "Send input", exact: true }).click();
    await expect.poll(async () => (await snapshot()).runs.find((r) => r.id === run!.id)?.state).toBe("completed");
    await page.screenshot({ path: path.join(evidence, "calculator-running-result.png") });
    const sentinel = path.join(workspace.root_path, "unrelated.txt");
    await writeFile(sentinel, "Preserve this fixture");
    await openSpace(page, "Chat");
    await page.getByRole("textbox", { name: "Message OLIVE", exact: true }).fill("Change it so it handles division by zero.");
    await page.getByRole("button", { name: "Send message", exact: true }).click();
    const revised = await reviewFixtureActions(answerMessages + 4);
    expect(revised.chat.messages.at(-1)?.content).toContain("checks passed");
    expect(await readFile(sentinel, "utf8")).toBe("Preserve this fixture");
    const trace = await page.evaluate((chat_id) => window.olive.call("interaction.inspect", { chat_id }), created.chat.id);
    await openSpace(page, "Studio");
    // Manual Run is an explicit UI action on the same saved workspace.
    await page.getByRole("button", { name: "Run", exact: true }).click();
    await showOutput();
    await expect.poll(async () => (await snapshot()).runs.some((r) => r.id !== run!.id && r.state === "running")).toBe(true);
    const secondRun = (await snapshot()).runs.find((r) => r.id !== run!.id && r.state === "running")!;
    await page.getByRole("combobox", { name: "Output channel" }).selectOption(secondRun.id);
    await page.getByRole("textbox", { name: "Program input" }).fill("9 / 0");
    await page.getByRole("button", { name: "Send input", exact: true }).click();
    await expect(page.locator(".output-terminal")).toContainText(/zero/i);
    await page.getByRole("textbox", { name: "Program input" }).fill("quit");
    await page.getByRole("button", { name: "Send input", exact: true }).click();
    await page.screenshot({ path: path.join(evidence, "division-zero.png") });
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1000, 700));
    await page.screenshot({ path: path.join(evidence, "calculator-small.png") });
    await writeFile(path.join(evidence, "result.json"), JSON.stringify({ trace, state: await snapshot() }, null, 2));
    await openSpace(page, "Chat");
    await page.getByRole("textbox", { name: "Message OLIVE", exact: true }).fill("Create a stopwatch project in Studio.");
    await page.getByRole("button", { name: "Send message", exact: true }).click();
    const dialog = page.getByRole("dialog").filter({ has: page.getByRole("heading", { name: "Your approval is needed" }) });
    await expect(dialog).toBeVisible({ timeout: 60000 });
    expect((await snapshot()).approvals[0].tool_name).toBe("studio.new_project");
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(dialog).toBeHidden();
    expect((await snapshot()).workspaces).toHaveLength(1);
    // Finish the Windows acceptance journey in this same real Chat-created
    // workspace. Replace only its synthetic program through Monaco and Save.
    await openSpace(page, "Studio");
    await page.getByRole("treeitem", { name: "main.py", exact: true }).click();
    const editor = page.getByRole("textbox", { name: "Source editor", exact: true });
    await editor.press("Control+a");
    await page.keyboard.insertText('name = input("Enter a word: ")\nprint("Received: " + name)\n');
    await editor.press("Control+s");
    await expect.poll(() => readFile(path.join(workspace.root_path, "main.py"), "utf8")).toContain('Received: ');
    let rejected = 0;
    app.process().stderr?.on("data", chunk => { rejected += (String(chunk).match(/Error occurred in handler for 'olive:call'/g) || []).length; });
    await page.getByRole("button", { name: "Run", exact: true }).click();
    const terminal = page.locator('.terminal-view:not([hidden])');
    await expect(terminal).toContainText("Enter a word:", { timeout: 15000 });
    await terminal.locator('textarea').pressSequentially("level");
    await terminal.locator('textarea').press("Enter");
    await expect(terminal).toContainText("Received: level");
    await openSpace(page, "OLIVE GO");
    const address = fixtureServer.address() as { port: number };
    const url = `http://127.0.0.1:${address.port}/`;
    await page.locator('.go-ntp input').fill(url);
    await page.locator('.go-ntp input').press("Enter");
    await expect.poll(() => app.evaluate(async ({ webContents }) => {
      const view = webContents.getAllWebContents().find(view => view.getURL().startsWith('http://127.0.0.1:'));
      return view && !view.isLoading() ? view.executeJavaScript('document.body.innerText') : '';
    })).toContain("OLIVE baseline browser fixture");
    for (const feature of ["Studio", "Mail", "Tasks", "Agent", "Chat"])
      await openSpace(page, feature);
    expect(rejected).toBe(0);
    await expect(page.getByRole("textbox", { name: "Message OLIVE", exact: true })).toBeVisible();
    const children = spawnSync(path.join(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"), ['-c',
      'import psutil,json,sys; print(json.dumps([(p.pid,p.create_time()) for p in psutil.Process(int(sys.argv[1])).children(recursive=True)]))',
      String(app.process().pid)], { encoding: 'utf8', windowsHide: true });
    expect(children.status, children.stderr).toBe(0);
    await app.close(); closed = true;
    await expect.poll(() => spawnSync(path.join(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"), ['-c',
      'import psutil,json,sys\nlive=[]\nfor pid,created in json.loads(sys.argv[1]):\n try:\n  p=psutil.Process(pid)\n  if p.create_time()==created: live.append(pid)\n except psutil.NoSuchProcess: pass\nprint(len(live))',
      children.stdout.trim()], { encoding: 'utf8', windowsHide: true }).stdout.trim(), { timeout: 15000 }).toBe('0');
  } finally {
    if (!closed) await app.close();
    fixtureServer.closeAllConnections();
    await new Promise<void>(resolve => fixtureServer.close(() => resolve()));
  }
});
