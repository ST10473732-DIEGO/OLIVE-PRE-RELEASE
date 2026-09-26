import { OliveLogo } from "./OliveLogo";

/** States in which OLIVE is really doing something; only these animate. */
export const activeState = (state: string) => ["Thinking", "Working", "Researching"].includes(state);
const ATTENTION = ["Approval required", "Paused", "Pausing", "Degraded", "Error"];

// The Core is the OLIVE mark with its state: a ring turns around it while OLIVE
// works, a badge marks attention, and at rest it breathes gently. On Welcome it
// draws itself in. All motion is CSS, so Reduce Motion, hidden windows and
// paused animations need no script.
export function OliveCore({
  state = "Ready",
  variant = "compact",
}: {
  state?: string;
  variant?: "welcome" | "compact";
}) {
  const attention = ATTENTION.includes(state);
  return (
    <div
      className={`core ${variant === "welcome" ? "core-large" : ""} ${activeState(state) ? "core-active" : ""}`}
      role="img"
      aria-label={`OLIVE: ${state}`}
      data-state={state}
    >
      <OliveLogo className="core-logo" />
      {activeState(state) && <span className="core-ring" aria-hidden="true" />}
      {attention && (
        <span className="olive-core-status" aria-hidden="true">
          {state === "Error" || state === "Degraded" ? "!" : state === "Approval required" ? "?" : "Ⅱ"}
        </span>
      )}
    </div>
  );
}
// Existing call sites retain their slot and shared-layout handoff.
export function Core({ state = "Ready", large = false }: { state?: string; large?: boolean }) {
  return <OliveCore state={state} variant={large ? "welcome" : "compact"} />;
}
