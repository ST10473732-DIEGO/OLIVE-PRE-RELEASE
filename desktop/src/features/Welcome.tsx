import { motion } from "motion/react";
import { ArrowRight } from "lucide-react";
import { Core } from "../components/Core";
import type { RuntimeState } from "../services/runtimeState";

// The entrance belongs to the same application as Home: the same ink ground,
// the same blue/cyan identity and the same typography, with the rotating
// dot-matrix olive as the one piece of atmosphere. It never waits for a model.
export function Welcome({
  state,
  ready,
  runtime,
  enter,
}: {
  state: string;
  ready: boolean;
  runtime: RuntimeState;
  enter: () => void;
}) {
  return (
    <main className="welcome">
      <div className="welcome-glow" aria-hidden="true" />
      <div className="welcome-content">
        <motion.div layoutId="core" layout="position" className="welcome-core">
          <Core large state={state} />
        </motion.div>
        <h1 className="wordmark">OLIVE</h1>
        <p className="welcome-tagline">Local Intelligence</p>
        <motion.button
          whileTap={{ scale: 0.985 }}
          className="primary enter"
          onClick={() => enter()}
        >
          Enter OLIVE
          <ArrowRight size={17} aria-hidden="true" />
        </motion.button>
        <span className="readiness" data-tone={runtime.tone}>
          <span className="status-dot" />
          {ready
            ? `Ready to open${runtime.detail ? ` · ${runtime.detail}` : ""}`
            : "Preparing your local space"}
        </span>
      </div>
    </main>
  );
}
