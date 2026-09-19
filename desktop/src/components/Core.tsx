import { useEffect, useId, useRef } from "react";
import { OliveRenderer } from "./olive-core/renderer";
import { activeState } from "./olive-core/geometry";

export function OliveCore({
  state = "Ready",
  variant = "compact",
}: {
  state?: string;
  variant?: "welcome" | "compact";
}) {
  const canvas = useRef<HTMLCanvasElement>(null),
    renderer = useRef<OliveRenderer | null>(null);
  const pattern = useId();
  useEffect(() => {
    try {
      renderer.current = new OliveRenderer(
        canvas.current!,
        variant === "welcome",
      );
    } catch {
      /* Locally rendered SVG remains visible if Canvas cannot start. */
    }
    return () => {
      renderer.current?.dispose();
      renderer.current = null;
    };
  }, [variant]);
  useEffect(() => {
    renderer.current?.setState(state);
  }, [state, variant]);
  const attention = [
    "Approval required",
    "Paused",
    "Pausing",
    "Degraded",
    "Error",
  ].includes(state);
  return (
    <div
      className={`core ${variant === "welcome" ? "core-large" : ""} ${activeState(state) ? "core-active" : ""}`}
      role="img"
      aria-label={`OLIVE: ${state}`}
      data-state={state}
    >
      <svg
        className="olive-core-fallback"
        viewBox="0 0 100 100"
        aria-hidden="true"
      >
        <defs>
          <pattern
            id={pattern}
            width="5"
            height="5"
            patternUnits="userSpaceOnUse"
          >
            <circle cx="2" cy="2" r="1.25" fill="currentColor" />
          </pattern>
        </defs>
        <path
          d="M60 12 C82 16 89 40 79 65 C70 88 50 96 31 85 C12 75 14 50 23 31 C32 12 44 6 60 12Z"
          fill={`url(#${pattern})`}
        />
        <ellipse
          cx="57"
          cy="23"
          rx="17"
          ry="9"
          transform="rotate(24 57 23)"
          fill="var(--pimento, #d8443c)"
          stroke="currentColor"
          strokeWidth="1.5"
        />
      </svg>
      <canvas ref={canvas} className="olive-core-canvas" aria-hidden="true" />
      {attention && (
        <span className="olive-core-status" aria-hidden="true">
          {state === "Error"
            ? "!"
            : state === "Degraded"
              ? "!"
              : state === "Approval required"
                ? "?"
                : "Ⅱ"}
        </span>
      )}
    </div>
  );
}
// Existing call sites retain their slot and shared-layout handoff.
export function Core({
  state = "Ready",
  large = false,
}: {
  state?: string;
  large?: boolean;
}) {
  return <OliveCore state={state} variant={large ? "welcome" : "compact"} />;
}
