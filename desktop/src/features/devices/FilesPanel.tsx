import { useState } from "react";
import { ArrowDownLeft, ArrowUpRight, CheckCircle2, CircleSlash, FileIcon, Hand, Loader2, TriangleAlert, Upload, XCircle } from "lucide-react";
import { call } from "../../services/api";
import type { Device, Transfer } from "./types";
import { Confirm, sentence } from "./ui";

/** V2 Inbox state vocabulary (Design System V2 §14.9): backend state → a
 *  word, a tone and an icon. Status is never colour alone. */
export function transferState(t: Pick<Transfer, "state" | "direction">): { label: string; tone: "ask" | "computing" | "success" | "warning" | "error" | "neutral" } {
  const incoming = t.direction === "incoming";
  switch (t.state) {
    case "offered":
    case "awaiting_approval":
      return { label: incoming ? "Waiting for you" : "Ready to send", tone: "ask" };
    case "accepted":
    case "transferring":
      return { label: incoming ? "Receiving" : "Sending", tone: "computing" };
    case "verifying":
      return { label: "Verifying", tone: "computing" };
    case "completed":
      return { label: incoming ? "Received · verified" : "Sent · verified", tone: "success" };
    case "interrupted":
      return { label: "Interrupted", tone: "warning" };
    case "failed":
      return { label: "Failed", tone: "error" };
    case "declined":
      return { label: "Declined", tone: "neutral" };
    case "cancelled":
      return { label: "Cancelled", tone: "neutral" };
    default:
      return { label: sentence(t.state), tone: "neutral" };
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
/** Why a transfer ended, only when that adds something to its state word. */
const reason = (t: Transfer) =>
  t.error && ["failed", "interrupted"].includes(t.state) ? sentence(t.error) : "";

export function FilesPanel({
  device,
  refresh,
}: {
  device: Device;
  refresh: () => Promise<void>;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [clearing, setClearing] = useState(false);
  async function act(action: () => Promise<unknown>) {
    if (busy) return;
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
  const transfers = (device.transfers || []).filter((t) => t.state !== "dismissed");
  const finished = transfers.filter((t) => terminal.has(t.state));
  const unsaved = finished.filter((t) => t.direction === "incoming" && t.state === "completed").length;
  return (
    <section className="devices-card" aria-label="File transfers">
      <header className="devices-card-head">
        <div>
          <h3>Files</h3>
          <p>
            {!paired
              ? "Transfers from before this device was revoked."
              : send === "deny"
                ? "Sending is Off. Turn on Send selected files in Permissions."
                : "Received files wait in OLIVE Inbox, unopened, until you save them."}
          </p>
        </div>
        <div className="devices-card-actions">
          <button
            className="quiet"
            disabled={!finished.length}
            onClick={() => setClearing(true)}
          >
            Clear
          </button>
          {paired && <button
            disabled={send === "deny" || !device.live?.encrypted}
            onClick={() =>
              void act(() =>
                window.olive.fileAction({
                  action: "connect-file-select",
                  device_id: device.device_id,
                }),
              )
            }
          >
            <Upload size={14} aria-hidden="true" />
            Send file
          </button>}
        </div>
      </header>
      {error && <p className="devices-inline-error" role="alert">{error}</p>}
      {transfers.length ? (
        <ul className="transfer-list">
          {transfers.map((t) => {
            const state = transferState(t);
            const Icon = ICONS[state.tone];
            const active = !terminal.has(t.state);
            const why = reason(t);
            return (
              <li key={t.transfer_id}>
                <article className="transfer-row" data-tone={state.tone}>
                  <span className="transfer-icon" aria-hidden="true">
                    <FileIcon size={16} />
                  </span>
                  <div className="transfer-main">
                    <strong title={t.metadata.name}>{t.metadata.name}</strong>
                    <span className="transfer-meta">
                      {t.direction === "incoming" ? <ArrowDownLeft size={12} aria-hidden="true" /> : <ArrowUpRight size={12} aria-hidden="true" />}
                      {active
                        ? `${size(t.received_size)} of ${size(t.metadata.size)}`
                        : size(t.metadata.size)}
                      {" · "}
                      {t.direction === "incoming" ? "From" : "To"} {device.display_name}
                      {why && <span className="transfer-why"> · {why}</span>}
                    </span>
                    {active && (
                      <progress
                        aria-label={`${t.metadata.name} transfer progress`}
                        max={Math.max(1, t.metadata.size)}
                        value={t.received_size}
                      />
                    )}
                  </div>
                  <span className="devices-state" data-tone={state.tone}>
                    <Icon size={12} aria-hidden="true" className={state.tone === "computing" ? "spin" : undefined} />
                    {state.label}
                  </span>
                  <div className="transfer-actions">
                    {t.direction === "outgoing" && t.state === "offered" && (
                      <button
                        disabled={!paired}
                        onClick={() =>
                          void act(() =>
                            call("connect.file_start", { transfer_id: t.transfer_id }),
                          )
                        }
                      >
                        Send reviewed file
                      </button>
                    )}
                    {active && (
                      <button
                        className="quiet"
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
                          className="quiet"
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
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="devices-empty-line">No files sent or received yet.</p>
      )}
      <details className="devices-fineprint">
        <summary>How OLIVE handles files</summary>
        <p>
          OLIVE never opens, previews or runs received files. A transfer is
          verified when its size and SHA-256 match; that is not a malware
          check. Transfers never resume automatically. Maximum 64 MiB per file.
        </p>
      </details>
      <Confirm
        open={clearing}
        onOpenChange={setClearing}
        title="Clear finished files"
        action="Clear files"
        onConfirm={async () => {
          await call("connect.files_clear", { device_id: device.device_id });
          await refresh();
        }}
      >
        <p>
          Removes {finished.length === 1 ? "1 finished transfer" : `${finished.length} finished transfers`} with {device.display_name} from this list.
          Transfers in progress stay.
        </p>
        {unsaved > 0 && (
          <p>
            <strong>{unsaved === 1 ? "1 received file hasn’t" : `${unsaved} received files haven’t`} been saved</strong> and will be deleted from OLIVE Inbox.
          </p>
        )}
      </Confirm>
    </section>
  );
}
