// Pure presentation logic for Home V2. Everything here is derived from real
// runtime records; nothing is invented, estimated or padded out.
import type { Approval, Chat, Snapshot } from "../../services/api";

export interface AttentionItem {
  id: string;
  kind: "approval" | "reminder" | "pending";
  title: string;
  detail: string;
}

export interface DueReminder {
  id: string;
  title: string;
  target_kind: string;
  target_id: string;
  due_at: string;
}

/** "Needs attention": approvals waiting outside the model, delivered
 *  reminders, and a pending action a conversation drafted. */
export function attentionItems(approvals: Approval[], reminders: DueReminder[], chat: Chat | null): AttentionItem[] {
  const items: AttentionItem[] = approvals.map((approval) => ({
    id: `approval:${approval.id}`,
    kind: "approval",
    title: approval.presentation?.action || approval.summary || "An action needs your approval",
    detail:
      approval.tool_name === "connect.request"
        ? "Connect · Ask · a paired device is waiting"
        : "Approval · OLIVE is waiting for you",
  }));
  for (const reminder of reminders)
    items.push({
      id: `reminder:${reminder.id}`,
      kind: "reminder",
      title: reminder.title,
      detail: reminder.target_kind ? `Reminder · linked ${reminder.target_kind}` : "Reminder",
    });
  if (chat?.pending_draft && chat.pending_draft.state)
    items.push({
      id: `pending:${chat.id}`,
      kind: "pending",
      title: `Pending action in "${chat.title}"`,
      detail: `Chat · ${chat.pending_draft.state.replaceAll("_", " ")} · nothing runs until you confirm`,
    });
  return items;
}

/** A human description of a real runtime activity item. */
export function activityLabel(item: { method: string; chat_id?: string }, chats: Snapshot["chats"]): { title: string; detail: string } {
  const chat = item.chat_id ? chats.find((c) => c.id === item.chat_id) : undefined;
  const where = chat ? ` in "${chat.title}"` : "";
  const [domain, action = ""] = item.method.split(".");
  if (domain === "interaction") return { title: `Answering${where}`, detail: "Chat" };
  if (domain === "research") return { title: `Researching${where}`, detail: "Research" };
  if (domain === "agent") return { title: "Working on an objective", detail: "Agent" };
  if (domain === "project" || domain === "studio")
    return { title: `${action ? action[0].toUpperCase() + action.slice(1).replaceAll("_", " ") : "Working"} in Studio`, detail: "Studio" };
  if (domain === "knowledge") return { title: "Indexing knowledge", detail: "Knowledge" };
  return { title: item.method.replaceAll("_", " ").replace(".", " · "), detail: domain[0]?.toUpperCase() + domain.slice(1) };
}

/** "in 25 min", "in 2 h 5 min", "now", "started 10 min ago". */
export function countdown(start: string, now: Date): string {
  const at = new Date(start).getTime();
  if (Number.isNaN(at)) return "";
  const minutes = Math.round((at - now.getTime()) / 60000);
  if (minutes === 0) return "now";
  const span = (value: number) => {
    const h = Math.floor(value / 60);
    const m = value % 60;
    return h ? `${h} h${m ? ` ${m} min` : ""}` : `${m} min`;
  };
  return minutes > 0 ? `in ${span(minutes)}` : `started ${span(-minutes)} ago`;
}

export function greeting(now: Date): string {
  const hour = now.getHours();
  return hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

/** First-run checklist. Only facts the runtime reports; each step is either
 *  done or has a real next action. */
export function firstRunSteps(ollama: string | undefined, presets: Snapshot["presets"], pairedDevices: number) {
  const text = (ollama || "").trim();
  const reachable = text.startsWith("Ollama ready") || text.includes("No models installed");
  const normal = presets?.find((p) => p.id === "normal");
  return [
    { id: "running", label: "OLIVE is running", done: true },
    { id: "ollama", label: "Start Ollama (the local model service)", done: reachable },
    { id: "model", label: "Install the OLIVE NORMAL model", done: normal?.status === "Ready" },
    { id: "pair", label: "Pair a device (optional)", done: pairedDevices > 0, optional: true },
  ];
}
