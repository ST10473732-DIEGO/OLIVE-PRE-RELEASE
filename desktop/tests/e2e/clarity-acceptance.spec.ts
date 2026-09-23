import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { openSpace, showPanel } from "./shell";
import { mkdtemp, mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";

// The clarity brief's acceptance journey A-O, run through the real Electron and
// Python path with an isolated profile and temporary projects. Nothing here
// touches a real development folder, a real account or a real message.
test("clarity acceptance journey: navigation, two independent projects, run, terminals, close and restart", async () => {
  test.setTimeout(900000);
  const root = path.resolve("..");
  const evidence = path.join(root, "artifacts/ui-review/clarity/acceptance");
  await mkdir(evidence, { recursive: true });
  const profile = await mkdtemp(path.join(tmpdir(), "olive-acceptance-"));
  const projects = path.join(profile, "projects");
  await mkdir(projects, { recursive: true });
  const environment = {
    ...process.env,
    OLIVE_DATA_DIR: profile,
    // No model is loaded: the journey must read honestly while AI is offline.
    OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
    DOTNET_CLI_TELEMETRY_OPTOUT: "1",
    DOTNET_NOLOGO: "1",
    DOTNET_CLI_HOME: profile,
  };
  const record: Record<string, unknown> = { profile, projects };
  let app = await electron.launch({ args: [path.resolve(".")], env: environment });
  const errors: string[] = [];
  try {
    let page = await app.firstWindow();
    page.setDefaultTimeout(45000);
    page.on("pageerror", (e) => errors.push(e.message));
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setContentSize(1600, 950),
    );
    // Every wizard and picker resolves to the temporary projects folder.
    await app.evaluate(({ dialog }, dir) => {
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [dir] });
    }, projects);
    const shot = async (name: string) => {
      await page.waitForTimeout(250);
      await page.screenshot({ path: path.join(evidence, `${name}.png`) });
    };
    const nav = () => page.getByRole("navigation", { name: "Main navigation" });
    const go = async (label: string) =>
      openSpace(page, label);
    const selector = () => page.getByRole("button", { name: /^Workspace: / });
    const switchTo = async (title: string) => {
      await selector().click();
      await page
        .getByRole("dialog", { name: "Workspaces" })
        .getByRole("button", { name: title, exact: true })
        .click();
      await expect(
        page.getByRole("button", { name: new RegExp(`^Workspace: ${title}`) }),
      ).toBeVisible();
    };
    const enter = async () => {
      const button = page.getByRole("button", { name: "Enter OLIVE", exact: true });
      await expect(button).toBeVisible({ timeout: 90000 });
      await button.click();
      await expect(page.locator("main.home")).toBeVisible();
    };

    // ---- A: the redesigned entrance leads to Home ----------------------
    await expect(page.locator(".welcome")).toBeVisible({ timeout: 90000 });
    await expect(page.locator(".welcome-core")).toBeVisible();
    await expect(page.getByText(/Ready to open/)).toBeVisible();
    await shot("A-welcome");
    await enter();
    await shot("A-home");

    // ---- B: every feature is found by a visible label, no commands -----
    for (const label of [
      "Studio", "Mail", "Calendar", "OLIVE GO", "Knowledge", "Settings",
      "Chat", "Agent", "Projects", "Memory", "Tasks", "Reminders",
    ])
      await expect(nav().getByRole("button", { name: label, exact: true })).toBeVisible();
    for (const label of ["Mail", "Calendar", "OLIVE GO", "Knowledge", "Settings"]) {
      await go(label);
      await expect(page.getByRole("heading", {name:label,exact:true}).first()).toBeVisible();
    }
    await go("Studio");
    await shot("B-studio-empty");

    // ---- C / L: the wizard reports real readiness before creating ------
    const openWizard = async () => {
      await page.getByRole("button", { name: "New project", exact: true }).first().click();
      await page.getByRole("dialog", { name: "New project" }).waitFor();
      // Discovery is bounded; the cards appear without a re-probe per render.
      await expect(page.locator(".language-card").first()).toBeVisible({ timeout: 120000 });
    };
    await openWizard();
    await shot("L-languages");
    const cards = page.locator(".language-card");
    const readiness: Record<string, { availability: string; detail: string; enabled: boolean }> = {};
    for (const card of await cards.all()) {
      const id = (await card.getAttribute("data-language")) || "";
      readiness[id] = {
        availability: (await card.getAttribute("data-availability")) || "",
        detail: (await card.locator(".readiness").innerText()).trim(),
        enabled: await card.isEnabled(),
      };
    }
    record.language_readiness = readiness;
    // A language may only be chosen when its own toolchain and template are
    // genuinely present; a missing toolchain never enables creation.
    for (const [id, item] of Object.entries(readiness)) {
      expect(item.detail, id).not.toBe("");
      expect(item.enabled, `${id} enabled state must follow its availability`).toBe(
        item.availability === "ready",
      );
    }
    expect(readiness.csharp.availability, "the .NET SDK is installed here").toBe("ready");
    expect(readiness.python.availability).toBe("ready");

    // Templates are filtered to the chosen language, from real metadata.
    await page.locator('.language-card[data-language="python"]').click();
    const pythonTemplates = (await page.locator(".template-card strong").allInnerTexts()).sort();
    await page.locator('.language-card[data-language="csharp"]').click();
    const dotnetTemplates = (await page.locator(".template-card strong").allInnerTexts()).sort();
    record.templates = { python: pythonTemplates, csharp: dotnetTemplates };
    expect(pythonTemplates).not.toEqual(dotnetTemplates);
    expect(dotnetTemplates.join(" ")).toContain("Console");

    // ---- C: create project A -------------------------------------------
    const finish = async (name: string) => {
      await page.getByLabel("Project name", { exact: true }).fill(name);
      await page.getByRole("button", { name: "Browse", exact: true }).click();
      // The exact operation is visible before anything is created.
      await expect(page.getByText(path.join(projects, name), { exact: false })).toBeVisible();
      await page.getByRole("button", { name: "Create project", exact: true }).click();
      await expect(page.locator(".wizard-done p[role=status]")).toContainText("Created", {
        timeout: 300000,
      });
      await page.getByRole("button", { name: "Done", exact: true }).click();
      await expect(
        page.getByRole("button", { name: new RegExp(`^Workspace: ${name}`) }),
      ).toBeVisible({ timeout: 30000 });
    };
    await finish("ProjectA");
    await shot("C-project-a");
    await page.getByRole("treeitem", { name: "Program.cs", exact: true }).click();
    const editor = page.getByRole("textbox", { name: "Source editor" });
    await expect(editor).toBeVisible();
    await editor.press("Control+End");
    await editor.press("Enter");
    await editor.pressSequentially("// unsaved marker in A");
    await expect(page.locator(".file-tab .dirty")).toBeVisible();

    // ---- K: add a project inside A's own solution ------------------------
    await page
      .getByRole("button", { name: "Add project to this solution", exact: true })
      .first()
      .click();
    const addSheet = page.getByRole("dialog", { name: "Add project to this solution" });
    await addSheet.getByRole("radio", { name: /Class library/ }).click();
    await addSheet.getByLabel("Project name", { exact: true }).fill("ProjectA.Core");
    await addSheet.getByRole("button", { name: "Create", exact: true }).click();
    await expect(addSheet.getByText(/^Created /)).toBeVisible({ timeout: 300000 });
    await addSheet.getByRole("button", { name: "Done", exact: true }).click();
    // It landed inside A, not beside it, and the unsaved buffer survived.
    expect((await readdir(path.join(projects, "ProjectA"))).sort()).toContain("ProjectA.Core");
    expect((await readdir(projects)).sort()).toEqual(["ProjectA"]);
    await expect(page.locator(".file-tab .dirty")).toBeVisible();
    await shot("K-added-to-solution");

    // ---- D + E: a second project while A stays open ---------------------
    await openWizard();
    await page.locator('.language-card[data-language="python"]').click();
    await finish("ProjectB");
    expect((await readdir(projects)).sort()).toEqual(["ProjectA", "ProjectB"]);
    await shot("E-project-b");

    // ---- F: run B and read its real output ------------------------------
    await page.getByRole("button", { name: "Run", exact: true }).click();
    const runs = () =>
      page.evaluate(
        async () =>
          (
            (await window.olive.call("runtime.snapshot", {})) as {
              runs: { state: string; stdout: string; stderr: string; exit_code: number }[];
            }
          ).runs,
      );
    await expect
      .poll(async () => (await runs()).at(-1)?.state, { timeout: 120000 })
      .toBe("completed");
    const run = (await runs()).at(-1)!;
    record.run = run;
    expect(run, run.stderr).toMatchObject({ state: "completed", exit_code: 0 });
    expect(run.stdout).toContain("Hello, OLIVE!");
    await showPanel(page, "Output");
    await expect.poll(() => page.locator(".output-terminal").innerText(), { timeout: 60000 })
      .toContain("Hello, OLIVE!");
    await shot("F-run-output");

    // ---- I: a terminal belongs to the workspace it was opened in --------
    const terminalTabs = () =>
      page.getByRole("tablist", { name: "Terminal sessions" }).getByRole("tab");
    const showTerminal = () => showPanel(page, "Terminal");
    await showTerminal();
    await page.getByRole("button", { name: "New terminal", exact: true }).click();
    await page.getByRole("button", { name: "Open PowerShell", exact: true }).click();
    await expect(terminalTabs()).toHaveCount(2, { timeout: 60000 });
    await shot("I-terminal-in-b");
    await switchTo("ProjectA");
    await showTerminal();
    // A has its own (empty) terminal list; B's session is not shown or reused.
    await expect(page.locator(".dock-empty")).toBeVisible();
    await expect(terminalTabs()).toHaveCount(0);
    await shot("I-terminal-in-a");

    // ---- G: A kept its unsaved buffer, cursor and open file -------------
    await expect(page.locator(".monaco-editor .view-lines")).toContainText("unsaved marker in A");
    await expect(page.locator(".file-tab .dirty")).toBeVisible();

    // ---- H: B is still its own session, with its terminal still open ----
    await switchTo("ProjectB");
    await showTerminal();
    await expect(terminalTabs()).toHaveCount(2);
    // B's own output channel still holds B's run, unchanged by the visit to A.
    await showPanel(page, "Output");
    await expect
      .poll(() => page.locator(".output-terminal").innerText(), { timeout: 30000 })
      .toContain("Hello, OLIVE!");
    await shot("H-back-in-b");

    // ---- J: cancelling a wizard changes nothing -------------------------
    await openWizard();
    await page.locator('.language-card[data-language="python"]').click();
    await page.getByLabel("Project name", { exact: true }).fill("Cancelled");
    await page
      .getByRole("dialog", { name: "New project" })
      .getByRole("button", { name: "Cancel", exact: true })
      .click();
    expect((await readdir(projects)).sort()).toEqual(["ProjectA", "ProjectB"]);
    await expect(page.getByRole("button", { name: /^Workspace: ProjectB/ })).toBeVisible();

    // ---- M: closing a dirty workspace offers Save / Discard / Cancel ----
    const requestClose = async () => {
      await selector().click();
      await page
        .getByRole("dialog", { name: "Workspaces" })
        .getByRole("button", { name: "Close ProjectA", exact: true })
        .click();
      await expect(page.getByRole("dialog", { name: "Close workspace" })).toBeVisible();
    };
    await requestClose();
    await expect(page.locator(".close-summary")).toContainText("1 unsaved file");
    await shot("M-close-summary");
    await page
      .getByRole("dialog", { name: "Close workspace" })
      .getByRole("button", { name: "Cancel", exact: true })
      .click();
    // Cancel changed nothing: A is still open and still unsaved.
    await switchTo("ProjectA");
    await expect(page.locator(".file-tab .dirty")).toBeVisible();
    expect(await readFile(path.join(projects, "ProjectA/Program.cs"), "utf8")).not.toContain(
      "unsaved marker in A",
    );
    await switchTo("ProjectB");
    await requestClose();
    await page
      .getByRole("dialog", { name: "Close workspace" })
      .getByRole("button", { name: "Save and close", exact: true })
      .click();
    await expect
      .poll(() => readFile(path.join(projects, "ProjectA/Program.cs"), "utf8"))
      .toContain("unsaved marker in A");
    await selector().click();
    const sheet = page.getByRole("dialog", { name: "Workspaces" });
    // Only B is open now; A stayed on disk and is offered as an approved folder.
    await expect(sheet.locator(".workspace-row")).toHaveCount(1);
    await expect(sheet.getByRole("button", { name: "ProjectB", exact: true })).toBeVisible();
    await expect(sheet.getByText("Other approved folders")).toBeVisible();
    await page.keyboard.press("Escape");
    await shot("M-after-save-and-close");

    // ---- O: the other features still work on synthetic local data -------
    const permissionsBefore = await page.evaluate(() =>
      window.olive.call("data.permissions", {}),
    );
    await go("Mail");
    await expect(page.getByRole("button", { name: "Compose", exact: true })).toBeVisible();
    const draft = (await page.evaluate(() =>
      window.olive.call("mail.save_draft", {
        body: { to: [], subject: "Synthetic acceptance draft", text: "Local only." },
      }),
    )) as { id: string };
    expect(
      ((await page.evaluate(
        (id) => window.olive.call("mail.get", { record_id: id }),
        draft.id,
      )) as { subject: string }).subject,
    ).toBe("Synthetic acceptance draft");
    await go("Calendar");
    await expect(page.getByRole("button", { name: "Agenda", exact: true })).toBeVisible();
    await go("Chat");
    await expect(page.getByRole("textbox", { name: "Message OLIVE", exact: true })).toBeVisible();
    await go("Research");
    await expect(page.getByRole("dialog", {name:"Research history"})).toBeVisible();
    expect(await page.evaluate(() => window.olive.call("data.permissions", {}))).toEqual(
      permissionsBefore,
    );
    await shot("O-features");

    // ---- N: restart restores a safe state and replays nothing -----------
    await app.close();
    app = await electron.launch({ args: [path.resolve(".")], env: environment });
    page = await app.firstWindow();
    page.setDefaultTimeout(45000);
    page.on("pageerror", (e) => errors.push(e.message));
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setContentSize(1600, 950),
    );
    await enter();
    await go("Studio");
    await expect(page.getByRole("button", { name: /^Workspace: ProjectB/ })).toBeVisible({
      timeout: 60000,
    });
    const after = (await page.evaluate(() => window.olive.call("runtime.snapshot", {}))) as {
      runs: { state: string }[];
    };
    // Nothing restarted itself: no program, no terminal, no debug session.
    expect(after.runs.filter((r) => ["starting", "running"].includes(r.state))).toEqual([]);
    await showTerminal();
    await expect(page.locator(".dock-empty")).toBeVisible();
    await expect(terminalTabs()).toHaveCount(0);
    expect(await readFile(path.join(projects, "ProjectA/Program.cs"), "utf8")).toContain(
      "unsaved marker in A",
    );
    await shot("N-after-restart");
    record.errors = errors;
    await writeFile(path.join(evidence, "journey.json"), JSON.stringify(record, null, 2));
    expect(errors).toEqual([]);
  } finally {
    await app.close();
  }
});

