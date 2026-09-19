import type { Approval } from "../services/api";
export function ApprovalSummary({ approval }: { approval: Approval }) {
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
