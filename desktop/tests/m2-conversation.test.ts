import { describe, it, expect } from "vitest";
import { responseAfter } from "../src/services/conversation";
import type { Chat } from "../src/services/api";
describe("workspace response identity", () => {
  it("retains the response to its conversation turn instead of later unrelated replies", () => {
    const chat: Chat = {
      id: "chat",
      title: "Fixture",
      model: "fixture",
      draft: "",
      partial: "",
      generating: false,
      documents: [],
      messages: [
        { id: "before", role: "assistant", content: "Earlier", sources: [] },
        {
          id: "request",
          role: "user",
          content: "Workspace request",
          sources: [],
        },
        {
          id: "result",
          role: "assistant",
          content: "Workspace result",
          sources: [],
        },
        {
          id: "later",
          role: "assistant",
          content: "Later unrelated answer",
          sources: [],
        },
      ],
    };
    expect(responseAfter(chat, { chatId: "chat", after: "before" })?.id).toBe(
      "result",
    );
    expect(
      responseAfter(chat, { chatId: "other", after: "before" }),
    ).toBeUndefined();
    expect(
      responseAfter(chat, { chatId: "chat", after: "deleted-message" }),
    ).toBeUndefined();
  });
});
