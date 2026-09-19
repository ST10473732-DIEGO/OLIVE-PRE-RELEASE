import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { openSpace, mainNav } from "./shell";

test("LIVE LOCAL five presets, simplified navigation and public research in Chat", async () => {
  test.skip(process.env.OLIVE_LIVE_AI !== "1", "Requires installed local models and public source retrieval");
  test.setTimeout(360000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-presets-ui-"));
  const evidence = path.resolve("../artifacts/core/functionality/presets");
  await mkdir(evidence, { recursive: true });
  const app = await electron.launch({ args: [path.resolve(".")], env: { ...process.env, OLIVE_DATA_DIR: profile } });
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", {name: "Enter OLIVE", exact: true}).click();
    await expect(mainNav(page).getByRole("button", {name: "Profile", exact: true})).toHaveCount(0);
    await expect(mainNav(page).getByRole("button", {name: "Contacts", exact: true})).toHaveCount(0);
    await expect(mainNav(page).getByRole("button", {name: "Research", exact: true})).toHaveCount(0);
    await openSpace(page, "Chat");
    const picker = page.getByRole("combobox", {name: "OLIVE preset"});
    await expect(picker).toHaveValue("normal");
    await expect(picker.locator("option")).toHaveCount(5);
    await picker.selectOption("fast");
    await page.getByRole("textbox", {name: "Message OLIVE"}).fill("Write a Python function that validates an email address.");
    await page.getByRole("button", {name: "Send message", exact: true}).click();
    await expect(page.locator(".message-assistant pre")).toBeVisible({timeout: 90000});
    await expect(picker).toBeEnabled({timeout: 90000});
    const s = await page.evaluate(() => window.olive.call("runtime.snapshot", {})) as {workspaces: unknown[]; runs: unknown[]; chat: {id: string}};
    expect(s.workspaces).toHaveLength(0); expect(s.runs).toHaveLength(0);
    await picker.selectOption("reimagine");
    await expect(picker).toHaveValue("reimagine");
    await expect(picker.locator("option:checked")).toContainText("generation needs setup");
    await picker.selectOption("normal");
    await page.getByRole("combobox", {name: "Research mode"}).selectOption("Quick");
    await page.getByRole("textbox", {name: "Message OLIVE"}).fill("Using https://docs.python.org/3/library/math.html, what does math.sqrt(9) return? Cite the documentation.");
    await page.getByRole("button", {name: "Send message", exact: true}).click();
    await expect(page.locator(".research-evidence summary").first()).toBeVisible({timeout: 30000});
    // Delegated review applies only to this public, read-only fixture question.
    // Never approve downloads, persistence, messaging or arbitrary tool calls.
    const deadline = Date.now() + 210000;
    let reviewed = 0;
    while (Date.now() < deadline) {
      const state = await page.evaluate(() => window.olive.call("runtime.snapshot", {})) as {
        activity: {items: unknown[]}; approvals: {tool_name: string; arguments: Record<string, unknown>}[];
      };
      const approval = state.approvals[0];
      if (approval) {
        expect(++reviewed).toBeLessThanOrEqual(15);
        expect(["web.search", "web.open"]).toContain(approval.tool_name);
        if (approval.tool_name === "web.search") {
          expect(String(approval.arguments.query)).toMatch(/python|sqrt/i);
          expect(String(approval.arguments.query).length).toBeLessThan(200);
        } else {
          const url = new URL(String(approval.arguments.url));
          expect(url.protocol).toBe("https:");
          expect(["docs.python.org", "www.python.org", "python.org"]).toContain(url.hostname);
        }
        await page.getByRole("dialog").getByRole("button", {name: "Approve this action", exact: true}).click();
      }
      if (!state.activity.items.length && !approval) break;
      await page.waitForTimeout(250);
    }
    await expect(picker).toBeEnabled({timeout: 210000});
    const result = await page.evaluate(async () => {
      const state = await window.olive.call("runtime.snapshot", {}) as {chat: {research_session_ids: string[]}};
      const id = state.chat.research_session_ids.at(-1)!;
      return window.olive.call("research.get", {session_id: id});
    }) as {status: string; sources: {url: string; status: string}[]; evidence: unknown[]; final_report: string; findings: {text: string; kind: string}[]};
    await writeFile(path.join(evidence, "research-result.json"), JSON.stringify(result, null, 2));
    expect(result.sources.some(source => source.url.startsWith("https://docs.python.org/"))).toBeTruthy();
    expect(result.evidence.length).toBeGreaterThan(0);
    expect(result.status).toBe("completed");
    expect(result.findings.some(finding => finding.text.includes("3.0") && finding.kind === "inference")).toBeTruthy();
    await expect(page.locator(".message-assistant").last()).toContainText("3.0", {timeout: 15000});
    await expect(page.locator(".message-assistant").last()).toContainText("Inference");
    await page.screenshot({path: path.join(evidence, "chat-research.png")});
    await page.getByRole("button", {name: "Saved research & evidence", exact: true}).click();
    await expect(page.getByRole("dialog", {name: "Research history"})).toBeVisible();
    await page.getByRole("dialog", {name: "Research history"}).getByRole("button", {name: "Close", exact: true}).click();
    await app.browserWindow(app.windows()[0]).then(win => win.evaluate(w => w.setSize(1024, 720)));
    await page.screenshot({path: path.join(evidence, "chat-small.png")});
    await openSpace(page, "Settings");
    await page.getByRole("button", {name: "General", exact: true}).click();
    await expect(page.getByRole("textbox", {name: "Preferred name"})).toHaveValue("Diego");
  } finally { await app.close(); }
});
