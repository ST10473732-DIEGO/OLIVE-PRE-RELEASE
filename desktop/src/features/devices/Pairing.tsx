import { Fragment, useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import * as Dialog from "@radix-ui/react-dialog";
import { call } from "../../services/api";
import type { PairingState } from "./types";
export function Pairing({
  initial,
  close,
  refresh,
}: {
  initial: PairingState;
  close: () => void;
  refresh: () => void;
}) {
  const [state, setState] = useState(initial),
    [now, setNow] = useState(Date.now()),
    [observed, setObserved] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const value = await call<PairingState>("connect.pair_status", {
          session_id: initial.session_id,
        });
        if (!stopped) {
          setState(value);
          setNow(Date.now());
          if (
            [
              "completed",
              "cancelled",
              "expired",
              "failed",
              "interrupted",
            ].includes(value.state)
          )
            return;
        }
      } catch {
        if (!stopped)
          setError(
            "Pairing status unavailable. Cancel and create a new offer.",
          );
      }
      if (!stopped) timer = setTimeout(() => void poll(), 1000);
    };
    timer = setTimeout(() => void poll(), 1000);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [initial.session_id]);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, []);
  const seconds = Math.max(0, Math.ceil(state.expires_at - now / 1000));
  const expired =
    state.state === "expired" ||
    (!["completed", "cancelled", "failed", "interrupted"].includes(
      state.state,
    ) &&
      seconds === 0);
  const cancel = async () => {
    if (!["completed", "cancelled", "failed", "expired"].includes(state.state))
      await call("connect.pair_cancel", { session_id: state.session_id }).catch(
        () => {},
      );
    refresh();
    close();
  };
  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open) void cancel();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="devices-overlay" />
        <Dialog.Content className="devices-modal">
          <Dialog.Title>
            {state.state === "completed"
              ? "Device paired"
              : state.state === "interrupted"
                ? "Pairing interrupted"
                : expired
                  ? "Pairing expired"
                  : state.comparison
                    ? "Compare both devices"
                    : "Connect a device"}
          </Dialog.Title>
          <Dialog.Description>
            {state.state === "completed"
              ? "Pairing confirms identity. All permissions start Off. The device remains offline until it connects."
              : "Compare the complete value on both intended OLIVE devices before confirming."}
          </Dialog.Description>
          {error && <p role="alert">{error}</p>}
          {!expired && state.offer && (
            <>
              <div className="devices-qr">
                <QRCodeSVG value={state.offer} size={248} marginSize={4} />
              </div>
              <p className="devices-countdown">
                Expires in {Math.floor(seconds / 60)}:
                {String(seconds % 60).padStart(2, "0")}
              </p>
              <p>Waiting for another OLIVE device…</p>
              <p className="muted">
                On the other desktop, choose Pair device and paste this public
                offer. There is no OLIVE Mobile app yet.
              </p>
              <button
                onClick={() =>
                  void navigator.clipboard
                    .writeText(state.offer!)
                    .catch(() => setError("Could not copy the public offer."))
                }
              >
                Copy public offer
              </button>
            </>
          )}
          {state.state === "interrupted" && (
            <p role="alert">
              {state.error === "pairing_unreachable"
                ? "Could not reach pairing device. Check that both devices selected the same local network. If the host firewall blocks pairing, allow OLIVE on that private network for this session; no firewall settings are changed automatically."
                : "Pairing interrupted. The peer may have cancelled. Start a new session, or exchange completion codes if both users already confirmed."}
            </p>
          )}
          {state.state === "cancelled" && <p>Pairing cancelled.</p>}
          {state.completion_code && (
            <details>
              <summary>Recover confirmed pairing</summary>
              <p>
                If completion was interrupted, exchange these public completion
                codes using Pair device. Recovery requires the original local
                confirmation on each desktop.
              </p>
              <button
                onClick={() =>
                  void navigator.clipboard
                    .writeText(state.completion_code!)
                    .catch(() => setError("Could not copy completion code."))
                }
              >
                Copy completion code
              </button>
            </details>
          )}
          {expired && (
            <p>
              The offer is invalid. Close this window and create a new pairing
              session.
            </p>
          )}
          {state.state === "failed" && (
            <p role="alert">Pairing failed. A new session is required.</p>
          )}
          {!expired && state.comparison && (
            <>
              <p>Candidate: {state.candidate_name || state.candidate_id}</p>
              <p>
                Compare this value on both devices. Expires{" "}
                {new Date(state.expires_at * 1000).toLocaleTimeString()}.
              </p>
              <code className="devices-comparison">
                {state.comparison.split(":").map((part, index, parts) => (
                  <Fragment key={index}>
                    {part}
                    {index < parts.length - 1 && (
                      <>
                        <span>:</span>
                        <wbr />
                      </>
                    )}
                  </Fragment>
                ))}
              </code>
              <button
                onClick={() =>
                  void navigator.clipboard
                    .writeText(state.comparison!)
                    .catch(() => setError("Could not copy comparison."))
                }
              >
                Copy comparison value
              </button>
              <details>
                <summary>Candidate public fingerprint</summary>
                <code className="devices-comparison">{state.fingerprint}</code>
              </details>
              {state.state === "confirmed" ? (
                <p>Waiting for the other device’s confirmation…</p>
              ) : (
                <label>
                  Value observed on the other device
                  <input
                    value={observed}
                    maxLength={256}
                    onChange={(e) => setObserved(e.target.value)}
                    autoComplete="off"
                  />
                </label>
              )}
            </>
          )}
          <div className="devices-modal-actions">
            <button onClick={() => void cancel()}>
              {state.state === "completed" ? "Done" : "Cancel"}
            </button>
            {state.comparison && state.state === "fingerprint_pending" && (
              <button
                className="primary"
                disabled={expired || !observed || busy}
                onClick={() => {
                  setBusy(true);
                  void call<PairingState>("connect.pair_confirm", {
                    session_id: state.session_id,
                    compared_value: observed.trim(),
                  })
                    .then(setState)
                    .catch(() => {
                      setError(
                        "Comparison did not match or the session expired. Pairing cannot continue.",
                      );
                      setState((s) => ({
                        ...s,
                        state: "failed",
                        comparison: undefined,
                      }));
                    })
                    .finally(() => setBusy(false));
                }}
              >
                Values match
              </button>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
