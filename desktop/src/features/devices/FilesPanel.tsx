import { useState } from "react";
import { ArrowDownLeft, ArrowUpRight, CheckCircle2, CircleSlash, FileIcon, Hand, Loader2, ShieldCheck, TriangleAlert, XCircle } from "lucide-react";
import { call } from "../../services/api";
import type { Device, Transfer } from "./types";

/** V2 Inbox state vocabulary (Design System V2 §14.9): backend state → a
 *  word, a tone and an icon. Status is never colour alone. */
export function transferState(t: Pick<Transfer, "state" | "direction">): { label: string; tone: "ask" | "computing" | "success" | "warning" | "error" | "neutral" } {
  switch (t.state) {
    case "offered":
    case "awaiting_approval":
      return { label: t.direction === "incoming" ? "Waiting for you" : "Waiting to send", tone: "ask" };
    case "accepted":
    case "transferring":
      return { label: t.direction === "incoming" ? "Receiving" : "Sending", tone: "computing" };
    case "verifying":
      return { label: "Verifying · SHA-256", tone: "computing" };
    case "completed":
      return { label: "Complete · verified", tone: "success" };
    case "interrupted":
      return { label: "Interrupted · partial data removed", tone: "warning" };
    case "failed":
      return { label: "Failed", tone: "error" };
    case "declined":
      return { label: "Declined", tone: "neutral" };
    case "cancelled":
      return { label: "Cancelled", tone: "neutral" };
    default:
      return { label: t.state.replaceAll("_", " "), tone: "neutral" };
  }
}
const ICONS = { ask: Hand, computing: Loader2, success: CheckCircle2, warning: TriangleAlert, error: XCircle, neutral: CircleSlash };
const size = (bytes: number) =>
  bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : bytes >= 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${bytes} B`;
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
      <div className="transfer-title">
        <h3>Files · OLIVE Inbox</h3>
      </div>
      <p className="notice" role="note">
        Received files stay inert: OLIVE never opens, previews or runs them, and
        keeps them until you choose Save. Complete means the byte count and
        SHA-256 matched. Transfers are never resumed automatically. Maximum 64
        MiB per file. Transfer verification is not a malware check.
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
      {(device.transfers || []).map((t) => {
        const state = transferState(t);
        const Icon = ICONS[state.tone];
        return (
        <article className="transfer-row" key={t.transfer_id} data-tone={state.tone}>
          <div className="transfer-head">
            <FileIcon size={15} aria-hidden="true" />
            <strong>{t.metadata.name}</strong>
            <span className="transfer-size">{size(t.metadata.size)}</span>
            <span className="transfer-dir">
              {t.direction === "incoming" ? <ArrowDownLeft size={13} aria-hidden="true" /> : <ArrowUpRight size={13} aria-hidden="true" />}
              {t.direction === "incoming" ? "From" : "To"} {device.display_name}
            </span>
            <span className="ws-pill transfer-state" data-tone={state.tone === "ask" || state.tone === "warning" ? "warning" : state.tone === "computing" ? "ai" : state.tone === "neutral" ? undefined : state.tone}>
              <Icon size={12} aria-hidden="true" className={state.tone === "computing" && t.state !== "verifying" ? "spin" : undefined} />
              {state.label}
            </span>
          </div>
          <p className="transfer-detail">
            {t.metadata.mime} ·{" "}
            {t.state === "completed"
              ? t.direction === "incoming"
                ? "Received · Transfer verified"
                : "Sent · Transfer verified"
              : t.state.replaceAll("_", " ")}
            {t.state === "completed" && <ShieldCheck size={12} aria-hidden="true" className="transfer-verified" />}
          </p>
          {!terminal.has(t.state) && (
            <>
              <progress
                aria-label={`${t.metadata.name} transfer progress`}
                max={Math.max(1, t.metadata.size)}
                value={t.received_size}
              />
              <p className="transfer-detail">
                {size(t.received_size)} of {size(t.metadata.size)}
                {device.live?.encrypted ? " · Encrypted · Local" : ""}
              </p>
            </>
          )}
          {t.error && <p className="transfer-error">{t.error.replaceAll("_", " ")}</p>}
          <div className="transfer-actions">
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
          </div>
        </article>
        );
      })}
      {!(device.transfers || []).length && <p className="transfer-empty">No transfers with {device.display_name} yet.</p>}
    </section>
  );
}
