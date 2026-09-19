import { expect, it } from "vitest";
import { validateCall } from "../electron/contracts";
import { fileActionSchema } from "../electron/file-actions";
import { outcomeLabel } from "../src/features/mail/types";

it("Mail IPC never accepts a raw secret getter, arbitrary host path or injected authority", () => {
  for (const method of [
    "mail.get_secret",
    "mail.import_preview",
    "mail.attach",
    "mail.export",
  ])
    expect(() =>
      validateCall({ id: "fixture", method, args: { path: "unapproved" } }),
    ).toThrow();
  expect(() =>
    fileActionSchema.parse({
      action: "mail-attach",
      record_id: "fixture",
      revision: 1,
      path: "unapproved",
    }),
  ).toThrow();
  expect(() =>
    validateCall({
      id: "fixture",
      method: "mail.send",
      args: {
        submission_id: "fixture",
        expected_fingerprint: "fixture",
        preview: {},
        approved: true,
      },
    }),
  ).toThrow();
  expect(() =>
    validateCall({
      id: "fixture",
      method: "mail.save_draft",
      args: { record_id: "fixture", revision: 0, body: {} },
    }),
  ).toThrow();
});
it("Mail makes server acceptance and uncertainty distinct from delivery", () => {
  expect(outcomeLabel.accepted).toBe("Accepted by your mail server");
  expect(outcomeLabel.outcome_uncertain).toContain("do not resend blindly");
  expect(outcomeLabel.partially_accepted).toContain("Some recipients");
  expect(outcomeLabel.cancelled).toContain("before submission");
});
