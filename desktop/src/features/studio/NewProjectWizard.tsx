import { useEffect, useMemo, useState } from "react";
import { FolderOpen, RefreshCw, Check, AlertTriangle } from "lucide-react";
import { Sheet } from "../../components/Sheet";
import { call, type Workspace } from "../../services/api";

export interface TemplateInfo {
  id: string;
  label: string;
  description: string;
  network: boolean;
}
export interface LanguageInfo {
  id: string;
  label: string;
  runtime: string;
  availability: "ready" | "toolchain_missing" | "template_unavailable" | "editing_only";
  detail: string;
  templates: TemplateInfo[];
  solution: boolean;
  options: {
    interpreters?: { path: string; label: string; version: string }[];
    frameworks?: string[];
  };
}
export interface Toolchains {
  languages: LanguageInfo[];
  checked_at: number;
  git: boolean;
}
const READINESS: Record<LanguageInfo["availability"], string> = {
  ready: "Ready to create",
  toolchain_missing: "Toolchain missing",
  template_unavailable: "Template unavailable",
  editing_only: "Editing only",
};

// A real wizard: language, template, name and location, then the options that
// actually apply. Every language state comes from detected tooling, so an
// unavailable toolchain is explained rather than silently offered.
export function NewProjectWizard({
  open,
  onOpenChange,
  workspaceId,
  onCreated,
  report,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceId: string;
  onCreated: (workspace: Workspace) => void;
  report: (error: unknown) => void;
}) {
  const [toolchains, setToolchains] = useState<Toolchains | null>(null);
  const [loading, setLoading] = useState(false);
  const [language, setLanguage] = useState("");
  const [template, setTemplate] = useState("");
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [interpreter, setInterpreter] = useState("");
  const [git, setGit] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState("");
  const [result, setResult] = useState<{ workspace: Workspace; destination: string; steps: { command: string[]; exit_code: number; output: string }[] } | null>(null);

  const load = (refresh: boolean) => {
    setLoading(true);
    void call<Toolchains>("project.toolchains", { workspace_id: workspaceId, refresh })
      .then((value) => {
        setToolchains(value);
        setLanguage((current) => current || value.languages.find((l) => l.availability === "ready")?.id || "");
      })
      .catch(report)
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    if (open) {
      setError("");
      setResult(null);
      if (!toolchains) load(false);
    }
  }, [open]);
  const selected = useMemo(
    () => toolchains?.languages.find((l) => l.id === language),
    [toolchains, language],
  );
  useEffect(() => {
    setTemplate(selected?.templates[0]?.id || "");
    setInterpreter(selected?.options.interpreters?.[0]?.path || "");
  }, [selected]);
  // The exact destination is confirmed by the backend before anything is made.
  useEffect(() => {
    setPreview("");
    setError("");
    if (!language || !template || !name.trim() || !location) return;
    let stale = false;
    void call<{ destination: string }>("project.new_preview", {
      language,
      template,
      name: name.trim(),
      location,
    })
      .then((value) => {
        if (!stale) setPreview(value.destination);
      })
      .catch((e) => {
        if (!stale) setError(e instanceof Error ? e.message : "That destination cannot be used.");
      });
    return () => {
      stale = true;
    };
  }, [language, template, name, location]);

  const ready = selected?.availability === "ready";
  const canCreate = Boolean(ready && template && name.trim() && location && preview && !error && !busy);
  const create = () => {
    setBusy(true);
    setError("");
    void call<{ workspace: Workspace; destination: string; steps: { command: string[]; exit_code: number; output: string }[] }>(
      "project.new",
      {
        language,
        template,
        name: name.trim(),
        location,
        interpreter: interpreter || "",
        git,
      },
    )
      .then((value) => {
        setResult(value);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "The project could not be created."))
      .finally(() => setBusy(false));
  };
  const close = () => {
    if (result) onCreated(result.workspace);
    onOpenChange(false);
    setResult(null);
  };
  return (
    <Sheet
      open={open}
      onOpenChange={(value) => {
        if (!value) close();
      }}
      title="New project"
      description="Creates a real project folder from an installed template and opens it as its own Studio workspace. Your current workspace stays open."
    >
      {result ? (
        <div className="wizard-done">
          <p role="status">
            <Check size={16} aria-hidden="true" /> Created <code>{result.destination}</code>
          </p>
          <details>
            <summary className="small">What ran ({result.steps.length})</summary>
            {result.steps.map((step, index) => (
              <pre key={index} className="small source-text">
                {step.command.join(" ")}
                {"\n"}exit {step.exit_code}
                {step.output ? "\n" + step.output : ""}
              </pre>
            ))}
          </details>
          <button className="primary" onClick={close}>
            Done
          </button>
        </div>
      ) : (
        <div className="wizard">
          <section className="wizard-step">
            <div className="row spread">
              <h3>1 · Language</h3>
              <button
                className="quiet small"
                onClick={() => load(true)}
                disabled={loading}
                title="Re-check installed SDKs, interpreters and templates"
              >
                <RefreshCw size={14} aria-hidden="true" />
                {loading ? "Checking…" : "Refresh"}
              </button>
            </div>
            {!toolchains && loading && <p className="muted small">Checking installed tooling…</p>}
            <div className="language-grid" role="radiogroup" aria-label="Project language">
              {toolchains?.languages.map((item) => (
                <button
                  key={item.id}
                  role="radio"
                  aria-checked={language === item.id}
                  className={`language-card ${language === item.id ? "selected" : ""}`}
                  data-language={item.id}
                  data-availability={item.availability}
                  disabled={item.availability !== "ready"}
                  onClick={() => setLanguage(item.id)}
                  title={item.detail}
                >
                  <strong>{item.label}</strong>
                  <span className="small muted">{item.detail}</span>
                  <span className="readiness" data-availability={item.availability}>
                    {item.availability !== "ready" && <AlertTriangle size={12} aria-hidden="true" />}
                    {READINESS[item.availability]}
                  </span>
                </button>
              ))}
            </div>
            {toolchains?.languages.some((l) => l.availability !== "ready") && (
              <p className="small muted">
                Languages without installed tooling are listed but cannot be created. Install the
                SDK or runtime yourself, then Refresh — OLIVE never installs it for you.
              </p>
            )}
          </section>

          <section className="wizard-step" hidden={!selected || !ready}>
            <h3>2 · Project type</h3>
            <div className="template-grid" role="radiogroup" aria-label="Project template">
              {selected?.templates.map((item) => (
                <button
                  key={item.id}
                  role="radio"
                  aria-checked={template === item.id}
                  className={`template-card ${template === item.id ? "selected" : ""}`}
                  onClick={() => setTemplate(item.id)}
                >
                  <strong>{item.label}</strong>
                  <span className="small muted">{item.description}</span>
                </button>
              ))}
            </div>
            {selected?.templates.length === 0 && (
              <p className="small">The installed tooling offers no template OLIVE supports.</p>
            )}
          </section>

          <section className="wizard-step" hidden={!ready}>
            <h3>3 · Name and location</h3>
            <label className="field">
              Project name
              <input
                aria-label="Project name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="my-project"
              />
            </label>
            <label className="field">
              Location
              <div className="row">
                <input
                  aria-label="Project location"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  placeholder="Choose a folder…"
                />
                <button
                  onClick={() =>
                    void window.olive
                      .chooseDirectory()
                      .then((path) => {
                        if (path) setLocation(path);
                      })
                      .catch(report)
                  }
                >
                  <FolderOpen size={15} aria-hidden="true" />
                  Browse
                </button>
              </div>
            </label>
            {preview && (
              <p className="small destination" role="status">
                Will create <code>{preview}</code>
              </p>
            )}
          </section>

          <section className="wizard-step" hidden={!ready}>
            <h3>4 · Options</h3>
            {selected?.options.interpreters && selected.options.interpreters.length > 0 && (
              <label className="field">
                Interpreter
                <select
                  aria-label="Python interpreter"
                  value={interpreter}
                  onChange={(e) => setInterpreter(e.target.value)}
                >
                  {selected.options.interpreters.map((item) => (
                    <option key={item.path} value={item.path}>
                      {item.label} {item.version} — {item.path}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label className="setting-row">
              <input
                type="checkbox"
                checked={git}
                onChange={(e) => setGit(e.target.checked)}
                disabled={!toolchains?.git}
              />
              Initialise a Git repository
              {!toolchains?.git && <span className="small muted"> (git was not found)</span>}
            </label>
            <p className="small muted">
              No packages are downloaded and no template scripts run. Restore or install
              dependencies afterwards from Studio, as a separate reviewed step.
            </p>
          </section>

          {error && <p role="alert">{error}</p>}
          <div className="row wizard-actions">
            <button onClick={close} disabled={busy}>
              Cancel
            </button>
            <button className="primary" disabled={!canCreate} onClick={create}>
              {busy ? "Creating…" : "Create project"}
            </button>
          </div>
        </div>
      )}
    </Sheet>
  );
}
