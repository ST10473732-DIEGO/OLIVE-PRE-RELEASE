import { describe, expect, it } from "vitest";
import { whenLabel } from "../src/services/when";

describe("whenLabel", () => {
  const now = new Date(2026, 8, 25, 21, 0);
  const time = (d: Date) => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  it("names today and yesterday, and keeps unreadable values", () => {
    expect(whenLabel("2026-09-25T20:20:03", now)).toBe(`Today ${time(new Date(2026, 8, 25, 20, 20))}`);
    expect(whenLabel("2026-09-24T14:44:04", now)).toBe(`Yesterday ${time(new Date(2026, 8, 24, 14, 44))}`);
    expect(whenLabel("not a date", now)).toBe("not a date");
  });
  it("adds the year only for another year", () => {
    expect(whenLabel("2026-09-20T09:00:00", now)).not.toMatch(/2026/);
    expect(whenLabel("2025-12-31T09:00:00", now)).toMatch(/2025/);
  });
});
