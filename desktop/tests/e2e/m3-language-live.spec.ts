import { test, expect, _electron as electron } from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";

test("M3 installed local interpreter proposes corrects and saves through Electron", async () => {
  test.skip(
    process.env.OLIVE_M3_LIVE_LANGUAGE !== "1",
    "Opt-in installed-model evaluation; deterministic native tests run ordinarily.",
  );
  test.setTimeout(600000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m3-language-"));
  const evidence =
    process.env.OLIVE_M3_EVIDENCE ||
    path.resolve("../artifacts/ui-review/M3/language-" + Date.now());
  await mkdir(evidence, { recursive: true });
  const launch = () =>
    electron.launch({
      args: [path.resolve(".")],
      env: {
        ...process.env,
        OLIVE_DATA_DIR: profile,
        OLIVE_OLLAMA_HOST: "http://127.0.0.1:11434",
      },
    });
  let app = await launch();
  const outcomes: unknown[] = [];
  try {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    await expect
      .poll(
        async () =>
          (
            (await page.evaluate(() =>
              window.olive.call("runtime.snapshot", {}),
            )) as { initializing: boolean }
          ).initializing,
        { timeout: 60000 },
      )
      .toBe(false);
    const request =
      "Create a local calendar event titled M3 Synthetic Practice on 2026-09-14 at 18:00 for two hours. Prepare it for review; do not save it yet.";
    await page
      .getByRole("textbox", { name: "Ask OLIVE anything", exact: true })
      .fill(request);
    await page
      .getByRole("button", { name: "Submit request", exact: true })
      .click();
    type Chat = {
      id: string;
      messages: { role: string; content: string }[];
      native_proposals: {
        id: string;
        revision: number;
        method: string;
        body: {
          title: string;
          start: string;
          end: string;
          project_id?: string;
          contact_ids?: string[];
          event_id?: string;
          target_id?: string;
        };
      }[];
    };
    const chat = async () =>
      (await page.evaluate(async () => {
        const state = (await window.olive.call("runtime.snapshot", {})) as {
          chat: { id: string };
        };
        return window.olive.call("chat.get", { chat_id: state.chat.id });
      })) as Chat;
    await expect
      .poll(
        async () =>
          (await chat()).messages.filter((m) => m.role === "assistant").length,
        { timeout: 150000 },
      )
      .toBeGreaterThan(0);
    const first = await chat();
    outcomes.push({
      request,
      chat: first,
      interpretation: await page.evaluate(
        (id) => window.olive.call("interaction.inspect", { chat_id: id }),
        first.id,
      ),
    });
    expect(first.native_proposals).toHaveLength(1);
    expect((first.native_proposals[0].body as {recurrence?:string}).recurrence || '').toBe('');
    expect(first.native_proposals[0].body.start).toBe(
      "2026-09-14T18:00:00+02:00",
    );
    expect(
      (
        (await page.evaluate(() =>
          window.olive.call("calendar.search", {}),
        )) as { items: unknown[] }
      ).items,
    ).toHaveLength(0);
    await page
      .getByRole("textbox", { name: "Message OLIVE", exact: true })
      .fill("Make the proposed practice one hour later, keeping its duration.");
    await page
      .getByRole("button", { name: "Send message", exact: true })
      .click();
    await expect
      .poll(
        async () =>
          (await chat()).messages.filter((m) => m.role === "assistant").length,
        { timeout: 120000 },
      )
      .toBeGreaterThan(1);
    const corrected = await chat();
    outcomes.push({ correction: corrected });
    expect(corrected.native_proposals[0]?.revision).toBe(2);
    expect(corrected.native_proposals[0].body.start).toBe(
      "2026-09-14T19:00:00+02:00",
    );
    expect(corrected.native_proposals[0].body.end).toBe(
      "2026-09-14T21:00:00+02:00",
    );
    await page.screenshot({
      path: path.join(evidence, "language-corrected-proposal.png"),
    });
    await page
      .getByRole("textbox", { name: "Message OLIVE", exact: true })
      .fill("Save this calendar proposal now.");
    await page
      .getByRole("button", { name: "Send message", exact: true })
      .click();
    const approval = page.getByRole("dialog").filter({
      has: page.getByRole("button", {
        name: "Approve this action",
        exact: true,
      }),
    });
    await expect
      .poll(
        async () =>
          (await approval.count()) > 0
            ? "approval"
            : (await chat()).messages.filter((m) => m.role === "assistant")
                  .length > 2
              ? "answer"
              : "running",
        { timeout: 120000 },
      )
      .not.toBe("running");
    await expect(approval).toBeVisible();
    const text = await approval.innerText();
    expect(text).toContain("M3 Synthetic Practice");
    expect(text).toContain("2026-09-14T19:00:00+02:00");
    expect(text).toContain("Calendar create");
    expect(text).not.toContain('FREQ=');
    await page.screenshot({
      path: path.join(evidence, "language-delegated-approval.png"),
    });
    outcomes.push({
      approval: "Exercised under explicit M3 synthetic-operation delegation",
      text,
    });
    await approval
      .getByRole("button", { name: "Approve this action", exact: true })
      .click();
    await expect
      .poll(
        async () =>
          (
            (await page.evaluate(() =>
              window.olive.call("calendar.search", {}),
            )) as { items: unknown[] }
          ).items.length,
      )
      .toBe(1);
    outcomes.push({
      saved: await page.evaluate(() => window.olive.call("calendar.search", {})),
      chat: await chat(),
    });
    const fixtures = await page.evaluate(async () => {
      const project = (await window.olive.call("data.create_project", {
        title: "M3 Language Project",
      })) as { id: string };
      const contact = (await window.olive.call("contacts.create", {
        body: {
          display_name: "James Synthetic",
          organization: "Fixture A",
          project_ids: [project.id],
        },
      })) as { id: string };
      await window.olive.call("contacts.create", {
        body: { display_name: "James Synthetic", organization: "Fixture B" },
      });
      const events = (await window.olive.call("calendar.search", {})) as {
        items: { id: string }[];
      };
      return {
        project: project.id,
        contact: contact.id,
        event: events.items[0].id,
      };
    });
    const say = async (text: string) => {
      const before = (await chat()).messages.filter(
        (m) => m.role === "assistant",
      ).length;
      await page
        .getByRole("textbox", { name: "Message OLIVE", exact: true })
        .fill(text);
      await page
        .getByRole("button", { name: "Send message", exact: true })
        .click();
      await expect
        .poll(
          async () =>
            (await chat()).messages.filter((m) => m.role === "assistant")
              .length,
          { timeout: 150000 },
        )
        .toBeGreaterThan(before);
      const result = await chat();
      outcomes.push({ request: text, chat: result });
      return result;
    };
    // Historical contact links remain readable, without a Contacts application.
    expect(await page.evaluate(id => window.olive.call("contacts.get", {record_id:id}),fixtures.contact)).toMatchObject({organization:"Fixture A",revision:1});
    const task = await say(
      `Create a personal task titled M3 Synthetic Follow-through for project M3 Language Project, linked to calendar event ${fixtures.event}. Prepare it for review without saving.`,
    );
    expect(task.native_proposals).toHaveLength(1);
    expect(task.native_proposals[0].method).toBe("tasks.create");
    expect(task.native_proposals[0].body).toMatchObject({
      project_id: fixtures.project,
      event_id: fixtures.event,
    });
    const review = async (expectedAction: string, expectedContent: string) => {
      await page
        .getByRole("button", { name: "Review save", exact: true })
        .click();
      await expect(approval).toBeVisible();
      const text = await approval.innerText();
      expect(text).toContain(expectedAction);
      expect(text).toContain(expectedContent);
      outcomes.push({
        approval: "Explicit M3 delegation, one matching action",
        text,
      });
      await approval
        .getByRole("button", { name: "Approve this action", exact: true })
        .click();
      await expect
        .poll(async () => (await chat()).native_proposals.length)
        .toBe(0);
    };
    await review("Tasks create", "M3 Synthetic Follow-through");
    const reminder = await say(
      "Create a reminder thirty minutes before the calendar event we saved in this conversation.",
    );
    expect(reminder.native_proposals).toHaveLength(1);
    expect(reminder.native_proposals[0].method).toBe("reminders.create");
    expect(reminder.native_proposals[0].body.target_id).toBe(fixtures.event);
    await review("Reminders create", fixtures.event);
    outcomes.push({
      composition: await page.evaluate(async () => ({
        tasks: await window.olive.call("tasks.search", {}),
        reminders: await window.olive.call("reminders.search", {}),
      })),
    });
    const free = await say(
      "Find a free block of two hours on 2026-09-14 during my working hours. Show options without saving anything.",
    );
    const freeEvidence = (await page.evaluate(
      (id) => window.olive.call("interaction.inspect", { chat_id: id }),
      free.id,
    )) as { resolved_steps: { intent: string }[] };
    expect(
      freeEvidence.resolved_steps.some(
        (step) => step.intent === "calendar.free_busy",
      ),
    ).toBe(true);
    expect(free.native_proposals).toHaveLength(0);
    const freeText = free.messages.at(-1)?.content || "";
    expect(freeText).toContain("2026-09-14T09:00:00+02:00 to 2026-09-14T11:00:00+02:00");
    expect(freeText).not.toContain("2026-09-15");
    outcomes.push({ freeTime: freeEvidence });
    await page
      .getByRole("button", { name: "Find anything", exact: true })
      .click();
    await page.getByRole("button", { name: "Open Agent", exact: true }).click();
    const count = (await chat()).messages.filter(
      (m) => m.role === "assistant",
    ).length;
    await page
      .getByRole("textbox", { name: "Agent objective", exact: true })
      .fill("List my native personal tasks.");
    await page
      .getByRole("button", { name: "Start objective", exact: true })
      .click();
    await expect
      .poll(
        async () =>
          (await chat()).messages.filter((m) => m.role === "assistant").length,
        { timeout: 120000 },
      )
      .toBeGreaterThan(count);
    expect((await chat()).messages.at(-1)?.content).toContain(
      "M3 Synthetic Follow-through",
    );
    outcomes.push({ agentNativeRead: await chat() });
    await page.screenshot({
      path: path.join(evidence, "agent-native-result.png"),
    });
    await page
      .getByRole("button", { name: "Find anything", exact: true })
      .click();
    await page.getByRole("button", {name:"Open Settings",exact:true}).click();
    await page.getByRole("navigation", {name:"Settings categories"}).getByRole("button", {name:"General",exact:true}).click();
    await expect(page.getByRole("textbox", {name:"Preferred name",exact:true})).toHaveValue("Diego");
    const previousIdentity = await page.evaluate(() => window.olive.call("profile.get", {}));
    await app.close();
    app = await launch();
    const restarted = await app.firstWindow();
    await restarted
      .getByRole("button", { name: "Enter OLIVE", exact: true })
      .click();
    const retained = (await restarted.evaluate(
      async (eventId) => ({
        profile: await window.olive.call("profile.get", {}),
        event: await window.olive.call("calendar.get", { record_id: eventId }),
        tasks: await window.olive.call("tasks.search", {}),
        reminders: await window.olive.call("reminders.search", {}),
      }),
      fixtures.event,
    )) as {
      profile: { display_name: string };
      event: { id: string; start: string };
      tasks: { items: unknown[] };
      reminders: { items: unknown[] };
    };
    expect(retained.profile).toEqual(previousIdentity);
    expect(retained.event.start).toBe("2026-09-14T19:00:00+02:00");
    expect(retained.tasks.items).toHaveLength(1);
    expect(retained.reminders.items).toHaveLength(1);
    outcomes.push({ fullBackendRestart: retained });
  } catch (error) {
    outcomes.push({ primary_error: String(error) });
    try {
      const page = await app.firstWindow();
      outcomes.push({
        failure_state: await page.evaluate(async () => {
          const state = (await window.olive.call("runtime.snapshot", {})) as {
            chat: { id: string };
          };
          return {
            chat: await window.olive.call("chat.get", {
              chat_id: state.chat.id,
            }),
            interpretation: await window.olive.call("interaction.inspect", {
              chat_id: state.chat.id,
            }),
          };
        }),
      });
      await page.screenshot({ path: path.join(evidence, "first-failure.png") });
    } catch (cleanupError) {
      outcomes.push({ secondary_capture_error: String(cleanupError) });
    }
    throw error;
  } finally {
    await writeFile(
      path.join(evidence, "language-result.json"),
      JSON.stringify(
        {
          classification:
            "real installed local model, real Electron/Python interpreter and native tools",
          profile,
          outcomes,
        },
        null,
        2,
      ),
    );
    await app.close();
  }
});
