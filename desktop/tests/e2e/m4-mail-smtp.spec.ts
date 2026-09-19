import { captureMail } from "./m4-capture";
import { test, expect, _electron as electron } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

for (const scenario of [
  "accepted",
  "partially_accepted",
  "outcome_uncertain",
] as const)
  test(
    "M4 delegated exact submission through Electron to independent loopback TLS sink: " +
      scenario,
    async () => {
      test.setTimeout(120000);
      const profile = await mkdtemp(path.join(tmpdir(), "olive-m4-smtp-ui-"));
      const sinkDir = await mkdtemp(path.join(tmpdir(), "olive-m4-sink-"));
      const evidence = path.resolve(
        "../artifacts/ui-review/M4/smtp-ui/" + scenario,
      );
      await mkdir(evidence, { recursive: true });
      const sink = spawn(
        path.resolve("../.venv/Scripts/python.exe"),
        [
          path.resolve("../scripts/run_m4_mail_sink.py"),
          "--directory",
          sinkDir,
          ...(scenario === "partially_accepted"
            ? ["--reject-address", "hidden@example.invalid"]
            : scenario === "outcome_uncertain"
              ? ["--lose-final-reply"]
              : []),
        ],
        { windowsHide: true, stdio: "pipe" },
      );
      let logs = "";
      sink.stdout.on("data", (d) => (logs += d));
      sink.stderr.on("data", (d) => (logs += d));
      let app: Awaited<ReturnType<typeof electron.launch>> | undefined;
      try {
        await expect
          .poll(
            async () => {
              try {
                const r = JSON.parse(
                  await readFile(path.join(sinkDir, "ready.json"), "utf8"),
                );
                return r.pid === sink.pid || r.parent_pid === sink.pid;
              } catch {
                return false;
              }
            },
            { timeout: 20000 },
          )
          .toBe(true);
        const ready = JSON.parse(
          await readFile(path.join(sinkDir, "ready.json"), "utf8"),
        );
        expect(path.resolve(ready.script)).toBe(
          path.resolve("../scripts/run_m4_mail_sink.py"),
        );
        expect(ready.connection.smtp.host).toBe("127.0.0.1");
        app = await electron.launch({
          args: [path.resolve(".")],
          env: {
            ...process.env,
            OLIVE_DATA_DIR: profile,
            OLIVE_OLLAMA_HOST: "http://127.0.0.1:1",
          },
        });
        const page = await app.firstWindow();
        await page
          .getByRole("button", { name: "Enter OLIVE", exact: true })
          .click();
        await page
          .getByRole("button", { name: "Find anything", exact: true })
          .click();
        await page
          .getByRole("button", { name: "Open Mail", exact: true })
          .click();
        await page
          .getByRole("button", { name: "Mail connections", exact: true })
          .click();
        await page
          .getByRole("button", { name: "Add connection", exact: true })
          .click();
        const form = page.getByRole("dialog", {
          name: "Connect a mail server",
        });
        await form
          .getByLabel("Connection name", { exact: true })
          .fill("M4 isolated loopback sink");
        await form
          .getByLabel("Sending email address", { exact: true })
          .fill("sender@example.invalid");
        await form.getByLabel("Username", { exact: true }).fill("fixture");
        await form.getByLabel("SMTP server", { exact: true }).fill("127.0.0.1");
        await form
          .getByLabel("Port", { exact: true })
          .fill(String(ready.connection.smtp.port));
        await form
          .getByLabel("SMTP security", { exact: true })
          .selectOption("starttls");
        await form
          .getByText("Private server certificate authority", { exact: true })
          .click();
        await form
          .getByLabel("Connection-specific CA certificate (PEM)", {
            exact: true,
          })
          .fill(ready.connection.ca_pem);
        await form
          .getByRole("button", { name: "Save connection", exact: true })
          .click();
        await expect(form).not.toBeVisible();
        await page
          .getByRole("button", { name: "Store credentials", exact: true })
          .click();
        const credential = page.getByRole("dialog", {
          name: "Store mail credentials",
        });
        await credential
          .getByLabel("Password or app password", { exact: true })
          .fill("fixture-secret");
        await expect(
          credential.getByLabel("Password or app password"),
        ).toHaveAttribute("type", "password");
        await credential
          .getByRole("button", { name: "Store credentials", exact: true })
          .click();
        await expect(credential).not.toBeVisible();
        await page
          .getByRole("button", { name: "Test connection", exact: true })
          .click();
        await expect(
          page.getByRole("region", { name: "Connection test results" }),
        ).toContainText("SMTP: completed");
        await expect
          .poll(async () => {
            try {
              await readFile(path.join(sinkDir, "message-1.eml"));
              return true;
            } catch {
              return false;
            }
          })
          .toBe(false);
        await page
          .getByRole("button", { name: "Reconnect", exact: true })
          .click();
        await expect(
          page.getByRole("button", { name: "Disconnect", exact: true }),
        ).toBeVisible();
        await captureMail(page, app, path.join(evidence, "connections.png"));
        await page
          .getByRole("dialog", { name: "Connections", exact: true })
          .getByRole("button", { name: "Close", exact: true })
          .click();
        await page
          .getByRole("button", { name: "Compose", exact: true })
          .click();
        await page
          .getByLabel("From / sending identity", { exact: true })
          .selectOption({
            label: "M4 isolated loopback sink · sender@example.invalid",
          });
        await page
          .getByLabel("To", { exact: true })
          .fill("recipient@example.invalid");
        await page
          .getByLabel("CC", { exact: true })
          .fill("copy@example.invalid");
        await page
          .getByLabel("BCC", { exact: true })
          .fill("hidden@example.invalid");
        await page
          .getByLabel("Subject", { exact: true })
          .fill("M4 delegated TLS fixture");
        await page
          .getByLabel("Message", { exact: true })
          .fill("Synthetic local acceptance — no Internet delivery.");
        const file = path.join(profile, "fixture.txt");
        await writeFile(file, "M4 immutable attachment fixture");
        await app.evaluate(({ dialog }, file) => {
          dialog.showOpenDialog = async () => ({
            canceled: false,
            filePaths: [file],
          });
        }, file);
        await page
          .getByRole("button", { name: "Attach file", exact: true })
          .click();
        await expect(
          page.getByText("fixture.txt", { exact: false }).first(),
        ).toBeVisible();
        await page
          .getByRole("button", { name: "Review submission", exact: true })
          .click();
        const approval = page.getByRole("dialog").filter({
          has: page.getByRole("button", {
            name: "Approve this action",
            exact: true,
          }),
        });
        await expect(approval).toBeVisible();
        if (scenario === "accepted") {
          const cancelledPreview = await approval.innerText();
          for (const value of [
            "127.0.0.1",
            String(ready.connection.smtp.port),
            "recipient@example.invalid",
            "M4 delegated TLS fixture",
            "fixture.txt",
          ])
            expect(cancelledPreview).toContain(value);
          await approval
            .getByRole("button", { name: "Cancel", exact: true })
            .click();
          await expect
            .poll(
              async () =>
                (
                  (await page.evaluate(() =>
                    window.olive.call("mail.outbox", {}),
                  )) as { items: { state: string }[] }
                ).items[0]?.state,
            )
            .toBe("cancelled");
          await expect(page.getByLabel("Message", { exact: true })).toHaveValue(
            "Synthetic local acceptance — no Internet delivery.",
          );
          await expect(
            readFile(path.join(sinkDir, "envelope-1.json")),
          ).rejects.toMatchObject({ code: "ENOENT" });
          await page
            .getByRole("button", { name: "Review submission", exact: true })
            .click();
          await expect(approval).toBeVisible();
        }
        const preview = await approval.innerText();
        for (const expected of [
          "127.0.0.1",
          String(ready.connection.smtp.port),
          "sender@example.invalid",
          "recipient@example.invalid",
          "copy@example.invalid",
          "hidden@example.invalid",
          "M4 delegated TLS fixture",
          "Synthetic local acceptance",
          "fixture.txt",
        ])
          expect(preview).toContain(expected);
        const attempts = (await page.evaluate(() =>
          window.olive.call("mail.outbox", {}),
        )) as { items: { id: string; state: string }[] };
        expect(attempts.items).toHaveLength(scenario === "accepted" ? 2 : 1);
        await captureMail(page, app, path.join(evidence, "exact-approval.png"));
        await approval
          .getByRole("button", { name: "Approve this action", exact: true })
          .click();
        await expect
          .poll(
            async () => {
              const r = (await page.evaluate(() =>
                window.olive.call("mail.outbox", {}),
              )) as { items: { state: string }[] };
              return r.items[0]?.state;
            },
            { timeout: 25000 },
          )
          .toBe(scenario);
        const envelope = JSON.parse(
          await readFile(path.join(sinkDir, "envelope-1.json"), "utf8"),
        );
        expect(envelope.recipients.sort()).toEqual(
          [
            "recipient@example.invalid",
            "copy@example.invalid",
            ...(scenario === "partially_accepted"
              ? []
              : ["hidden@example.invalid"]),
          ].sort(),
        );
        const raw = await readFile(path.join(sinkDir, "message-1.eml"), "utf8");
        expect(raw).not.toMatch(/^bcc:/im);
        expect(raw).toContain("M4 delegated TLS fixture");
        expect(raw).toContain("fixture.txt");
        await expect(
          page.getByRole("button", { name: "Review submission", exact: true }),
        ).toBeDisabled();
        await page.getByRole("button", { name: /^Outbox/ }).click();
        await expect(
          page
            .getByRole("heading", {
              name:
                scenario === "accepted"
                  ? "Accepted by your mail server"
                  : scenario === "partially_accepted"
                    ? "Some recipients accepted"
                    : "Outcome uncertain — do not resend blindly",
              exact: true,
            })
            .first(),
        ).toBeVisible();
        await captureMail(
          page,
          app,
          path.join(evidence, "submission-outcome.png"),
        );
        await writeFile(
          path.join(evidence, "result.json"),
          JSON.stringify(
            {
              classification:
                "live local Electron/production SMTP/independent aiosmtpd STARTTLS sink",
              profile,
              owned_sink_pid: sink.pid,
              approval:
                "One exact action approved under explicit user delegation",
              prior_review_cancelled_without_submission:
                scenario === "accepted",
              preview,
              envelope,
              scenario,
              submission: attempts.items[0].id,
            },
            null,
            2,
          ),
        );
        await page
          .getByRole("button", { name: "Mail connections", exact: true })
          .click();
        await page
          .getByRole("button", { name: "Remove credentials", exact: true })
          .click();
        await expect(
          page.getByRole("button", { name: "Store credentials", exact: true }),
        ).toBeVisible();
      } finally {
        if (app) {
          const page = await app.firstWindow();
          // Fixture-owned credential cleanup through the same validated endpoint;
          // never enumerate or retrieve unrelated vault records.
          await page.evaluate(async () => {
            const r = (await window.olive.call("mail.connections", {})) as {
              items: {
                id: string;
                revision: number;
                name: string;
                credential_ref: string;
                smtp: { host: string };
              }[];
            };
            for (const c of r.items) {
              if (
                c.name !== "M4 isolated loopback sink" ||
                c.smtp.host !== "127.0.0.1"
              )
                throw new Error("Unexpected fixture connection during cleanup");
              if (c.credential_ref)
                await window.olive.call("mail.connection_state", {
                  record_id: c.id,
                  revision: c.revision,
                  enabled: false,
                  remove_credentials: true,
                });
            }
          });
          await app.close();
        }
        await writeFile(path.join(sinkDir, "stop"), "stop owned fixture");
        await expect.poll(() => sink.exitCode, { timeout: 15000 }).toBe(0);
        await writeFile(path.join(evidence, "sink.log"), logs);
        await writeFile(
          path.join(evidence, "cleanup.json"),
          await readFile(path.join(sinkDir, "stopped.json")),
        );
      }
    },
  );
