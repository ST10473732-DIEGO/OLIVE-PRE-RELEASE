import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { spawnSync } from "node:child_process";
import { goHome, openSpace, openHistory } from "./shell";
test("Chat options branches search attachments export and deletion use real local services", async () => {
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m2-chat-"));
  const root = path.resolve("..");
  expect(
    spawnSync(
      path.join(root, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"),
      [path.join(root, "scripts/seed_m2_chat_fixture.py"), profile],
      { cwd: root },
    ).status,
  ).toBe(0);
  const evidence = path.join(root, "artifacts/ui-review/M2");
  await mkdir(evidence, { recursive: true });
  const attachment = path.join(profile, "fixture-attachment.txt");
  await writeFile(attachment, "A harmless local attachment fixture.");
  const exported = path.join(profile, "fixture-export.md");
  const app = await electron.launch({
    args: [path.resolve(".")],
    env: {
      ...process.env,
      OLIVE_DATA_DIR: profile,
      OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
    },
  });
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await openSpace(page, "Chat");
    // The conversation rail is docked open on a wide window; the open
    // conversation is also a workbench tab of the same name.
    await openHistory(page);
    await page
      .locator(".conversation-items")
      .getByRole("button", {
        name: "Fixture conversation branches",
        exact: true,
      })
      .click();
    await page
      .getByRole("button", { name: "Previous response branch" })
      .click();
    await expect(
      page.getByText("Fixture branch one.", { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Next response branch" }).click();
    await expect(
      page.getByText("Fixture branch two.", { exact: true }),
    ).toBeVisible();
    // Selecting a conversation keeps the docked rail open on a wide window.
    await openHistory(page);
    await page
      .getByRole("textbox", { name: "Search conversations" })
      .fill("uniquefixturemarker");
    await expect(
      page.locator(".conversation-items .conversation-row"),
    ).toHaveCount(1);
    await page.getByRole("textbox", { name: "Search conversations" }).fill("");
    await page
      .getByRole("textbox", { name: "Message OLIVE" })
      .fill("Retained unsent fixture");
    await goHome(page);
    await openSpace(page, "Chat");
    await expect(
      page.getByRole("textbox", { name: "Message OLIVE" }),
    ).toHaveValue("Retained unsent fixture");
    const project = (await page.evaluate(() =>
      window.olive.call("data.create_project", {
        title: "Fixture chat project",
      }),
    )) as { id: string };
    await page
      .getByRole("button", { name: "Conversation options", exact: true })
      .click();
    const sheet = page.getByRole("dialog");
    await sheet
      .getByRole("textbox", { name: "Conversation title" })
      .fill("Fixture renamed conversation");
    await sheet
      .getByRole("textbox", { name: "Conversation notes" })
      .fill("Fixture notes retained locally");
    await sheet
      .getByRole("combobox", { name: "Conversation project" })
      .selectOption(project.id);
    await sheet
      .getByRole("button", { name: "Save conversation details" })
      .click();
    await expect(sheet.getByRole("status")).toHaveText(
      "Conversation details saved.",
    );
    await app.evaluate(({ dialog }, exported) => {
      dialog.showSaveDialog = async () => ({
        canceled: false,
        filePath: exported,
      });
    }, exported);
    await sheet
      .getByRole("button", { name: "Export conversation", exact: true })
      .click();
    await expect(sheet.getByRole("status")).toHaveText(
      "Conversation exported.",
    );
    expect(await readFile(exported, "utf8")).toContain("Fixture branch two");
    await sheet.getByRole("button", { name: "Close", exact: true }).click();
    await app.evaluate(({ dialog }, attachment) => {
      dialog.showOpenDialog = async () => ({
        canceled: false,
        filePaths: [attachment],
      });
    }, attachment);
    await page
      .getByRole("button", { name: "Attach files to this message", exact: true })
      .click();
    await expect(
      page.getByRole("button", {
        name: "Remove attachment fixture-attachment.txt",
      }),
    ).toBeVisible();
    await page.screenshot({
      path: path.join(evidence, "chat-options-attachments-fixture.png"),
    });
    await page
      .getByRole("button", { name: "Remove attachment fixture-attachment.txt" })
      .click();
    await expect(
      page.getByRole("button", {
        name: "Remove attachment fixture-attachment.txt",
      }),
    ).toBeHidden();
    expect(await readFile(attachment, "utf8")).toContain("harmless");
    await page.evaluate(() => {
      const input = document.createElement("input");
      input.type = "file";
      input.id = "fixture-drop-input";
      document.body.append(input);
    });
    await page.locator("#fixture-drop-input").setInputFiles(attachment);
    await page.evaluate(() => {
      const input = document.querySelector<HTMLInputElement>(
        "#fixture-drop-input",
      )!;
      const data = new DataTransfer();
      data.items.add(input.files![0]);
      document
        .querySelector(".conversation")!
        .dispatchEvent(
          new DragEvent("drop", { bubbles: true, dataTransfer: data }),
        );
      input.remove();
    });
    await expect(
      page.getByRole("button", {
        name: "Remove attachment fixture-attachment.txt",
      }),
    ).toBeVisible();
    expect(
      await page.evaluate(async () => {
        try {
          await window.olive.attachFiles("fixture", [
            new File(["synthetic"], "fake.txt"),
          ]);
          return false;
        } catch {
          return true;
        }
      }),
    ).toBe(true);

    await page
      .getByRole("button", { name: "Conversation options", exact: true })
      .click();
    await expect(
      sheet.getByRole("textbox", { name: "Conversation notes" }),
    ).toHaveValue("Fixture notes retained locally");
    await expect(sheet.getByText("Delete this conversation", { exact: true })).toHaveCount(0);
    await sheet.getByRole("button", { name: "Close", exact: true }).click();
    // One chat is deleted from its own row in the list, after a clear question.
    const list = page.locator(".conversation-items");
    const bin = list.getByRole("button", { name: "Delete Fixture renamed conversation", exact: true });
    await list.getByRole("button", { name: "Fixture renamed conversation", exact: true }).hover();
    await expect(bin).toBeVisible();
    await bin.click();
    const question = page.getByRole("alertdialog", { name: "Delete this chat?" });
    await expect(question).toContainText("Fixture renamed conversation");
    await expect(question.getByRole("button", { name: "Cancel", exact: true })).toBeFocused();
    await page.screenshot({ path: path.join(evidence, "chat-delete-confirm.png") });
    await question.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(question).toBeHidden();
    await expect(list.getByRole("button", { name: "Fixture renamed conversation", exact: true })).toBeVisible();
    await bin.click();
    await question.getByRole("button", { name: "Delete chat", exact: true }).click();
    await expect(question).toBeHidden();
    await expect(list.getByRole("button", { name: "Fixture renamed conversation", exact: true })).toHaveCount(0);
    await expect(
      page.getByRole("heading", { name: "Fixture retained conversation", exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("alert")).toBeHidden();
    // Conversation options now offers deleting the whole history instead.
    await page.getByRole("button", { name: "Conversation options", exact: true }).click();
    await sheet.getByRole("button", { name: "Delete all chat history", exact: true }).click();
    const everything = page.getByRole("alertdialog", { name: "Delete all chat history?" });
    await expect(everything).toContainText("cannot be undone");
    await page.screenshot({ path: path.join(evidence, "chat-delete-all-confirm.png") });
    await everything.getByRole("button", { name: "Delete everything", exact: true }).click();
    await expect(everything).toBeHidden();
    await expect(list.locator(".conversation-row")).toHaveCount(1);
    await expect(list.getByRole("button", { name: "Fixture retained conversation", exact: true })).toHaveCount(0);
  } finally {
    await app.close();
  }
});
