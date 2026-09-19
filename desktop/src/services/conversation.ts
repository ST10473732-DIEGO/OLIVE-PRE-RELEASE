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
