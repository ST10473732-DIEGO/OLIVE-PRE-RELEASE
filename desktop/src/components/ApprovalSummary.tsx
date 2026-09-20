import type { Approval } from "../services/api";
export function ApprovalSummary({ approval }: { approval: Approval }) {
  if (approval.tool_name === "connect.request")
    return (
      <div className="connect-approval">
        <p className="ws-eyebrow">OLIVE Connect request</p>
        <h3>{String(approval.arguments.source_name || "Paired device")}</h3>
        <div className="ws-panel">
          <p className="ws-eyebrow">Requesting</p>
          <strong>{approval.summary}</strong>
          {approval.arguments.studio ? <>
            <p>{String(approval.arguments.target_name)}</p>
            <p>{String((approval.arguments.studio as Record<string, unknown>).path || "Current project configuration")}</p>
            <p>One guarded operation on this shared workspace.</p>
          </> : approval.arguments.inference ? <>
            <p>OLIVE {String((approval.arguments.inference as Record<string, unknown>).preset).toUpperCase()}</p>
            <p>{String((approval.arguments.inference as Record<string, unknown>).message_count)} visible messages · {String((approval.arguments.inference as Record<string, unknown>).input_bytes)} bytes of context</p>
            <p>Tool-free text inference only. No access to this device’s private context.</p>
          </> : approval.arguments.file ? (
            <>
              <p>
                {String(
                  (approval.arguments.file as Record<string, unknown>).name,
                )}
              </p>
              <p>
                {String(
                  (approval.arguments.file as Record<string, unknown>).size,
                )}{" "}
                bytes ·{" "}
                {String(
                  (approval.arguments.file as Record<string, unknown>).mime,
                )}
              </p>
              <p>
                Inert file transfer only. Receipt does not open, execute or
                import the file.
              </p>
            </>
          ) : (
            <p>
              {String(approval.arguments.capability).startsWith("sync.")
                ? "This exact structured record exchange."
                : "One read-only operation. No message content or inference access."}
            </p>
          )}
        </div>
        <p>On: {String(approval.arguments.target_name || "This device")}</p>
        <p className="muted">
          Allow once applies only to this exact request. The saved permission
          stays Ask.
        </p>
      </div>
    );
  const targets = approval.presentation?.targets || approval.targets;
  return (
    <>
      <div className="approval-headline">
        <span className="badge" data-tone="warning">
          {approval.tool_name} · risk {approval.risk_level}
        </span>
        <h3>{approval.presentation?.action || approval.summary}</h3>
      </div>
      <dl className="approval-summary">
        <dt>Action</dt>
        <dd>{approval.presentation?.action || approval.summary}</dd>
        <dt>Target</dt>
        <dd>
          {targets.length
            ? targets.join(", ")
            : "No target provided; inspect the action before approving."}
        </dd>
        <dt>Content</dt>
        <dd className="approval-content">
          {approval.presentation?.content ||
            "No content summary supplied. Review technical details before approving."}
        </dd>
        <dt>Scope</dt>
        <dd>
          {approval.presentation?.scope ||
            `One ${approval.tool_name} action; risk level ${approval.risk_level}.`}
        </dd>
        <dt>Consequence</dt>
        <dd className="approval-consequence">
          {approval.presentation?.consequence ||
            "This authorises the action described above. Cancel to prevent it from starting."}
        </dd>
      </dl>
      <details>
        <summary>Technical details</summary>
        <pre>{JSON.stringify(approval.arguments, null, 2)}</pre>
      </details>
    </>
  );
}
