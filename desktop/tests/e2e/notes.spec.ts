import { test, expect, _electron as electron, type ElectronApplication, type Page } from "@playwright/test";
import { mkdtemp, rm } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { openSpace } from "./shell";

// OLIVE Notes in the real Electron app with an isolated profile and no model.
// Synthetic text only. Physical phone sync is covered elsewhere (and by the
// owner on the Mac); this proves the desktop app end to end.
const root = path.resolve("..");

async function launch(profile: string): Promise<{ app: ElectronApplication; page: Page }> {
  const env = { ...process.env, OLIVE_DATA_DIR: profile, OLIVE_OLLAMA_HOST: "http://127.0.0.1:1", OLIVE_START_OLLAMA: "0" };
  delete (env as Record<string, string | undefined>).ELECTRON_RUN_AS_NODE;
  const app = await electron.launch({ executablePath: path.join(root, "run_olive.sh"), chromiumSandbox: true, env, timeout: 90000 });
  const page = await app.firstWindow();
  await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
  return { app, page };
}

test("OLIVE Notes: create, type, rename, search, pin, delete, restore, live update, restart", async () => {
  test.skip(process.platform !== "linux", "Linux desktop acceptance");
  test.setTimeout(300000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-notes-e2e-"));
  let { app, page } = await launch(profile);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  try {
    await openSpace(page, "OLIVE Notes");
    await expect(page.locator(".shell")).toHaveAttribute("data-route", "notes");
    await expect(page.getByRole("heading", { name: "No notes yet" })).toBeVisible();
    await page.getByRole("button", { name: "New note", exact: true }).first().click();
    const editor = page.locator("textarea.notes-textarea");
    await expect(editor).toBeFocused();
    await editor.pressSequentially("Desktop line 1\nolive-sync-zebra-9271 kit list");
    await expect(page.getByRole("status").filter({ hasText: "Saved locally" })).toBeVisible();
    await page.getByRole("textbox", { name: "Note title" }).fill("OLIVE Notes Sync Test");
    await page.getByRole("textbox", { name: "Note title" }).press("Enter");
    await expect(page.getByRole("list", { name: "Notes", exact: true }).getByText("OLIVE Notes Sync Test")).toBeVisible();

    // Undo removes only this device's latest typing burst (bursts are 500 ms apart).
    await page.waitForTimeout(800);
    await editor.press("End");
    await editor.pressSequentially(" TEMP");
    await page.waitForTimeout(700);
    await editor.press("Control+z");
    await expect(editor).toHaveValue("Desktop line 1\nolive-sync-zebra-9271 kit list");

    // Leave and come back: the text is stored, not held by the view.
    await openSpace(page, "Chat");
    await openSpace(page, "OLIVE Notes");
    await expect(editor).toHaveValue("Desktop line 1\nolive-sync-zebra-9271 kit list");

    // A Chat-originated CRDT edit arrives live; the caret stays on its text.
    await editor.click();
    await editor.evaluate((el: HTMLTextAreaElement) => el.setSelectionRange(3, 3));
    const chatId = await page.evaluate(async () => ((await window.olive.call("runtime.snapshot", {})) as { chat: { id: string } }).chat.id);
    await page.evaluate(async (id) => {
      await window.olive.call("interaction.submit", { chat_id: id, text: "Add 'Chat line' to my OLIVE Notes Sync Test note" });
    }, chatId);
    await expect(editor).toHaveValue("Desktop line 1\nolive-sync-zebra-9271 kit list\nChat line");
    expect(await editor.evaluate((el: HTMLTextAreaElement) => el.selectionStart)).toBe(3);

    // Local search.
    await page.getByRole("textbox", { name: "Search notes" }).fill("zebra-9271");
    await expect(page.getByRole("list", { name: "Notes", exact: true }).getByText("OLIVE Notes Sync Test")).toBeVisible();
    await page.getByRole("button", { name: "Clear search", exact: true }).click();

    // Pin, delete to Recently Deleted, restore the same note.
    await page.getByRole("button", { name: "Pin note", exact: true }).click();
    await expect(page.getByRole("button", { name: "Unpin note", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Move note to Recently Deleted", exact: true }).click();
    await page.getByRole("group", { name: "Notes view" }).getByRole("button", { name: /Recently Deleted/ }).click();
    await page.getByRole("list", { name: "Recently deleted notes" }).getByText("OLIVE Notes Sync Test").click();
    await page.getByRole("button", { name: "Restore", exact: true }).click();
    await page.getByRole("group", { name: "Notes view" }).getByRole("button", { name: /^Notes/ }).click();
    await expect(page.getByRole("list", { name: "Notes", exact: true }).getByText("OLIVE Notes Sync Test")).toBeVisible();

    // History has at least the rename checkpoint.
    await page.getByRole("list", { name: "Notes", exact: true }).getByText("OLIVE Notes Sync Test").click();
    await page.getByRole("button", { name: "Version history", exact: true }).click();
    await expect(page.getByRole("list", { name: "Versions" }).getByRole("listitem").first()).toBeVisible();
    expect(errors).toEqual([]);

    // Restart on the same isolated profile: the note is still there.
    await app.close();
    ({ app, page } = await launch(profile));
    await openSpace(page, "OLIVE Notes");
    await expect(page.locator("textarea.notes-textarea")).toHaveValue("Desktop line 1\nolive-sync-zebra-9271 kit list\nChat line");
    await expect(page.getByRole("list", { name: "Notes", exact: true }).getByText("OLIVE Notes Sync Test")).toBeVisible();
  } finally {
    await app.close().catch(() => undefined);
    await rm(profile, { recursive: true, force: true });
  }
});
