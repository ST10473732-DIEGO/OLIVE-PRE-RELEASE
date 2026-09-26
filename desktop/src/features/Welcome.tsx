import { useState } from "react";
import { motion } from "motion/react";
import { ArrowRight, Check, Cpu, ShieldCheck } from "lucide-react";
import { Core } from "../components/Core";
import type { RuntimeState } from "../services/runtimeState";

// The Grove entrance: the dot-matrix olive, the wordmark, and two honest
// checks (the local AI and where your data lives) before Home. It never waits
// for a model: OLIVE opens even when Ollama is still starting or missing.
export function Welcome({
  state,
  ready,
  runtime,
  enter,
  model,
}: {
  /** The model status label, for example "NORMAL ready". */
  model?: string;
  state: string;
  ready: boolean;
  runtime: RuntimeState;
  enter: () => void;
}) {
  const [skip, setSkip] = useState(() => localStorage.getItem("skipWelcome") === "true");
  const aiReady = ready && runtime.tone !== "error" && runtime.detail !== "AI offline" && runtime.detail !== "no model installed";
  const checks = [
    {
      id: "ai",
      icon: Cpu,
      title: "Local AI",
      detail: !ready ? "Starting the local runtime…" : aiReady ? `Ollama · ${model || runtime.detail || "ready"}` : `${runtime.detail || "Unavailable"} · everything else still works`,
      done: aiReady,
      waiting: !ready,
    },
    {
      id: "private",
      icon: ShieldCheck,
      title: "Private by default",
      detail: "Chats, files and memory stay on this device",
      done: true,
      waiting: false,
    },
  ];
  return (
    <main className="welcome">
      <div className="welcome-glow" aria-hidden="true" />
      <div className="welcome-content">
        <motion.div layoutId="core" layout="position" className="welcome-core">
          <Core large state={state} />
        </motion.div>
        <h1 className="wordmark">OLIVE</h1>
        <p className="welcome-tagline">Your assistant, running entirely on this computer.</p>
        <ul className="welcome-checks" aria-label="Readiness">
          {checks.map((check) => (
            <li key={check.id}>
              <span className="welcome-check-icon" aria-hidden="true">
                <check.icon size={16} />
              </span>
              <span className="welcome-check-text">
                <strong>{check.title}</strong>
                <small>{check.detail}</small>
              </span>
              <span className="welcome-check-state" aria-label={check.waiting ? "Starting" : check.done ? "Ready" : "Needs attention"}>
                {check.waiting ? <span className="welcome-spinner" /> : check.done ? <span className="welcome-tick"><Check size={11} strokeWidth={3} /></span> : <span className="welcome-warn">!</span>}
              </span>
            </li>
          ))}
        </ul>
        <motion.button whileTap={{ scale: 0.985 }} className="primary enter" onClick={() => enter()}>
          Enter OLIVE
          <ArrowRight size={17} aria-hidden="true" />
        </motion.button>
        <span className="readiness" data-tone={runtime.tone}>
          <span className="status-dot" />
          {ready
            ? `Ready to open${runtime.detail ? ` · ${runtime.detail}` : ""}`
            : "Preparing your local space"}
        </span>
        <label className="welcome-skip">
          <input
            type="checkbox"
            className="ws-switch"
            checked={skip}
            onChange={(event) => {
              setSkip(event.target.checked);
              localStorage.setItem("skipWelcome", String(event.target.checked));
            }}
          />
          Open straight to Home next time
        </label>
      </div>
    </main>
  );
}
