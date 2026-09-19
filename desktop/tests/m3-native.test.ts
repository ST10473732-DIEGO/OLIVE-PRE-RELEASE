import { expect, it } from "vitest";
import { validateCall } from "../electron/contracts";
import { fileActionSchema } from "../electron/file-actions";
import { personalDate } from "../src/features/personal/format";
import { body } from "../src/features/personal/types";

it("native file import/export paths remain main-process choices", () => {
  for (const method of [
    "personal.import_preview",
    "personal.export",
    "profile.avatar",
  ])
    expect(() =>
      validateCall({ id: "fixture", method, args: { path: "unapproved" } }),
    ).toThrow();
  expect(() =>
    fileActionSchema.parse({
      action: "personal-import",
      kind: "contact",
      format: "csv",
      path: "unapproved",
    }),
  ).toThrow();
  expect(() =>
    validateCall({
      id: "fixture",
      method: "contacts.search",
      args: { query: "Synthetic", approved: true },
    }),
  ).toThrow();
});
it("profile formatting keeps date-only deadlines stable across timezones", () => {
  const profile = {
    timezone: "America/Los_Angeles",
    locale: "en-ZA",
    date_format: "dd/MM/yyyy",
    time_format: "24h",
  };
  expect(personalDate("2026-09-14", profile)).toBe("14/09/2026");
  expect(personalDate("2026-09-14T00:30:00Z", profile)).toBe(
    "13/09/2026 17:30",
  );
  expect(
    personalDate("2026-09-14", { ...profile, date_format: "yyyy-MM-dd" }),
  ).toBe("2026-09-14");
});
it("editing a returned record excludes authoritative metadata and provenance", () => {
  const value = {
    id: "fixture",
    uid: "source",
    kind: "task",
    revision: 3,
    created_at: "then",
    updated_at: "now",
    title: "Synthetic",
    provenance: { created: { origin: "local_import" } },
    occurrence_id: "original",
    recovery_warning: "optional",
  };
  expect(body(value)).toEqual({ title: "Synthetic" });
});
