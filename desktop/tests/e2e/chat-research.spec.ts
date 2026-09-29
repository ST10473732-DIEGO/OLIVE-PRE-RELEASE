import { test, expect, _electron as electron } from "@playwright/test";
import { mkdtemp } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import path from "node:path";
import { openSpace, mainNav } from "./shell";

test("legacy remembered Research view opens Chat after application reload", async () => {
  const profile = await mkdtemp(path.join(tmpdir(), "olive-legacy-research-route-"));
  const app = await electron.launch({chromiumSandbox: true, args: [path.resolve(".")], env: {...process.env, OLIVE_DATA_DIR: profile}});
  try {
    const page = await app.firstWindow();
    await page.evaluate(() => {
      localStorage.setItem("spaceViews", JSON.stringify({chat: "research"}));
      localStorage.setItem("skipWelcome", "true");
    });
    await page.reload();
    // Active route is not persisted or URL-routed: reload always starts Home.
    await expect(page.locator(".shell")).toHaveAttribute("data-route", "home");
    await openSpace(page, "Chat");
    await expect(page.locator(".shell")).toHaveAttribute("data-route", "chat");
    await expect(page.getByRole("textbox", {name: "Message OLIVE", exact: true})).toBeVisible();
    await expect(mainNav(page).getByRole("button", {name: "Research", exact: true})).toHaveCount(0);
  } finally { await app.close(); }
});

test("LIVE Chat PDF research, follow-up, explicit web comparison and NVIDIA", async () => {
  test.skip(process.env.OLIVE_LIVE_AI !== "1", "Requires installed local model and public providers");
  test.setTimeout(600000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-chat-research-gui-"));
  const pdf = path.join(profile, "Synthetic report.pdf");
  execFileSync(path.resolve("../.venv/bin/python"), [path.resolve("../scripts/create_chat_research_fixture.py"), pdf]);
  const app = await electron.launch({chromiumSandbox: true, args: [path.resolve(".")], env: {...process.env, OLIVE_DATA_DIR: profile}});
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", {name: "Enter OLIVE", exact:true}).click();
    await openSpace(page, "Chat");
    await expect(mainNav(page).getByRole("button", {name:"Research", exact:true})).toHaveCount(0);
    await expect(page.getByRole("combobox", {name:"Research mode"})).toHaveCount(0);
    await expect(page.getByRole("combobox", {name:"OLIVE preset"}).locator("option")).toHaveCount(9);
    await app.evaluate(({dialog}, file) => {dialog.showOpenDialog = async () => ({canceled:false,filePaths:[file]});}, pdf);
    await page.getByRole("button", {name:"Attach files to this message",exact:true}).click();
    await expect(page.getByRole("button", {name:"Remove attachment Synthetic report.pdf",exact:true})).toBeVisible({timeout:30000});
    for (const [index, question] of [
      "Research this PDF and summarize its main findings.",
      "What evidence does it provide for its main recommendation?",
      "Compare this PDF with current information online.",
      "Research the latest developments in NVIDIA today.",
    ].entries()) {
      const before = await page.locator(".message-assistant").count();
      await page.getByRole("textbox", {name:"Message OLIVE",exact:true}).fill(question);
      await page.getByRole("button", {name:"Send message",exact:true}).click();
      await expect(page.getByRole("button", {name:"Stop response",exact:true})).toBeVisible({timeout:10000});
      await expect(page.getByRole("button", {name:"Stop response",exact:true})).toBeHidden({timeout:180000});
      await expect(page.locator('.shell')).toHaveAttribute('data-route','chat');
      const state = await page.evaluate(() => window.olive.call("runtime.snapshot", {})) as {chat:{messages:{role:string;content:string;sources:{id:string;kind:string}[];provider:unknown}[];documents:unknown[]}};
      const last = state.chat.messages.at(-1)!;
      console.log(JSON.stringify({question, checked_at:new Date().toISOString(), answer:last, errors: await page.getByRole("alert").allTextContents()}));
      expect(state.chat.documents.length).toBe(1);
      if (index < 2) {
        await expect(page.locator(".message-assistant")).toHaveCount(before+1,{timeout:180000});
        expect(last.sources.some(s => s.kind === "document_excerpt")).toBe(true);
      } else {
        // A real public outage/absence of dated evidence must be recorded as a
        // failed live acceptance, not converted into a hard-coded expected answer.
        expect.soft(last.role, "Live public retrieval must supply an answer").toBe("assistant");
        expect.soft(last.sources.some(s => ["page_excerpt","search_snippet"].includes(s.kind))).toBe(true);
        if (index === 2 && last.role === "assistant") {
          // Validate recognized references, including the legitimate formats
          // captured from local synthesis; never accept source names alone.
          const ids = JSON.parse(execFileSync(path.resolve("../.venv/bin/python"), ["-c",
            "import json,sys; from olive.services.now_service import supplied_citations; print(json.dumps(sorted(supplied_citations(sys.stdin.read()))))"],
            {cwd: path.resolve(".."), input: last.content, encoding: "utf-8"})) as string[];
          expect.soft(ids.some(id => id.startsWith("D"))).toBe(true);
          expect.soft(ids.some(id => id.startsWith("S"))).toBe(true);
          expect.soft(ids.every(id => last.sources.some(source => source.id === id))).toBe(true);
          expect.soft(last.sources.some(s => s.kind === "document_excerpt")).toBe(true);
        }
      }
    }
    await page.getByRole("button", {name:"Saved research & evidence",exact:true}).click();
    await expect(page.getByRole("dialog", {name:"Research history"})).toBeVisible();
  } finally {await app.close();}
});
