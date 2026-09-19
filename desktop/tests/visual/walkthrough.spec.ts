import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { record } from "../e2e/recording";
import { openSpace, mainNav, openHistory } from "../e2e/shell";

// A design tour of the redesigned OLIVE, recorded to an mp4. It only shows the
// new composition (shell, tabs, launcher, pages) — no builds, tests or debug.
test("design walkthrough recording", async () => {
  test.setTimeout(360000);
  const root = path.resolve("..");
  const evidence = path.resolve(path.join(root, "artifacts/ui-review/redesign", "walkthrough"));
  await mkdir(evidence, { recursive: true });
  const profile = await mkdtemp(path.join(tmpdir(), "olive-walkthrough-"));
  const seed = spawnSync(
    path.join(root, ".venv/Scripts/python.exe"),
    [path.join(root, "scripts/seed_visual_fixture.py"), profile],
    { cwd: root, encoding: "utf8", windowsHide: true },
  );
  expect(seed.status, seed.stderr).toBe(0);
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: { ...process.env, OLIVE_DATA_DIR: profile, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1" },
  });
  const errors: string[] = [];
  try {
    const page = await app.firstWindow();
    page.setDefaultTimeout(30000);
    page.on("pageerror", (error) => errors.push(error.message));
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setContentSize(1440, 900));

    // A caption banner injected into the page so the tour narrates itself.
    await page.addStyleTag({
      content: `#olive-tour{position:fixed;left:0;right:0;bottom:0;z-index:99999;
        background:linear-gradient(180deg,rgba(7,12,20,0),rgba(7,12,20,.92));
        color:#eaf1fb;font:500 15px/1.4 "Segoe UI Variable","Segoe UI",system-ui;
        padding:34px 26px 16px;pointer-events:none;opacity:0;transition:opacity .3s ease}
        #olive-tour.show{opacity:1}
        #olive-tour b{display:block;font-size:19px;font-weight:650;letter-spacing:.2px}
        #olive-tour span{color:#9db4d0}`,
    });
    await page.evaluate(() => {
      const el = document.createElement("div");
      el.id = "olive-tour";
      el.innerHTML = "<b></b><span></span>";
      document.body.appendChild(el);
    });
    const say = async (title: string, sub: string, hold = 2600) => {
      await page.evaluate(
        ([t, s]) => {
          const el = document.getElementById("olive-tour")!;
          el.querySelector("b")!.textContent = t;
          el.querySelector("span")!.textContent = s;
          el.classList.add("show");
        },
        [title, sub],
      );
      await page.waitForTimeout(hold);
    };
    const clearCaption = () =>
      page.evaluate(() => document.getElementById("olive-tour")?.classList.remove("show"));

    const finish = await record(page, evidence, "olive-design-walkthrough.mp4");

    // 1. Welcome (protected startup experience, unchanged).
    await expect(page.getByText(/Ready to open/)).toBeVisible({ timeout: 60000 });
    await say("OLIVE", "A local-first personal AI desktop app — the redesigned experience.", 3000);
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await expect(page.locator("main.home")).toBeVisible();

    // 2. Home — the workbench.
    await say("Home", "A compact top bar is the whole shell. No permanent side rail.", 3400);
    await say("Open now · Recent · Right now", "Home is built around the work you actually have open.", 3200);
    await clearCaption();
    await page.waitForTimeout(600);

    // 3. Spaces launcher (on demand).
    await mainNav(page).getByRole("button", { name: "All Spaces", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Spaces" })).toBeVisible();
    await say("Spaces", "Everything OLIVE can do opens on demand — grouped, searchable, not a rail.", 3600);
    await page.getByRole("dialog", { name: "Spaces" }).getByRole("button", { name: "Chat", exact: true }).click();

    // 4. Chat — conversation-first, history on demand.
    await expect(page.locator(".messages")).toBeVisible();
    await say("Chat", "Conversation-first: the thread fills the width.", 3000);
    await openHistory(page);
    await say("History on demand", "Conversations open as a panel when you want them, then step aside.", 3200);
    await page.getByRole("button", { name: "Close conversation history", exact: true }).click();
    await page.waitForTimeout(500);

    // 5. Studio — editor-first IDE.
    await openSpace(page, "Studio");
    await page.getByRole("button", { name: "Fixture · local Python project" }).first().click();
    await page.getByRole("treeitem", { name: "main.py", exact: true }).click();
    await expect(page.locator(".monaco-editor").first()).toBeVisible({ timeout: 30000 });
    await say("Studio", "An editor-first IDE: Files and solution, the editor, and an on-demand tool dock.", 3600);
    await page.getByRole("button", { name: "Show Terminal", exact: true }).click();
    await say("Bottom dock", "Terminal, Problems, Tests, Output, Git and Debug — opened on request, never empty.", 3400);
    await page.getByRole("button", { name: "Show Problems", exact: true }).click();
    await page.waitForTimeout(1500);
    await page.locator("button.assistant-toggle").click();
    await say("Ask OLIVE", "The assistant is opened on request — resizable, closable, pinnable.", 3200);
    await page.locator("button.assistant-toggle").click();
    await clearCaption();
    await page.waitForTimeout(500);

    // 6. Work tabs — open a few spaces to show the workbench tabs.
    for (const name of ["Mail", "Calendar", "Research"]) {
      await mainNav(page).getByRole("button", { name: "All Spaces", exact: true }).click();
      await page.getByRole("dialog", { name: "Spaces" }).getByRole("button", { name, exact: true }).click();
      await page.waitForTimeout(700);
    }
    await mainNav(page).getByRole("button", { name: "Home", exact: true }).click();
    await say("Open work as tabs", "Every conversation, project and workspace is a tab with a stable identity.", 3600);

    // 7. Mail — two-pane reading + full-width compose.
    await openSpace(page, "Mail");
    await expect(page.locator(".mail-list")).toBeVisible();
    await say("Mail", "Two panes for reading; the detail pane appears only on selection.", 3200);
    const firstMessage = page.locator(".mail-list-item").first();
    if (await firstMessage.count()) {
      await firstMessage.click();
      await page.waitForTimeout(1800);
    }
    await page.getByRole("button", { name: "Compose", exact: true }).click();
    await expect(page.locator(".mail-layout.composing")).toBeVisible();
    await say("Full-width compose", "Composing steps the list aside and keeps folders for navigation.", 3400);
    await clearCaption();

    // 8. Light theme + a final look at Home.
    await mainNav(page).getByRole("button", { name: "Home", exact: true }).click();
    await page.getByRole("button", { name: "OLIVE activity", exact: true }).click();
    await page.getByRole("button", { name: "Toggle theme", exact: true }).click();
    await page.keyboard.press("Escape");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await say("One coherent art direction", "Dark or light, the same distinctive, futuristic identity.", 3400);
    await mainNav(page).getByRole("button", { name: "All Spaces", exact: true }).click();
    await page.waitForTimeout(2400);
    await page.keyboard.press("Escape");
    await say("OLIVE", "The redesigned, structurally different experience — all on your device.", 3200);
    await clearCaption();
    await page.waitForTimeout(700);

    const result = await finish();
    console.log("RECORDING: " + JSON.stringify(result));
    expect(result.recorded, JSON.stringify(result)).toBe(true);
  } finally {
    await app.close();
  }
  expect(errors).toEqual([]);
});
