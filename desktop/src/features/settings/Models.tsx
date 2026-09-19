import { useState } from "react";
import { call, type Preset } from "../../services/api";
import { useResource } from "../../services/useResource";
import { Details } from "../../components/WorkspacePage";
import { Sheet } from "../../components/Sheet";
interface Policy {
  mode: string;
  overrides: Record<string, string>;
  contexts: Record<string, number>;
  vram_gb: number;
  keep_alive: number;
}
interface Stack {
  presets: Preset[];
  conversation: {chat_id: string; model: string};
  policy: Policy;
  installed: string[];
  assignments: { role: string; model: string; context: number }[];
  benchmark_active: boolean;
  residency: unknown;
  metrics: unknown;
  decisions: unknown;
}
export function Models({ report }: { report: (e: unknown) => void }) {
  const resource = useResource(() => call<Stack>("models.status", {}));
  const [draft, setDraft] = useState<Policy>();
  const [selected, setSelected] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [install, setInstall] = useState(false);
  const [model, setModel] = useState("");
  const [notice, setNotice] = useState("");
  const data = resource.data;
  const policy = draft || data?.policy;
  const operation = async (fn: () => Promise<unknown>, message: string) => {
    try {
      await fn();
      setNotice(message);
      await resource.refresh();
    } catch (e) {
      report(e);
    }
  };
  if (!data || !policy)
    return <p role="status">{resource.error || "Loading model rolesâ€¦"}</p>;
  return (
    <section>
      <h3>OLIVE presets</h3>
      <p className="muted">Presets choose local models and pipelines. Provider weights retain their original identity.</p>
      {data.presets.map(p => <details key={p.id}>
        <summary>{p.name} · {p.status}</summary>
        <p>{p.description}</p>
        <p>{p.runtime} · {p.model || "No media engine configured"} · {p.pipeline}</p>
        <p className="muted">Digest: {p.digest || "Unavailable"}<br />{p.resource_policy}</p>
      </details>)}
      <h3>Advanced provider selection</h3>
      <label className="field">Current conversation model
        <select value={data.conversation.model} onChange={e => void operation(() => call("chat.model", {chat_id: data.conversation.chat_id, model: e.target.value}), "Explicit provider selected for this conversation")}>
          {!data.installed.includes(data.conversation.model) && <option value={data.conversation.model}>{data.conversation.model || "No model"}</option>}
          {data.installed.map(m => <option key={m}>{m}</option>)}
        </select>
      </label>
      <h3>Model roles</h3>
      <p className="muted">
        Measured role assignments stay in Python. Refresh lists local models;
        benchmarking is opt-in.
      </p>
      <label className="field">
        Selection mode
        <select
          value={policy.mode}
          onChange={(e) => setDraft({ ...policy, mode: e.target.value })}
        >
          {["Automatic", "Performance", "Balanced", "Quality"].map((m) => (
            <option key={m}>{m}</option>
          ))}
        </select>
      </label>
      {data.assignments.map((a) => (
        <div className="scope-row" key={a.role}>
          <label className="field">
            {a.role} Â· {a.model}
            <select
              aria-label={`${a.role} model override`}
              value={policy.overrides[a.role] || ""}
              onChange={(e) =>
                setDraft({
                  ...policy,
                  overrides: { ...policy.overrides, [a.role]: e.target.value },
                })
              }
            >
              <option value="">Automatic</option>
              {data.installed.map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
          </label>
          <label className="field">
            Context tokens
            <input
              type="number"
              min={1024}
              max={65536}
              value={policy.contexts[a.role]}
              onChange={(e) =>
                setDraft({
                  ...policy,
                  contexts: {
                    ...policy.contexts,
                    [a.role]: Number(e.target.value),
                  },
                })
              }
            />
          </label>
        </div>
      ))}
      <div className="row">
        <button
          onClick={() =>
            void operation(
              () => call("models.save", { policy: { ...policy } }),
              "Model policy saved.",
            )
          }
        >
          Save model policy
        </button>
        <button
          onClick={() =>
            void operation(
              () => call("models.refresh", {}),
              "Installed models refreshed.",
            )
          }
        >
          Refresh models
        </button>
        <button onClick={() => setInstall(true)}>
          Install an Ollama modelâ€¦
        </button>
      </div>
      <Details
        value={{
          residency: data.residency,
          metrics: data.metrics,
          decisions: data.decisions,
        }}
        title="Residency, metrics and routing evidence"
      />
      <details>
        <summary>Local benchmarks</summary>
        <p>
          Select models explicitly. Benchmarks load models and use local GPU
          resources.
        </p>
        {data.installed.map((m) => (
          <label className="check-field" key={m}>
            <input
              type="checkbox"
              checked={selected.includes(m)}
              onChange={(e) =>
                setSelected(
                  e.target.checked
                    ? [...selected, m]
                    : selected.filter((x) => x !== m),
                )
              }
            />
            {m}
          </label>
        ))}
        <div className="row">
          <button
            disabled={!selected.length || running}
            onClick={() => {
              setRunning(true);
              void operation(
                () =>
                  call("models.benchmark", { models: selected, timeout: 60 }),
                "Benchmark finished. Inspect the local evidence.",
              ).finally(() => setRunning(false));
            }}
          >
            Benchmark selected models
          </button>
          <button
            disabled={!running && !data.benchmark_active}
            onClick={() =>
              void operation(
                () => call("models.stop_benchmark", {}),
                "Benchmark cancellation requested.",
              )
            }
          >
            Stop benchmark
          </button>
        </div>
      </details>
      <p role="status">{notice}</p>
      <Sheet
        open={install}
        onOpenChange={setInstall}
        title="Download an Ollama model"
        description="This explicitly downloads model files to the local Ollama installation. No model is downloaded by opening Settings."
      >
        <label className="field">
          Exact model name
          <input value={model} onChange={(e) => setModel(e.target.value)} />
        </label>
        <div className="row">
          <button onClick={() => setInstall(false)}>Cancel</button>
          <button
            className="primary"
            disabled={!model.trim()}
            onClick={() => {
              setInstall(false);
              void operation(
                () =>
                  call("data.pull_model", {
                    name: model.trim(),
                    confirmed: true,
                  }),
                "Model download completed.",
              );
            }}
          >
            Approve download
          </button>
        </div>
      </Sheet>
    </section>
  );
}
