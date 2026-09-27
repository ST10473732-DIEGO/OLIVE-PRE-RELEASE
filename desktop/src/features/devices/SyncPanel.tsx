import { useState } from "react";
import { call } from "../../services/api";
import type { Device, DevicesState } from "./types";
import { Segmented, ago, fullTime, sentence } from "./ui";

type Version = {
  kind: string;
  deleted: boolean;
  revision: string;
  updated_at: string;
  payload: Record<string, unknown>;
};
type Conflict = {
  id: string;
  peer: string;
  reason: string;
  local: Version | null;
  incoming: Version;
};
type Selection = { id: string; title: string; selected: boolean };
const domains = [
  ["sync.tasks", "Tasks"],
  ["sync.calendar", "Calendar"],
  ["sync.reminders", "Reminders"],
  ["sync.chat", "Selected chats"],
] as const;
function Fields({ version }: { version: Version | null }) {
  if (!version) return <p>No local record</p>;
  if (version.deleted) return <p>Deleted</p>;
  function entries(value: unknown, label = ""): [string, string][] {
    if (value === null || value === "") return [[label, "None"]];
    if (Array.isArray(value)) {
      if (!value.length) return [[label, "None"]];
      return value.flatMap((item, index) =>
        entries(item, `${label} ${index + 1}`),
      );
    }
    if (typeof value === "object") {
      return Object.entries(value as Record<string, unknown>).flatMap(
        ([key, item]) =>
          entries(
            item,
            [label, key.replaceAll("_", " ")].filter(Boolean).join(" · "),
          ),
      );
    }
    return [
      [
        label,
        typeof value === "boolean" ? (value ? "Yes" : "No") : String(value),
      ],
    ];
  }
  return (
    <dl>
      {entries(version.payload).map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
export function SyncPanel({
  device,
  data,
  refresh,
}: {
  device: Device;
  data: DevicesState;
  refresh: () => Promise<void>;
}) {
  const [error, setError] = useState("");
  const [conflicts, setConflicts] = useState<Conflict[] | null>(null);
  const [chats, setChats] = useState<Selection[] | null>(null);
  const [busy, setBusy] = useState(false);
  const status =
    device.sync || (data.sync?.peer === device.device_id ? data.sync : null);
  const running =
    status && ["running", "awaiting_approval"].includes(status.state);
  async function act(action: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sync could not complete");
    } finally {
      setBusy(false);
    }
  }
  const review = async () =>
    setConflicts(await call<Conflict[]>("connect.sync_conflicts", {}));
  const summary = status
    ? [
        {
          completed: "Last sync completed",
          running: "Syncing now",
          awaiting_approval: "Waiting for approval on the other device",
          failed: "Last sync failed",
          cancelled: "Last sync cancelled",
        }[status.state] || sentence(status.state),
        `${status.sent} sent`,
        `${status.received} received`,
        `${status.conflicts} ${status.conflicts === 1 ? "conflict" : "conflicts"}`,
      ].join(" · ") + (status.error ? ` · ${sentence(status.error)}` : "")
    : "";
  return (
    <section className="devices-card" aria-label="Sync">
      <header className="devices-card-head">
        <div>
          <h3>Sync</h3>
          <p>
            {status?.last_sync
              ? <>Last synced <span title={fullTime(status.last_sync)}>{ago(status.last_sync)}</span></>
              : "Choose what stays in sync with this device."}
          </p>
        </div>
        <div className="devices-card-actions">
          {running && (
            <button
              className="quiet"
              onClick={() => void act(() => call("connect.sync_cancel", {}))}
            >
              Cancel sync
            </button>
          )}
          <button
            disabled={
              !!running ||
              device.live?.state !== "online" ||
              device.trust_state !== "paired"
            }
            onClick={() =>
              void act(() =>
                call("connect.sync_now", { device_id: device.device_id }),
              )
            }
          >
            Sync now
          </button>
        </div>
      </header>
      <div className="devices-rows">
        {domains.map(([capability, label]) => (
          <div className="devices-row-line" key={capability}>
            <span className="devices-row-label">{label}</span>
            <Segmented
              label={`${label} sync`}
              disabled={device.trust_state !== "paired"}
              value={
                device.permissions?.find(
                  (p) => p.capability === capability && p.scope === null,
                )?.decision || "deny"
              }
              onChange={(decision) =>
                act(() =>
                  call("connect.permission", {
                    device_id: device.device_id,
                    capability,
                    decision,
                  }),
                )
              }
            />
          </div>
        ))}
      </div>
      {status && <p className="devices-status-line" role="status">{summary}</p>}
      {error && <p className="devices-inline-error" role="alert">{error}</p>}
      <div className="devices-card-foot">
        <button className="quiet" onClick={() => void act(review)}>Review conflicts</button>
        <button
          className="quiet"
          onClick={() =>
            void act(async () =>
              setChats(
                await call<Selection[]>("connect.sync_chats", {
                  device_id: device.device_id,
                }),
              ),
            )
          }
        >
          Select conversations
        </button>
        <span className="devices-hint">Reminders notify separately on each device.</span>
      </div>
        {chats && (
          <div className="devices-sub" aria-label="Selected conversations">
            <p className="devices-hint">
              Only selected conversations are shared with this device.
              Attachments do not transfer.
            </p>
            {chats.map((chat) => (
              <label className="devices-check-row" key={chat.id}>
                <input
                  type="checkbox"
                  checked={chat.selected}
                  disabled={busy}
                  onChange={(e) => {
                    const selected = e.target.checked;
                    void act(async () =>
                      setChats(
                        await call<Selection[]>("connect.sync_select", {
                          device_id: device.device_id,
                          conversation_id: chat.id,
                          selected,
                        }),
                      ),
                    );
                  }}
                />
                {chat.title}
              </label>
            ))}
          </div>
        )}
        {conflicts && (
          <div className="devices-sub" aria-label="Sync conflicts">
            {conflicts.length === 0 && <p className="devices-hint">No conflicts require review.</p>}
            {conflicts.map((conflict) => (
              <article className="devices-conflict" key={conflict.id}>
                <h4>{conflict.incoming.kind} conflict</h4>
                <p className="devices-hint">{sentence(conflict.reason)}</p>
                <h5>This device</h5>
                <Fields version={conflict.local} />
                <h5>
                  {data.devices.find((d) => d.device_id === conflict.peer)
                    ?.display_name || "Paired device"}
                </h5>
                <Fields version={conflict.incoming} />
                {(["local", "incoming"] as const).map((choice) => (
                  <button
                    key={choice}
                    disabled={
                      busy ||
                      (choice === "local" && !conflict.local) ||
                      (!!(
                        conflict.local?.deleted || conflict.incoming.deleted
                      ) &&
                        !(choice === "local"
                          ? conflict.local?.deleted
                          : conflict.incoming.deleted))
                    }
                    onClick={() =>
                      void act(async () => {
                        const result = await call<{ state: string }>(
                          "connect.sync_resolve",
                          { conflict_id: conflict.id, choice },
                        );
                        await review();
                        if (result.state === "review_again")
                          throw new Error(
                            "The local record changed. Review both versions again.",
                          );
                      })
                    }
                  >
                    {choice === "local"
                      ? "Keep this device"
                      : "Use incoming version"}
                  </button>
                ))}
              </article>
            ))}
          </div>
        )}
    </section>
  );
}