// Acceptance L: the missing-toolchain state, proven by removing the tooling
// from the environment rather than by pretending. Nothing is installed here.
test("a language without installed tooling is reported honestly and cannot be created", async () => {
  test.setTimeout(300000);
  const root = path.resolve("..");
  const evidence = path.join(root, "artifacts/ui-review/clarity/acceptance");
  await mkdir(evidence, { recursive: true });
  const profile = await mkdtemp(path.join(tmpdir(), "olive-no-toolchain-"));
  const system = process.env.SystemRoot || "C:\Windows";
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
      // Only the Windows system folders: no Node, no JDK, no .NET SDK.
      PATH: `${path.join(system, "system32")};${system}`,
      Path: `${path.join(system, "system32")};${system}`,
      JAVA_HOME: "",
    },
  });
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(45000);
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await page.getByRole("navigation", { name: "Main navigation" })
      .getByRole("button", { name: "Studio", exact: true }).click();
    await page.getByRole("button", { name: "New project", exact: true }).first().click();
    await expect(page.locator(".language-card").first()).toBeVisible({ timeout: 120000 });
    const missing: Record<string, string> = {};
    for (const card of await page.locator(".language-card").all()) {
      const id = (await card.getAttribute("data-language")) || "";
      const availability = (await card.getAttribute("data-availability")) || "";
      if (availability === "ready") continue;
      missing[id] = (await card.locator(".readiness").innerText()).trim();
      // A language OLIVE cannot actually create is never selectable.
      expect(await card.isEnabled(), `${id} must not be selectable`).toBe(false);
      expect((await card.getAttribute("title")) || "").toMatch(/not found|no template|editing/i);
    }
    await writeFile(
      path.join(evidence, "missing-toolchains.json"),
      JSON.stringify({ path: `${path.join(system, "system32")};${system}`, missing }, null, 2),
    );
    // At least Node and the JDK are genuinely absent from this environment.
    expect(Object.keys(missing).length).toBeGreaterThan(0);
    expect(missing.javascript).toBe("Toolchain missing");
    await page.screenshot({ path: path.join(evidence, "L-toolchain-missing.png") });
    // Creation stays blocked: no name field is reachable for a missing language.
    await page.locator('.language-card[data-language="javascript"]').click({ force: true });
    await expect(page.getByRole("button", { name: "Create project", exact: true })).toBeDisabled();
  } finally {
    await app.close();
  }
});

