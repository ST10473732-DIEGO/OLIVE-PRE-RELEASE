import { useState } from "react";
import { call } from "../../services/api";
import type { Device } from "./types";
const terminal = new Set([
  "completed",
  "failed",
  "interrupted",
  "declined",
  "cancelled",
  "dismissed",
]);
export function FilesPanel({
  device,
  refresh,
}: {
  device: Device;
  refresh: () => Promise<void>;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "File transfer failed");
    } finally {
      setBusy(false);
    }
  }
  const paired = device.trust_state === "paired";
  const send =
    device.permissions?.find(
      (p) => p.capability === "files.send" && p.scope === null,
    )?.decision || "deny";
  return (
    <section className="devices-sync" aria-label="File transfers">
      <h3>Files · OLIVE Inbox</h3>
      <p>
        Received files stay inert in OLIVE until you choose Save. Maximum 64 MiB
        per file. Transfer verification is not a malware check.
      </p>
      {error && <p role="alert">{error}</p>}
      <button
        disabled={busy || !paired || send === "deny" || !device.live?.encrypted}
        onClick={() =>
          void act(() =>
            window.olive.fileAction({
              action: "connect-file-select",
              device_id: device.device_id,
            }),
          )
        }
      >
        Send file
      </button>
      {send === "deny" && (
        <p>Send selected files is Off. Change it in Permissions to send.</p>
      )}
      {(device.transfers || []).map((t) => (
        <article className="ws-panel" key={t.transfer_id}>
          <strong>{t.metadata.name}</strong>
          <p>
            {t.metadata.size.toLocaleString()} bytes · {t.metadata.mime}
          </p>
          <p>
            {t.direction === "incoming" ? "From" : "To"} {device.display_name} ·{" "}
            {t.state === "completed"
              ? t.direction === "incoming"
                ? "Received · Transfer verified"
                : "Sent · Transfer verified"
              : t.state.replaceAll("_", " ")}
          </p>
          {!terminal.has(t.state) && (
            <>
              <progress
                aria-label={`${t.metadata.name} transfer progress`}
                max={Math.max(1, t.metadata.size)}
                value={t.received_size}
              />
              <p>
                {t.received_size.toLocaleString()} /{" "}
                {t.metadata.size.toLocaleString()} bytes{" "}
                {device.live?.encrypted ? "· Encrypted · Local" : ""}
              </p>
            </>
          )}
          {t.error && <p>{t.error.replaceAll("_", " ")}</p>}
          {t.direction === "outgoing" && t.state === "offered" && (
            <button
              disabled={busy || !paired}
              onClick={() =>
                void act(() =>
                  call("connect.file_start", { transfer_id: t.transfer_id }),
                )
              }
            >
              Send reviewed file
            </button>
          )}
          {!terminal.has(t.state) && (
            <button
              disabled={busy}
              onClick={() =>
                void act(() =>
                  call("connect.file_cancel", { transfer_id: t.transfer_id }),
                )
              }
            >
              Cancel transfer
            </button>
          )}
          {t.direction === "incoming" && t.state === "completed" && (
            <>
              <button
                disabled={busy}
                onClick={() =>
                  void act(() =>
                    window.olive.fileAction({
                      action: "connect-file-save",
                      transfer_id: t.transfer_id,
                    }),
                  )
                }
              >
                Save
              </button>
              <button
                disabled={busy}
                onClick={() =>
                  void act(() =>
                    call("connect.file_dismiss", {
                      transfer_id: t.transfer_id,
                    }),
                  )
                }
              >
                Dismiss from Inbox
              </button>
            </>
          )}
        </article>
      ))}
    </section>
  );
}
