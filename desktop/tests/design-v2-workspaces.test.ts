import { describe, expect, it } from "vitest";
import { dayInZone, miniMonth, minutesInZone, placeDay, rangeTitle } from "../src/features/personal/calendarModel";
import { transferState } from "../src/features/devices/FilesPanel";

describe("Calendar time grid", () => {
  const zone = "Africa/Johannesburg";
  it("reads minutes and days in the profile zone, not the machine zone", () => {
    const instant = new Date("2026-09-23T12:30:00Z"); // 14:30 SAST
    expect(minutesInZone(instant, zone)).toBe(14 * 60 + 30);
    expect(dayInZone(instant, zone)).toBe("2026-09-23");
    expect(dayInZone(new Date("2026-09-23T23:30:00Z"), zone)).toBe("2026-09-24");
  });
  it("places events by their real times and puts overlaps side by side", () => {
    const events = [
      { id: "a", start: "2026-09-23T07:00:00Z", end: "2026-09-23T07:30:00Z" }, // 09:00–09:30
      { id: "b", start: "2026-09-23T12:30:00Z", end: "2026-09-23T14:00:00Z" }, // 14:30–16:00
      { id: "c", start: "2026-09-23T12:30:00Z", end: "2026-09-23T13:00:00Z" }, // 14:30–15:00
      { id: "d", start: "2026-09-24T07:00:00Z", end: "2026-09-24T08:00:00Z" }, // next day
    ];
    const placed = placeDay(events, "2026-09-23", zone);
    expect(placed.map((p) => p.item.id)).toEqual(["a", "b", "c"]);
    const a = placed.find((p) => p.item.id === "a")!;
    expect([a.top, a.bottom, a.lanes]).toEqual([540, 570, 1]);
    const b = placed.find((p) => p.item.id === "b")!;
    const c = placed.find((p) => p.item.id === "c")!;
    expect(b.lanes).toBe(2);
    expect(c.lanes).toBe(2);
    expect(new Set([b.lane, c.lane])).toEqual(new Set([0, 1]));
  });
  it("clips an event that crosses midnight to each day", () => {
    const late = [{ id: "x", start: "2026-09-23T20:00:00Z", end: "2026-09-24T00:00:00Z" }]; // 22:00–02:00
    expect(placeDay(late, "2026-09-23", zone)[0]).toMatchObject({ top: 1320, bottom: 1440 });
    expect(placeDay(late, "2026-09-24", zone)[0]).toMatchObject({ top: 0, bottom: 120 });
  });
  it("titles ranges and builds a Monday-first mini month", () => {
    const week = Array.from({ length: 7 }, (_, i) => new Date(2026, 8, 21 + i, 12));
    expect(rangeTitle("Week", week, "en-GB")).toBe("21 – 27 September 2026");
    const days = miniMonth(new Date(2026, 8, 23, 12));
    expect(days).toHaveLength(42);
    expect(days[0].getDay()).toBe(1);
    expect(days[0].getDate()).toBe(31);
  });
});

describe("OLIVE Inbox state vocabulary", () => {
  it("maps every backend state to a word and a tone, never colour alone", () => {
    expect(transferState({ state: "offered", direction: "incoming" })).toEqual({ label: "Waiting for you", tone: "ask" });
    expect(transferState({ state: "transferring", direction: "incoming" }).label).toBe("Receiving");
    expect(transferState({ state: "transferring", direction: "outgoing" }).label).toBe("Sending");
    expect(transferState({ state: "offered", direction: "outgoing" }).label).toBe("Ready to send");
    expect(transferState({ state: "verifying", direction: "incoming" })).toEqual({ label: "Verifying", tone: "computing" });
    expect(transferState({ state: "completed", direction: "incoming" })).toEqual({ label: "Received · verified", tone: "success" });
    expect(transferState({ state: "completed", direction: "outgoing" }).label).toBe("Sent · verified");
    expect(transferState({ state: "interrupted", direction: "incoming" })).toEqual({ label: "Interrupted", tone: "warning" });
    expect(transferState({ state: "failed", direction: "incoming" }).tone).toBe("error");
    expect(transferState({ state: "declined", direction: "incoming" }).label).toBe("Declined");
    expect(transferState({ state: "cancelled", direction: "outgoing" }).label).toBe("Cancelled");
  });
});