// Language servers, debuggers and terminals are child processes of the
// backend. If OLIVE quits before they stop, they keep running on the machine:
// six orphaned OmniSharp instances is what slowed a whole suite run down.
test("closing OLIVE leaves no language server running", async () => {
  test.setTimeout(600000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-shutdown-"));
  const projects = path.join(profile, "projects");
  await mkdir(projects, { recursive: true });
  // OmniSharp is unambiguous: nothing else on the machine starts it.
  const omnisharp = () =>
    Number(
      spawnSync(path.resolve(process.platform === "win32" ? "../.venv/Scripts/python.exe" : "../.venv/bin/python"), [
        "-c",
        "import psutil; print(sum('omnisharp' in (p.info['name'] or '').lower() for p in psutil.process_iter(['name'])))",
      ], { encoding: "utf8" }).stdout.trim() || "0",
    );
  const baseline = omnisharp();
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
      DOTNET_CLI_TELEMETRY_OPTOUT: "1",
      DOTNET_NOLOGO: "1",
      DOTNET_CLI_HOME: profile,
    },
  });
  let started = baseline;
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(45000);
    await app.evaluate(({ dialog }, dir) => {
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [dir] });
    }, projects);
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await page.getByRole("navigation", { name: "Main navigation" })
      .getByRole("button", { name: "Studio", exact: true }).click();
    await page.getByRole("button", { name: "New project", exact: true }).first().click();
    await expect(page.locator('.language-card[data-language="csharp"]')).toBeEnabled({
      timeout: 120000,
    });
    await page.locator('.language-card[data-language="csharp"]').click();
    await page.getByLabel("Project name", { exact: true }).fill("ShutdownFixture");
    await page.getByRole("button", { name: "Browse", exact: true }).click();
    await page.getByRole("button", { name: "Create project", exact: true }).click();
    await expect(page.locator(".wizard-done p[role=status]")).toContainText("Created", {
      timeout: 300000,
    });
    await page.getByRole("button", { name: "Done", exact: true }).click();
    await page.getByRole("treeitem", { name: "Program.cs", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "Source editor" })).toBeVisible();
    // Wait for the C# language server to actually be up.
    await expect.poll(() => omnisharp(), { timeout: 120000 }).toBeGreaterThan(baseline);
    started = omnisharp();
  } finally {
    await app.close();
  }
  // The backend stops its children as it goes; give the OS a moment to reap.
  await expect
    .poll(() => omnisharp(), { timeout: 30000, intervals: [1000] })
    .toBeLessThanOrEqual(baseline);
  expect(started, "a language server should have been running before the close").toBeGreaterThan(
    baseline,
  );
});
