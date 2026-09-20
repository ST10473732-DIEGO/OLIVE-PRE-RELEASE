import { useEffect, useState } from "react";
import { call, type Chat } from "../../services/api";

export interface ModelTarget {
  device_id: string;
  display_name: string;
  state: string;
  permission: "allow" | "ask" | "deny";
  busy: boolean;
  presets: Record<string, boolean>;
}

export function targetState(target: ModelTarget, preset: string): string {
  if (target.state === "revoked") return "Revoked";
  if (target.state !== "online") return "Offline";
  if (target.permission === "deny") return "Remote AI Off";
  if (!target.presets[preset]) return "Model unavailable";
  if (target.busy) return "Busy";
  return target.permission === "ask" ? "Online · Ask" : "Online";
}

export function TargetOptions({ targets, preset }: { targets: ModelTarget[]; preset: string }) {
  return <>{targets.map((target) => <option key={target.device_id} value={target.device_id}
    disabled={target.state === "revoked"}>
    {target.display_name} · {targetState(target, preset)}
  </option>)}</>;
}

export function RemoteTarget({ chat, busy, changed, report }: {
  chat: Chat; busy: boolean; changed: (chat: Chat) => void; report: (error: unknown) => void;
}) {
  const [targets, setTargets] = useState<ModelTarget[]>([]);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const value = await call<ModelTarget[]>("connect.model_targets", {});
        if (!stopped) setTargets(value);
      } catch {
        if (!stopped) setTargets((old) => old.map((t) => ({ ...t, state: "offline" })));
      }
      if (!stopped) timer = setTimeout(() => void poll(), 5000);
    };
    void poll();
    return () => { stopped = true; clearTimeout(timer); };
  }, []);
  return <label className="chat-preset">Run on
    <select aria-label="Run on" value={chat.run_on || ""} disabled={busy}
      onChange={(event) => void call<Chat>("chat.run_on", { chat_id: chat.id, device_id: event.target.value }).then(changed).catch(report)}>
      <option value="">This device</option>
      {chat.run_on && !targets.some((t) => t.device_id === chat.run_on) &&
        <option value={chat.run_on}>Selected device · Offline</option>}
      <TargetOptions targets={targets} preset={chat.preset || ""} />
    </select>
  </label>;
}

export function RemoteAttribution({ provider, complete = true }: {
  provider?: Chat["remote_provider"]; complete?: boolean;
}) {
  if (provider?.runtime !== "OLIVE Connect") return null;
  return <p className="small" role="status">{complete ? "Answered by" : "Thinking on"} {provider.device_name} · OLIVE {provider.preset?.toUpperCase()}</p>;
}
