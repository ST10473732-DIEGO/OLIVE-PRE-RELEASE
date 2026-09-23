import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { activityLabel, attentionItems, countdown, firstRunSteps, greeting } from "../src/features/home/homeModel";
import { messageAttribution } from "../src/features/chat/RemoteTarget";
import { Markdown } from "../src/components/Markdown";
import type { Approval, Chat, Snapshot } from "../src/services/api";

describe("Home V2 model", () => {
  const approval = { id: "a1", fingerprint: "f", summary: "Create event", tool_name: "calendar.create", risk_level: "low", targets: [], arguments: {} } as Approval;
  it("builds Needs attention only from real approvals, reminders and pending drafts", () => {
    expect(attentionItems([], [], null)).toEqual([]);
    const chat = { id: "c", title: "Budget", pending_draft: { state: "awaiting_confirmation" } } as unknown as Chat;
    const items = attentionItems([approval, { ...approval, id: "a2", tool_name: "connect.request" }], [
      { id: "d1", title: "Water seedlings", target_kind: "task", target_id: "t", due_at: "" },
    ], chat);
    expect(items.map((i) => i.kind)).toEqual(["approval", "approval", "reminder", "pending"]);
    expect(items[1].detail).toContain("Connect · Ask");
    expect(items[3].detail).toContain("nothing runs until you confirm");
  });
  it("describes running work from the activity record, never invented", () => {
    const chats = [{ id: "c", title: "Irrigation" }] as Snapshot["chats"];
    expect(activityLabel({ method: "interaction.submit", chat_id: "c" }, chats).title).toBe('Answering in "Irrigation"');
    expect(activityLabel({ method: "project.test" }, chats)).toEqual({ title: "Test in Studio", detail: "Studio" });
  });
  it("counts down to the next event and names past starts honestly", () => {
    const now = new Date("2026-09-23T14:05:00Z");
    expect(countdown("2026-09-23T14:30:00Z", now)).toBe("in 25 min");
    expect(countdown("2026-09-23T16:10:00Z", now)).toBe("in 2 h 5 min");
    expect(countdown("2026-09-23T14:05:00Z", now)).toBe("now");
    expect(countdown("2026-09-23T13:55:00Z", now)).toBe("started 10 min ago");
    expect(countdown("not a date", now)).toBe("");
    expect(greeting(new Date(2026, 8, 23, 9))).toBe("Good morning");
  });
  it("reports first-run steps from real Ollama and preset state", () => {
    const offline = firstRunSteps("Ollama unavailable: refused", [], 0);
    expect(offline.find((s) => s.id === "ollama")?.done).toBe(false);
    const ready = firstRunSteps("Ollama ready", [{ id: "normal", status: "Ready" }] as Snapshot["presets"], 1);
    expect(ready.every((s) => s.done)).toBe(true);
  });
});

describe("Chat V2 attribution and code blocks", () => {
  it("attributes local and remote turns truthfully from the recorded provider", () => {
    expect(messageAttribution(undefined)).toBe("");
    expect(messageAttribution({ runtime: "Ollama", preset: "fast" })).toBe("OLIVE FAST · This device");
    expect(messageAttribution({ runtime: "OLIVE Connect", preset: "max", device_name: "Gaming PC" })).toBe("Answered by Gaming PC · OLIVE MAX");
    // A remote answer is never presented as local.
    expect(messageAttribution({ runtime: "OLIVE Connect", preset: "max", device_name: "Gaming PC" })).not.toContain("This device");
  });
  it("renders code blocks with a language header and a Copy action, and no active HTML", () => {
    const html = renderToStaticMarkup(createElement(Markdown, { text: "```python\nprint('hi')\n```\n\n<script>x()</script>" }));
    expect(html).toContain("code-block");
    expect(html).toContain(">python<");
    expect(html).toContain("Copy python code");
    expect(html).not.toContain("<script>");
  });
});
