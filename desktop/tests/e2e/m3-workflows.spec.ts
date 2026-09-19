import {
  test,
  expect,
  _electron as electron,
  type Page,
} from "@playwright/test";
import path from "node:path";
import { mkdtemp, mkdir, writeFile, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import type { Method } from "../../electron/contracts";

// Synthetic setup uses the same validated preload and real Python services.
// File chooser selection is a controlled test double; approval buttons are real.
test("M3 legacy records, recurrence, linked tasks, Calendar import and restart", async () => {
  test.setTimeout(180000);
  const profile = await mkdtemp(path.join(tmpdir(), "olive-m3-workflows-"));
  const evidence =
    process.env.OLIVE_M3_EVIDENCE ||
    path.resolve("../artifacts/ui-review/M3/workflows-" + Date.now());
  await mkdir(evidence, { recursive: true });
  const outcomes: unknown[] = [];
  const launch = () =>
    electron.launch({
      args: [path.resolve(".")],
      env: {
        ...process.env,
        OLIVE_DATA_DIR: profile,
        OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
      },
    });
  let app = await launch();
  type RecordValue = { id: string; revision: number; [key: string]: unknown };
  const api = <T = RecordValue>(
    page: Page,
    method: Method,
    args: Record<string, unknown> = {},
  ) =>
    page.evaluate(({ method, args }) => window.olive.call(method, args), {
      method,
      args,
    }) as Promise<T>;
  const enter = async () => {
    const page = await app.firstWindow();
    await page.getByRole("button", { name: "Enter OLIVE", exact: true }).click();
    return page;
  };
  const go = async (page: Page, name: string) => {
    await page
      .getByRole("button", { name: "Find anything", exact: true })
      .click();
    await page
      .getByRole("button", { name: "Open " + name, exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name, exact: true }),
    ).toBeVisible();
  };
  const approve = async (
    page: Page,
    action: string,
    content: string,
    deny = false,
  ) => {
    const dialog = page.getByRole("dialog").filter({
      has: page.getByRole("button", {
        name: "Approve this action",
        exact: true,
      }),
    });
    await expect(dialog).toBeVisible();
    const text = await dialog.innerText();
    expect(text).toContain(action);
    expect(text).toContain(content);
    expect(text).toContain("local");
    outcomes.push({
      approval: "Explicitly delegated synthetic M3 operation",
      action,
      text,
      decision: deny ? "deny" : "approve once",
    });
    await dialog
      .getByRole("button", {
        name: deny ? "Cancel" : "Approve this action",
        exact: true,
      })
      .click({ timeout: 10000 });
  };
  try {
    let page = await enter();
    await app.evaluate(({ BrowserWindow }) =>
      BrowserWindow.getAllWindows()[0].setSize(1440, 920),
    );
    const identity = await api(page, "profile.get");
    const project = await api(page, "data.create_project", {
      title: "M3 Synthetic Project",
      description: "Acceptance fixtures only",
    });
    const one = await api(page, "contacts.create", {
      body: {
        display_name: "James Synthetic",
        organization: "Fixture A",
        project_ids: [project.id],
      },
    });
    const two = await api(page, "contacts.create", {
      body: { display_name: "James Synthetic", organization: "Fixture B" },
    });
    const resolution = await api(page, "contacts.resolve", {
      query: "James Synthetic",
    });
    expect(resolution.status).toBe("ambiguous");
    outcomes.push({ resolution });
    const preview = await api(page, "contacts.merge_preview", {
      keep_id: one.id,
      remove_id: two.id,
    });
    // Legacy merge remains a compatibility service with real scoped approval;
    // Contacts is deliberately absent from normal feature presentation.
    expect(JSON.stringify(preview)).toContain("Fixture A");
    expect(JSON.stringify(preview)).toContain("Fixture B");
    const merging = api(page, "contacts.merge", {preview:{...preview,conflicts_reviewed:true}});
    await approve(page, "Contacts merge", "James Synthetic");
    await merging;
    await expect
      .poll(
        async () =>
          (await api<{ items: unknown[] }>(page, "contacts.search")).items
            .length,
      )
      .toBe(1);
    expect(
      (await api(page, "contacts.get", { record_id: one.id })).project_ids,
    ).toEqual([project.id]);
    outcomes.push({ merge_preview: preview });
    const recurring = await api(page, "calendar.create", {
      body: {
        calendar_id: identity.default_calendar,
        title: "M3 recurring fixture",
        start: "2026-09-14T09:00",
        end: "2026-09-14T10:00",
        timezone: "Africa/Johannesburg",
        recurrence: "FREQ=DAILY;COUNT=3",
        project_id: project.id,
        contact_ids: [one.id],
      },
    });
    await go(page, "Calendar");
    await page.getByLabel("Calendar date", { exact: true }).fill("2026-09-14");
    await page.getByRole("button", { name: "Agenda", exact: true }).click();
    await page
      .getByRole("button", { name: /M3 recurring fixture/ })
      .nth(1)
      .click();
    await expect(page.getByLabel("Edit scope", { exact: true })).toHaveValue(
      "occurrence",
    );
    await page
      .getByLabel("Event start", { exact: true })
      .fill("2026-09-15T11:00");
    await page
      .getByLabel("Event end", { exact: true })
      .fill("2026-09-15T12:00");
    await page.screenshot({
      path: path.join(evidence, "event-occurrence-edit.png"),
    });
    await page.getByRole("button", { name: "Save Event", exact: true }).click();
    await expect
      .poll(
        async () =>
          (await api(page, "calendar.get", { record_id: recurring.id }))
            .revision,
      )
      .toBe(2);
    const range = await api<{ items: RecordValue[] }>(page, "calendar.range", {
      after: "2026-09-14",
      before: "2026-09-18",
      timezone: "Africa/Johannesburg",
    });
    expect(range.items.map((x) => x.start)).toEqual([
      "2026-09-14T09:00:00+02:00",
      "2026-09-15T11:00:00+02:00",
      "2026-09-16T09:00:00+02:00",
    ]);
    outcomes.push({ occurrences: range });
    await api(page, "calendar.create", {
      body: {
        calendar_id: identity.default_calendar,
        title: "M3 all-day fixture",
        start: "2026-09-17",
        end: "2026-09-18",
        all_day: true,
      },
    });
    await api(page, "calendar.create", {
      body: {
        calendar_id: identity.default_calendar,
        title: "M3 overnight fixture",
        start: "2026-09-18T23:00",
        end: "2026-09-19T01:00",
        timezone: "Africa/Johannesburg",
      },
    });
    const free = await api<{ items: { start: string; end: string }[] }>(
      page,
      "calendar.free_busy",
      {
        after: "2026-09-14T09:00:00+02:00",
        before: "2026-09-14T17:00:00+02:00",
        duration: 120,
      },
    );
    expect(new Date(free.items[0].start).getTime()).toBe(
      new Date("2026-09-14T10:00:00+02:00").getTime(),
    );
    const task = await api(page, "tasks.create", {
      body: {
        title: "M3 linked task",
        project_id: project.id,
        contact_ids: [one.id],
      },
    });
    await go(page, "Tasks");
    await page.getByRole("button", { name: "All", exact: true }).click();
    await page
      .locator("article")
      .filter({
        has: page.getByRole("button", { name: /M3 linked task.*No deadline/ }),
      })
      .getByRole("button", { name: "Schedule", exact: true })
      .click();
    await page.getByLabel("Minutes needed", { exact: true }).fill("120");
    await page
      .getByRole("button", { name: "Find free time this week", exact: true })
      .click();
    await page.getByRole("radio").first().check();
    await page
      .getByRole("button", { name: "Save linked work block", exact: true })
      .click();
    await expect
      .poll(
        async () =>
          (await api(page, "tasks.get", { record_id: task.id })).event_id,
      )
      .not.toBe("");
    const linked = await api(page, "tasks.get", { record_id: task.id });
    const scheduled = {
      task: linked,
      event: await api(page, "calendar.get", { record_id: linked.event_id }),
    };
    expect(scheduled.task.event_id).toBe(scheduled.event.id);
    const completed = await api(page, "tasks.complete", {
      record_id: task.id,
      revision: scheduled.task.revision,
    });
    const reopened = await api(page, "tasks.reopen", {
      record_id: task.id,
      revision: completed.revision,
    });
    expect(reopened.status).toBe("open");
    const reminder = await api(page, "reminders.create", {
      body: {
        target_kind: "task",
        target_id: task.id,
        at: "2026-01-01T10:00:00+02:00",
      },
    });
    await expect
      .poll(
        async () =>
          (
            await api<{ items: RecordValue[] }>(page, "reminders.history")
          ).items.filter(
            (x) => x.reminder_id === reminder.id && x.state === "delivered",
          ).length,
        { timeout: 15000 },
      )
      .toBe(1);
    const history = await api<{ items: RecordValue[] }>(
      page,
      "reminders.history",
    );
    const delivery = history.items.find((x) => x.reminder_id === reminder.id)!;
    await api(page, "reminders.snooze", {
      delivery_id: delivery.id,
      minutes: 10,
    });
    await api(page, "reminders.dismiss", { delivery_id: delivery.id });
    const deleting = api(page, "tasks.delete", {
      record_id: task.id,
      revision: reopened.revision,
    }).then(
      () => ({ unexpected: true }),
      (error) => ({ denied: String(error) }),
    );
    await approve(page, "Tasks delete", "M3 linked task", true);
    expect(await deleting).toHaveProperty("denied");
    expect(
      (await api(page, "tasks.get", { record_id: task.id })).revision,
    ).toBe(reopened.revision);
    // Contact CSV/vCard validation remains covered by Python compatibility tests.
    // The active UI interchange workflow is Calendar.
    for (const fixture of [
      {
        route: "Calendar",
        format: "ics",
        kind: "calendar.search" as const,
        title: "M3 ICS Event",
        text: "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//OLIVE//Synthetic//EN\r\nBEGIN:VEVENT\r\nUID:m3-ics-fixture\r\nDTSTART;VALUE=DATE:20260921\r\nDTEND;VALUE=DATE:20260922\r\nSUMMARY:M3 ICS Event\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n",
      },
    ]) {
      const file = path.join(profile, "synthetic." + fixture.format);
      await writeFile(file, fixture.text);
      await app.evaluate(({ dialog }, file) => {
        dialog.showOpenDialog = async () => ({
          canceled: false,
          filePaths: [file],
        });
      }, file);
      await go(page, fixture.route);
      await page
        .getByRole("combobox", { name: "Interchange format", exact: true })
        .selectOption(fixture.format);
      await page.getByRole("button", { name: "Import", exact: true }).click();
      const preview = page.getByRole("dialog", { name: "Review import" });
      await expect(preview).toContainText(fixture.title);
      await preview.getByText("Record details", { exact: true }).click();
      await page.screenshot({
        path: path.join(evidence, fixture.format + "-import-preview.png"),
      });
      await page
        .getByRole("button", { name: "Review and commit import", exact: true })
        .click();
      await approve(page, "Personal import commit", fixture.title);
      await expect
        .poll(
          async () =>
            (
              await api<{ items: unknown[] }>(page, fixture.kind, {
                query: fixture.title,
              })
            ).items.length,
        )
        .toBe(1);
      const before = await api<{ items: RecordValue[] }>(page, fixture.kind, {
        query: fixture.title,
      });
      await page.getByRole("button", { name: "Import", exact: true }).click();
      await expect(
        preview.getByLabel("Import choice 1", { exact: true }),
      ).toHaveValue("skip");
      await page
        .getByRole("button", { name: "Cancel import", exact: true })
        .click();
      const after = await api<{ items: RecordValue[] }>(page, fixture.kind, {
        query: fixture.title,
      });
      expect(after.items).toEqual(before.items);
      outcomes.push({
        interchange: fixture.format,
        unchanged_reimport:
          "default skipped; explicit cancel; ID/revision retained",
        records: after,
      });
      const wholeBefore = await api<{ items: RecordValue[] }>(
        page,
        fixture.kind,
      );
      const roundtrip = path.join(profile, "roundtrip." + fixture.format);
      await app.evaluate(({ dialog }, file) => {
        dialog.showSaveDialog = async () => ({
          canceled: false,
          filePath: file,
        });
      }, roundtrip);
      await page.getByRole("button", { name: "Export", exact: true }).click();
      await expect
        .poll(async () => {
          try {
            return await readFile(roundtrip, "utf8");
          } catch (error) {
            if ((error as NodeJS.ErrnoException).code === "ENOENT") return "";
            throw error;
          }
        })
        .toContain(fixture.title);
      await app.evaluate(({ dialog }, file) => {
        dialog.showOpenDialog = async () => ({
          canceled: false,
          filePaths: [file],
        });
      }, roundtrip);
      await page.getByRole("button", { name: "Import", exact: true }).click();
      await expect(preview).toBeVisible();
      await expect(preview.getByRole("alert")).toHaveCount(0);
      await page
        .getByRole("button", { name: "Review and commit import", exact: true })
        .click();
      await approve(page, "Personal import commit", fixture.title);
      await expect(preview).not.toBeVisible();
      const wholeAfter = await api<{ items: RecordValue[] }>(
        page,
        fixture.kind,
      );
      expect(wholeAfter.items.map((r) => r.id).sort()).toEqual(
        wholeBefore.items.map((r) => r.id).sort(),
      );
      outcomes.push({
        roundtrip: fixture.format,
        idsRetained: true,
        records: wholeAfter,
      });
    }
    await app.close();
    app = await launch();
    page = await enter();
    expect(
      (await api(page, "tasks.get", { record_id: task.id })).event_id,
    ).toBe(scheduled.event.id);
    const restarted = await api<{ items: RecordValue[] }>(
      page,
      "reminders.history",
    );
    expect(
      restarted.items.filter((x) => x.reminder_id === reminder.id),
    ).toHaveLength(1);
    expect(restarted.items.find((x) => x.id === delivery.id)?.state).toBe(
      "dismissed",
    );
    outcomes.push({
      restart:
        "Real backend and Electron restart; stable linked records and dismissed delivery retained",
      free,
      scheduled,
      reminder_history: restarted,
    });
    await go(page, "Projects");
    await page.getByRole("button", { name: /M3 Synthetic Project/ }).click();
    await expect(page.getByRole("navigation", {name:"Project relationships"}).getByRole("button", {name:"Contacts",exact:true})).toHaveCount(0);
    const retained = await api(page,"contacts.get",{record_id:one.id});
    expect(retained.project_ids).toEqual([project.id]);
    expect((await api(page,"calendar.get",{record_id:recurring.id})).contact_ids).toEqual([one.id]);
    await page.screenshot({path:path.join(evidence,"project-native-links.png")});
  } catch (error) {
    outcomes.push({ primary_error: String(error) });
    try {
      await (
        await app.firstWindow()
      ).screenshot({ path: path.join(evidence, "workflow-first-failure.png") });
    } catch (secondary) {
      outcomes.push({ secondary: String(secondary) });
    }
    throw error;
  } finally {
    await writeFile(
      path.join(evidence, "workflows-result.json"),
      JSON.stringify(
        {
          profile,
          classification:
            "Live local Electron/Python; synthetic setup via validated preload; native file selection mocked; actual delegated approval buttons",
          outcomes,
        },
        null,
        2,
      ),
    );
    await app.close();
  }
});
