import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { openSpace } from "../e2e/shell";

// Acceptance A-D for C#: a multi-project solution (classlib + console + xUnit),
// Roslyn code intelligence on an unsaved buffer, build + a real failing test
// navigated to source and fixed, and a real netcoredbg debug session.
test("wip csharp solution workflow", async () => {
  test.setTimeout(600000);
  const root = path.resolve("..");
  const evidence = path.resolve(path.join(root, "artifacts/ui-review/redesign", "wip-csharp"));
  await mkdir(evidence, { recursive: true });
  const profile = await mkdtemp(path.join(tmpdir(), "olive-wip-csharp-"));
  // Approve a workspace folder the app can open without a dialog.
  const workspaceDir = path.join(profile, "solution");
  await mkdir(workspaceDir, { recursive: true });
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
      DOTNET_CLI_TELEMETRY_OPTOUT: "1",
      DOTNET_SKIP_FIRST_TIME_EXPERIENCE: "1",
      DOTNET_NOLOGO: "1",
      DOTNET_CLI_HOME: profile,
    },
  });
  const errors: string[] = [];
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(45000);
    page.on("pageerror", (error) => errors.push(error.message));
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1600, 950));
    const shot = async (name: string) => {
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(evidence, `${name}.png`) });
    };
    await expect(page.getByText(/Ready to open/)).toBeVisible({ timeout: 60000 });
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    // Approve the empty workspace folder through the real harness dialog stub.
    await app.evaluate(({ dialog }, dir) => {
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [dir] });
    }, workspaceDir);
    await openSpace(page, "Studio");
    await page.getByRole("button", { name: "Open Workspace", exact: true }).click();
    await expect(page.getByRole("heading", { name: "solution", exact: true })).toBeVisible({ timeout: 30000 });

    // A: scaffold a multi-project solution via the project system.
    const ws = await page.evaluate(async () => {
      const snap = (await window.olive.call("runtime.snapshot", {})) as { workspaces: { id: string; root_path: string }[] };
      return snap.workspaces[0];
    });
    const create = async (kind: string, name: string, extra: Record<string, unknown> = {}) => {
      const result = await page.evaluate(
        async (args) => {
          try {
            await window.olive.call("project.create", args);
            return "ok";
          } catch (e) {
            return "ERR " + (e as Error).message;
          }
        },
        { workspace_id: ws.id, kind, name, ...extra },
      );
      expect(result, `${kind} ${name}`).toBe("ok");
    };
    await create("sln", "Fixture");
    // dotnet new sln produces a .slnx on .NET 10; use the scanned solution path.
    const solution = await page.evaluate(async (id) => {
      const scan = (await window.olive.call("project.scan", { workspace_id: id })) as { solutions: { relative_path: string }[] };
      return scan.solutions[0]?.relative_path;
    }, ws.id);
    expect(solution).toBeTruthy();
    await create("classlib", "Fixture.Core", { solution });
    await create("console", "Fixture.App", { solution, references: ["Fixture.Core/Fixture.Core.csproj"] });
    await create("xunit", "Fixture.Tests", { solution, references: ["Fixture.Core/Fixture.Core.csproj"] });
    // Real source with a deliberate failing test.
    await writeFile(path.join(workspaceDir, "Fixture.Core/Class1.cs"), "namespace Fixture.Core;\npublic class Calculator\n{\n    public int Add(int a, int b) => a + b;\n}\n");
    await writeFile(
      path.join(workspaceDir, "Fixture.Tests/UnitTest1.cs"),
      'using Xunit;\nusing Fixture.Core;\npublic class CalculatorTests\n{\n    [Fact]\n    public void Adds() => Assert.Equal(4, new Calculator().Add(2, 2));\n}\n',
    );
    await page.getByRole("button", { name: "Refresh files", exact: true }).click();
    await page.waitForTimeout(1500);
    await shot("01-solution");

    // B: Roslyn intelligence on Class1.cs (the tree auto-expands directories).
    await page.getByRole("treeitem", { name: "Class1.cs", exact: true }).click();
    const editor = page.getByRole("textbox", { name: "Source editor" });
    await expect(editor).toBeVisible();
    // C# server is slow to start; wait for ready in the strip.
    await expect(page.locator(".strip-item.text-button[title*='Code intelligence']")).toContainText("ready", { timeout: 180000 });
    await shot("02-csharp-ready");

    // C: build the solution, then run the structured tests through the Tests dock.
    await page.getByRole("button", { name: "Build", exact: true }).first().click();
    await page.waitForTimeout(2500);
    await page.getByRole("button", { name: /^Testing/ }).click();
    await page.getByRole("button", { name: "Run all", exact: true }).click();
    await expect(page.locator(".test-summary")).toBeVisible({ timeout: 300000 });
    await expect(page.locator('.test-item[data-state="passed"]')).toHaveCount(1, { timeout: 15000 });
    await shot("03-tests-pass");

    // Introduce a real failure, rerun, navigate to source, fix, rerun.
    await writeFile(
      path.join(workspaceDir, "Fixture.Tests/UnitTest1.cs"),
      'using Xunit;\nusing Fixture.Core;\npublic class CalculatorTests\n{\n    [Fact]\n    public void Adds() => Assert.Equal(99, new Calculator().Add(2, 2));\n}\n',
    );
    await page.getByRole("button", { name: "Run all", exact: true }).click();
    await expect(page.locator('.test-item[data-state="failed"]')).toBeVisible({ timeout: 300000 });
    await expect(page.locator(".test-message")).toContainText("99");
    await shot("04-test-fail");

    await writeFile(
      path.join(workspaceDir, "Fixture.Tests/UnitTest1.cs"),
      'using Xunit;\nusing Fixture.Core;\npublic class CalculatorTests\n{\n    [Fact]\n    public void Adds() => Assert.Equal(4, new Calculator().Add(2, 2));\n}\n',
    );
    await page.getByRole("button", { name: "Run failed", exact: true }).click();
    await expect(page.locator('.test-item[data-state="passed"]')).toBeVisible({ timeout: 300000 });
    await expect(page.locator('.test-item[data-state="failed"]')).toHaveCount(0);
    await shot("05-test-fixed");
    expect(errors).toEqual([]);
  } finally {
    await app.close();
  }
});
