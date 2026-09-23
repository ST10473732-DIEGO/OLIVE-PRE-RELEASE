import type { Chat } from "./api";
export interface ConversationAnchor {
  chatId: string;
  after: string;
}
export function responseAfter(chat: Chat, anchor?: ConversationAnchor) {
  if (!anchor || anchor.chatId !== chat.id) return undefined;
  const index = anchor.after
    ? chat.messages.findIndex((message) => message.id === anchor.after)
    : -1;
  if (anchor.after && index < 0) return undefined;
  return chat.messages
    .slice(index + 1)
    .find((message) => message.role === "assistant");
}

/** Every message after an anchor: the Studio assistant's own thread inside
 *  the shared conversation. */
export function threadAfter(chat: Chat, anchor?: ConversationAnchor) {
  if (!anchor || anchor.chatId !== chat.id) return [];
  const index = anchor.after ? chat.messages.findIndex((message) => message.id === anchor.after) : -1;
  if (anchor.after && index < 0) return [];
  return chat.messages.slice(index + 1);
}

export interface StudioContextParts {
  problems?: string;
  failingTest?: string;
  changes?: string;
}
/** The request text plus only the context the person switched on. Nothing
 *  else is attached: no project map, no other files. */
export function withStudioContext(text: string, parts: StudioContextParts): string {
  const sections: string[] = [text.trim()];
  if (parts.problems) sections.push(`Problems reported in this workspace:\n${parts.problems}`);
  if (parts.failingTest) sections.push(`Failing test:\n${parts.failingTest}`);
  if (parts.changes) sections.push(`Uncommitted changes:\n${parts.changes}`);
  return sections.join("\n\n").slice(0, 24000);
}
