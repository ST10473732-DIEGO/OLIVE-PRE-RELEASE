import { useEffect, useState } from "react";
import { Boxes, FlaskConical, Globe, Library, Star, Terminal, Plus, Settings2 } from "lucide-react";
import { call } from "../../services/api";
import { Sheet } from "../../components/Sheet";

export interface ProjectRecord {
  path: string;
  relative_path: string;
  name: string;
  sdk: string;
  target_frameworks: string[];
  output_type: string;
  references: string[];
  packages: { name: string; version: string }[];
  is_test: boolean;
  is_web: boolean;
  is_executable: boolean;
  launch_profiles: { name: string; command: string; application_url: string; launch_browser: boolean }[];
  error: string;
}
export interface SolutionRecord {
  path: string;
  relative_path: string;
  name: string;
  format: string;
  projects: string[];
  error: string;
}
export interface RunConfiguration {
  startup_project: string;
  configuration: string;
  arguments: string[];
  working_directory: string;
  environment: Record<string, string>;
  interpreter: string;
  launch_profile: string;
  program: string;
  stop_at_entry: boolean;
}
export interface ProjectScan {
  root: string;
  solutions: SolutionRecord[];
  projects: ProjectRecord[];
  global_json: { sdk_version: string; roll_forward: string } | null;
  python: { present: boolean; markers: string[]; tests_directory: boolean };
  node: { present: boolean };
  kind: string;
  run_configuration: RunConfiguration;
  tooling: {
    dotnet: { available: boolean; version?: string; sdks?: string[]; runtimes?: string[]; executable?: string };
    csharp_language_server: { available: boolean; version: string; licence: string };
    dotnet_debugger: { available: boolean; version: string; licence: string };
    python_debugger: { available: boolean; provider: string };
    python_language_server: { available: boolean; provider: string };
    terminal: { available: boolean; provider: string };
    python: { executable: string; version: string };
  };
}
export function useProjectScan(workspaceId: string, report: (error: unknown) => void) {
  const [scan, setScan] = useState<ProjectScan | null>(null);
  const [loading, setLoading] = useState(false);
  const refresh = async () => {
    if (!workspaceId) return;
    setLoading(true);
    try {
      setScan(await call<ProjectScan>("project.scan", { workspace_id: workspaceId }));
    } catch (error) {
      report(error);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    setScan(null);
    void refresh();
  }, [workspaceId]);
  return { scan, loading, refresh, setScan };
}
// The solution view: what the workspace actually contains according to the
// project files on disk, and which project runs.
export function ProjectPanel({
  workspaceId,
  scan,
  refresh,
  openFile,
  report,
  build,
  busy,
}: {
  workspaceId: string;
  scan: ProjectScan | null;
  refresh: () => Promise<void>;
  openFile: (path: string) => void;
  report: (error: unknown) => void;
  build: (mode: string, target?: string) => void;
  busy: boolean;
}) {
  const [creating, setCreating] = useState(false);
  const [adding, setAdding] = useState(false);
  const [configuring, setConfiguring] = useState(false);
  if (!scan) return <p className="small muted explorer-note">Reading project files…</p>;
  const config = scan.run_configuration;
  const setStartup = async (path: string) => {
    try {
      await call("project.config_save", { workspace_id: workspaceId, config: { ...config, startup_project: path } });
      await refresh();
    } catch (error) {
      report(error);
    }
  };
  const dotnet = scan.tooling.dotnet;
  return (
    <div className="project-panel">
      <div className="explorer-head">
        <span className="eyebrow">
          {scan.kind === "dotnet" ? "Solution" : scan.kind === "python" ? "Python project" : "Project"}
        </span>
        <div className="row">
          <button className="icon-button" aria-label="Add project to this solution" title="Add a new project to this solution" onClick={() => setCreating(true)}>
            <Plus size={14} aria-hidden="true" />
          </button>
          <button className="icon-button" aria-label="Run configuration" title="Startup project, configuration, arguments, environment" onClick={() => setConfiguring(true)}>
            <Settings2 size={14} aria-hidden="true" />
          </button>
        </div>
      </div>
      {scan.kind === "dotnet" && (
        <>
          {scan.solutions.map((solution) => (
            <div className="solution-row" key={solution.path}>
              <button className="tree-like" onClick={() => openFile(solution.relative_path)} title={solution.path}>
                <Boxes size={14} aria-hidden="true" />
                <span>{solution.name}</span>
                <span className="small muted">.{solution.format}</span>
              </button>
              {solution.error && <p className="small" role="alert">{solution.error}</p>}
            </div>
          ))}
          <ul className="project-list" aria-label="Projects">
            {scan.projects.map((project) => {
              const startup = Boolean(config.startup_project) && config.startup_project.toLowerCase() === project.path.toLowerCase();
              return (
                <li key={project.path} data-startup={startup} data-test={project.is_test}>
                  <button className="tree-like project-row" onClick={() => openFile(project.relative_path)} title={project.path}>
                    {project.is_test ? (
                      <FlaskConical size={14} aria-hidden="true" />
                    ) : project.is_web ? (
                      <Globe size={14} aria-hidden="true" />
                    ) : project.is_executable ? (
                      <Terminal size={14} aria-hidden="true" />
                    ) : (
                      <Library size={14} aria-hidden="true" />
                    )}
                    <span className="project-name">{project.name}</span>
                    <span className="small muted">{project.target_frameworks.join(", ")}</span>
                  </button>
                  <div className="project-actions">
                    {project.is_executable && !project.is_test && (
                      <button
                        className={`icon-button ${startup ? "selected" : ""}`}
                        aria-label={startup ? `${project.name} is the startup project` : `Set ${project.name} as startup project`}
                        aria-pressed={startup}
                        title={startup ? "Startup project" : "Set as startup project"}
                        onClick={() => void setStartup(project.path)}
                      >
                        <Star size={13} aria-hidden="true" />
                      </button>
                    )}
                    <button className="quiet small" disabled={busy} onClick={() => build("build", project.relative_path)} title={`dotnet build ${project.name}`}>
                      Build
                    </button>
                  </div>
                  {project.error && <p className="small" role="alert">{project.error}</p>}
                  {project.references.length > 0 && (
                    <p className="small muted project-refs">→ {project.references.map((r) => r.split(/[\\/]/).pop()?.replace(/\.csproj$/, "")).join(", ")}</p>
                  )}
                </li>
              );
            })}
          </ul>
          {scan.solutions.length > 0 && (
            <button className="text-button small" onClick={() => setAdding(true)}>
              Add existing project to solution…
            </button>
          )}
          <p className="small muted explorer-note">
            {dotnet.available ? (
              <>
                .NET SDK {dotnet.version || "?"}
                {scan.global_json?.sdk_version ? ` · global.json pins ${scan.global_json.sdk_version}` : ""}
              </>
            ) : (
              "The .NET SDK was not found on this machine."
            )}
          </p>
        </>
      )}
      {scan.kind === "python" && (
        <p className="small muted explorer-note">
          {scan.python.markers.join(", ")} · {scan.tooling.python.version}
          {scan.python.tests_directory ? " · tests/" : ""}
        </p>
      )}
      {scan.kind === "folder" && (
        <p className="small muted explorer-note">No .NET or Python project markers. Create one from a template.</p>
      )}
      <NewProjectDialog
        open={creating}
        close={() => setCreating(false)}
        workspaceId={workspaceId}
        scan={scan}
        done={refresh}
        report={report}
      />
      <AddExistingDialog open={adding} close={() => setAdding(false)} workspaceId={workspaceId} scan={scan} done={refresh} report={report} />
      <RunConfigurationDialog
        open={configuring}
        close={() => setConfiguring(false)}
        workspaceId={workspaceId}
        scan={scan}
        done={refresh}
        report={report}
      />
    </div>
  );
}
const TEMPLATES = [
  { id: "console", name: "Console application", hint: "C# console app" },
  { id: "webapi", name: "ASP.NET Core Web API", hint: "Minimal HTTP API" },
  { id: "classlib", name: "Class library", hint: "Shared code" },
  { id: "xunit", name: "xUnit test project", hint: "Tests with xunit" },
  { id: "mstest", name: "MSTest test project", hint: "Tests with MSTest" },
  { id: "nunit", name: "NUnit test project", hint: "Tests with NUnit" },
  { id: "sln", name: "Solution file", hint: "Empty solution" },
];
function NewProjectDialog({
  open,
  close,
  workspaceId,
  scan,
  done,
  report,
}: {
  open: boolean;
  close: () => void;
  workspaceId: string;
  scan: ProjectScan;
  done: () => Promise<void>;
  report: (error: unknown) => void;
}) {
  const [kind, setKind] = useState("console");
  const [name, setName] = useState("");
  const [directory, setDirectory] = useState("");
  const [solution, setSolution] = useState(scan.solutions[0]?.relative_path || "");
  const [references, setReferences] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ created: string; steps: { command: string[]; exit_code: number | null; output: string }[] } | null>(null);
  const valid = /^[A-Za-z0-9_.-]{1,80}$/.test(name);
  const create = async () => {
    setBusy(true);
    setError("");
    try {
      const created = await call<{ created: string; steps: { command: string[]; exit_code: number | null; output: string }[] }>("project.create", {
        workspace_id: workspaceId,
        kind,
        name,
        directory,
        solution: kind === "sln" ? "" : solution,
        references,
      });
      setResult(created);
      await done();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The template could not be created.");
      report(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet
      open={open}
      onOpenChange={(value) => {
        if (!value) {
          close();
          setResult(null);
        }
      }}
      title="Add project to this solution"
      description="Adds a project to the solution already open in this workspace, using the installed .NET template. To start a separate project, use New project in the Studio header."
    >
      {result ? (
        <>
          <p role="status">Created {result.created}</p>
          <details>
            <summary className="small">Commands run ({result.steps.length})</summary>
            {result.steps.map((step, index) => (
              <pre key={index} className="small source-text">
                {step.command.join(" ")}
                {"\n"}exit {step.exit_code ?? "?"}
                {step.output ? "\n" + step.output : ""}
              </pre>
            ))}
          </details>
          <button className="primary" onClick={() => { close(); setResult(null); }}>
            Done
          </button>
        </>
      ) : (
        <>
          <div className="template-grid" role="radiogroup" aria-label="Template">
            {TEMPLATES.map((template) => (
              <button
                key={template.id}
                role="radio"
                aria-checked={kind === template.id}
                className={`template-card ${kind === template.id ? "selected" : ""}`}
                onClick={() => setKind(template.id)}
              >
                <strong>{template.name}</strong>
                <span className="small muted">{template.hint}</span>
              </button>
            ))}
          </div>
          <label className="field">
            {kind === "sln" ? "Solution name" : "Project name"}
            <input aria-label="Project name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme.Api" />
          </label>
          <label className="field">
            Folder inside the workspace (optional)
            <input aria-label="Project folder" value={directory} onChange={(e) => setDirectory(e.target.value)} placeholder="src" />
          </label>
          {kind !== "sln" && scan.solutions.length > 0 && (
            <label className="field">
              Add to solution
              <select aria-label="Solution" value={solution} onChange={(e) => setSolution(e.target.value)}>
                <option value="">Do not add to a solution</option>
                {scan.solutions.map((item) => (
                  <option key={item.path} value={item.relative_path}>
                    {item.relative_path}
                  </option>
                ))}
              </select>
            </label>
          )}
          {kind !== "sln" && scan.projects.length > 0 && (
            <fieldset className="field">
              <legend className="small">Reference existing projects</legend>
              {scan.projects.map((project) => (
                <label key={project.path} className="small">
                  <input
                    type="checkbox"
                    checked={references.includes(project.relative_path)}
                    onChange={(e) =>
                      setReferences((current) =>
                        e.target.checked ? [...current, project.relative_path] : current.filter((item) => item !== project.relative_path),
                      )
                    }
                  />
                  {project.name}
                </label>
              ))}
            </fieldset>
          )}
          {error && <p role="alert">{error}</p>}
          <div className="row">
            <button onClick={close} disabled={busy}>
              Cancel
            </button>
            <button className="primary" disabled={busy || !valid} onClick={() => void create()}>
              {busy ? "Creating…" : "Create"}
            </button>
          </div>
        </>
      )}
    </Sheet>
  );
}
function AddExistingDialog({
  open,
  close,
  workspaceId,
  scan,
  done,
  report,
}: {
  open: boolean;
  close: () => void;
  workspaceId: string;
  scan: ProjectScan;
  done: () => Promise<void>;
  report: (error: unknown) => void;
}) {
  const [solution, setSolution] = useState(scan.solutions[0]?.relative_path || "");
  const [project, setProject] = useState("");
  const [busy, setBusy] = useState(false);
  const missing = scan.projects.filter(
    (item) => !scan.solutions.some((s) => s.projects.some((p) => p.toLowerCase() === item.path.replace(/\\/g, "/").toLowerCase())),
  );
  return (
    <Sheet open={open} onOpenChange={(value) => !value && close()} title="Add existing project" description="Adds a project file already inside the workspace to a solution with dotnet sln add.">
      <label className="field">
        Solution
        <select aria-label="Target solution" value={solution} onChange={(e) => setSolution(e.target.value)}>
          {scan.solutions.map((item) => (
            <option key={item.path} value={item.relative_path}>
              {item.relative_path}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        Project file
        <input aria-label="Project file path" value={project} onChange={(e) => setProject(e.target.value)} placeholder="src/Acme.Core/Acme.Core.csproj" list="olive-missing-projects" />
        <datalist id="olive-missing-projects">
          {missing.map((item) => (
            <option key={item.path} value={item.relative_path} />
          ))}
        </datalist>
      </label>
      <div className="row">
        <button onClick={close} disabled={busy}>
          Cancel
        </button>
        <button
          className="primary"
          disabled={busy || !project.trim() || !solution}
          onClick={() => {
            setBusy(true);
            void call("project.add_existing", { workspace_id: workspaceId, solution, project: project.trim() })
              .then(done)
              .then(close)
              .catch(report)
              .finally(() => setBusy(false));
          }}
        >
          Add to solution
        </button>
      </div>
    </Sheet>
  );
}
export function RunConfigurationDialog({
  open,
  close,
  workspaceId,
  scan,
  done,
  report,
}: {
  open: boolean;
  close: () => void;
  workspaceId: string;
  scan: ProjectScan;
  done: () => Promise<void>;
  report: (error: unknown) => void;
}) {
  const [draft, setDraft] = useState<RunConfiguration>(scan.run_configuration);
  const [environment, setEnvironment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (open) {
      setDraft(scan.run_configuration);
      setEnvironment(
        Object.entries(scan.run_configuration.environment)
          .map(([name, value]) => `${name}=${value}`)
          .join("\n"),
      );
      setError("");
    }
  }, [open, scan.run_configuration]);
  const startup = scan.projects.find((p) => p.path.toLowerCase() === draft.startup_project.toLowerCase());
  const save = async () => {
    setBusy(true);
    setError("");
    try {
      const env = Object.fromEntries(
        environment
          .split("\n")
          .map((line) => line.trim())
          .filter((line) => line && line.includes("="))
          .map((line) => [line.slice(0, line.indexOf("=")).trim(), line.slice(line.indexOf("=") + 1)]),
      );
      await call("project.config_save", { workspace_id: workspaceId, config: { ...draft, environment: env } });
      await done();
      close();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The configuration could not be saved.");
      report(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet
      open={open}
      onOpenChange={(value) => !value && close()}
      title="Run configuration"
      description="How Run, Debug and Test start the project. Secret-looking variable names are refused; values are never logged."
    >
      {scan.kind === "dotnet" ? (
        <>
          <label className="field">
            Startup project
            <select aria-label="Startup project" value={draft.startup_project} onChange={(e) => setDraft({ ...draft, startup_project: e.target.value, launch_profile: "" })}>
              <option value="">Choose a project</option>
              {scan.projects
                .filter((p) => p.is_executable && !p.is_test)
                .map((p) => (
                  <option key={p.path} value={p.path}>
                    {p.name} ({p.target_frameworks.join(", ")})
                  </option>
                ))}
            </select>
          </label>
          <label className="field">
            Configuration
            <select aria-label="Build configuration" value={draft.configuration} onChange={(e) => setDraft({ ...draft, configuration: e.target.value })}>
              <option>Debug</option>
              <option>Release</option>
            </select>
          </label>
          {startup && startup.launch_profiles.length > 0 && (
            <label className="field">
              Launch profile
              <select aria-label="Launch profile" value={draft.launch_profile} onChange={(e) => setDraft({ ...draft, launch_profile: e.target.value })}>
                <option value="">None (--no-launch-profile)</option>
                {startup.launch_profiles.map((profile) => (
                  <option key={profile.name} value={profile.name}>
                    {profile.name} {profile.application_url ? `· ${profile.application_url}` : ""}
                  </option>
                ))}
              </select>
            </label>
          )}
        </>
      ) : (
        <>
          <label className="field">
            Program (inside the workspace)
            <input aria-label="Program" value={draft.program} onChange={(e) => setDraft({ ...draft, program: e.target.value })} placeholder="main.py" />
          </label>
          <label className="field">
            Interpreter
            <input aria-label="Interpreter" value={draft.interpreter} onChange={(e) => setDraft({ ...draft, interpreter: e.target.value })} placeholder={scan.tooling.python.executable} />
          </label>
        </>
      )}
      <label className="field">
        Arguments (one per line)
        <textarea aria-label="Program arguments" rows={2} value={draft.arguments.join("\n")} onChange={(e) => setDraft({ ...draft, arguments: e.target.value.split("\n").filter((line) => line.trim()) })} />
      </label>
      <label className="field">
        Working directory (inside the workspace; blank for the project folder)
        <input aria-label="Working directory" value={draft.working_directory} onChange={(e) => setDraft({ ...draft, working_directory: e.target.value })} />
      </label>
      <label className="field">
        Environment overrides (NAME=value per line; only the safe allow-list is passed through)
        <textarea aria-label="Environment overrides" rows={3} value={environment} onChange={(e) => setEnvironment(e.target.value)} />
      </label>
      <label className="setting-row">
        <input type="checkbox" checked={draft.stop_at_entry} onChange={(e) => setDraft({ ...draft, stop_at_entry: e.target.checked })} />
        Stop at entry when debugging
      </label>
      {error && <p role="alert">{error}</p>}
      <div className="row">
        <button onClick={close} disabled={busy}>
          Cancel
        </button>
        <button className="primary" onClick={() => void save()} disabled={busy}>
          Save configuration
        </button>
      </div>
    </Sheet>
  );
}
