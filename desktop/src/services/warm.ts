import { useRef } from "react";
import { call } from "./api";

const QUIET_MS = 30_000;

/** Preload the conversation's local model once the person starts typing, so the
 *  first reply does not wait for the model to load. At most once per 30 s. */
export function useWarmModel(chatId: string | undefined) {
  const last = useRef({ chatId: "", at: 0 });
  return () => {
    if (!chatId) return;
    const now = Date.now();
    if (last.current.chatId === chatId && now - last.current.at < QUIET_MS) return;
    last.current = { chatId, at: now };
    void call("chat.warm", { chat_id: chatId }).catch(() => undefined);
  };
}
