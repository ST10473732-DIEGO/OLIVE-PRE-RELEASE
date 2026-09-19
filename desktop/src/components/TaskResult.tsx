import type { Validation } from "../services/studioOutput";
const names: Record<string, string> = {
  completed: "Completed",
  cancelled: "Cancelled",
  blocked: "Blocked",
  failed: "Failed",
  awaiting_approval: "Awaiting approval",
  running: "Working",
  cancelling: "Stopping",
  not_attempted: "Not attempted",
  outcome_uncertain: "Outcome uncertain",
  partially_completed: "Partially completed",
};
export function TaskResult({ value }: { value: Validation }) {
  return (
    <div className="task-result" role="status" data-task-state={value.state}>
      <strong>{names[value.state] || "Status unavailable"}</strong>
      <p>{value.summary}</p>
      {value.state === "cancelled" &&
        value.results.every((r) => r.state === "not_attempted") && (
          <p>Test commands were not started.</p>
        )}
      {value.results.length > 0 && (
        <details>
          <summary>Step results</summary>
          <ul>
            {value.results.map((r, i) => (
              <li key={r.session_id || i}>
                {r.name}: {names[r.state || ""] || "Status unavailable"}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
