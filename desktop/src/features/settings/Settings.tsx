import { LayoutControls } from "./LayoutControls";
import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import { WorkspacePage, Details } from "../../components/WorkspacePage";
import { Permissions } from "./Permissions";
import { Diagnostics } from "./Diagnostics";
import { Models } from "./Models";
import { DesktopPolicies } from "./DesktopPolicies";
import MailConnections from "../mail/MailConnections";
import BrowserSettings from "../go/BrowserSettings";
import "../mail/mail.css";
import type { Field, SettingsValue, Value } from "./types";

export default function Settings({
  interfaceScale,
  setInterfaceScale,
  resetLayout,
  initializing,
  developer,
  setDeveloper,
  chatId,
  report,
  theme,
  setTheme,
  reduced,
  setReduced,
  diagnosticsRequest = 0,
  browserRequest = 0,
}: {
  interfaceScale: number;
  setInterfaceScale: (value: number) => void;
  resetLayout: () => void;
  initializing: boolean;
  developer: boolean;
  setDeveloper: (value: boolean) => void;
  chatId: string;
  report: (e: unknown) => void;
  theme: string;
  setTheme: (value: string) => void;
  reduced: boolean;
  browserRequest?: number;
  setReduced: (value: boolean) => void;
  /** Bumped when navigation asks for Diagnostics (it lives inside Settings). */
  diagnosticsRequest?: number;
}) {
  const resource = useResource(async () => {
    const [schema, value] = await Promise.all([
      call<{ fields: Field[]; presets: Record<string, string> }>(
        "settings.schema",
        {},
      ),
      call<SettingsValue>("data.settings", { chat_id: chatId }),
    ]);
    return { schema, value };
  });
  const [draft, setDraft] = useState<SettingsValue>();
  const [category, setCategory] = useState("Appearance");
  useEffect(() => {
    if (diagnosticsRequest) setCategory("Diagnostics");
  }, [diagnosticsRequest]);
  useEffect(() => {
    if (browserRequest) setCategory("Browser");
  }, [browserRequest]);
  const [search, setSearch] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [maintenance, setMaintenance] = useState<unknown>();
  const [skip, setSkip] = useState(
    localStorage.getItem("skipWelcome") === "true",
  );
  const value = draft || resource.data?.value;
  const schema = resource.data?.schema;
  const categories = [
    "General",
    "Appearance",
    "Chat",
    "Models",
    "Permissions",
    "Connections",
    "Browser",
    "Memory",
    "Knowledge",
    "Research",
    "Desktop Control",
    "OCR",
    "Studio",
    "Backup & Data",
    "Diagnostics",
  ];
  const categoryKeywords: Record<string, string> = {
    Appearance:
      "theme dark light reduce motion animations welcome home startup developer navigation text size scale layout",
    Models: "ollama aliases roles default benchmark download inference",
    Permissions: "trust approvals rules allow deny scope",
    Connections: "mail smtp imap server credentials accounts tls password",
    Browser: "olive go browser search engine google duckduckgo bing suggestions new tab favourites private downloads",
    "Backup & Data": "backup restore export chat memory data maintenance",
    Diagnostics: "diagnostics logs health copy export status",
  };
  const fields =
    schema?.fields.filter((f) =>
      search
        ? `${f.label} ${f.category}`
            .toLowerCase()
            .includes(search.toLowerCase())
        : f.category === category,
    ) || [];
  const edit = (f: Field, next: Value) => {
    if (!value) return;
    if (f.target === "params")
      setDraft({ ...value, params: { ...value.params, [f.key]: next } });
    else if (f.target === "research")
      setDraft({
        ...value,
        settings: {
          ...value.settings,
          research: {
            ...(value.settings.research as Record<string, Value>),
            [f.key]: next,
          },
        },
      });
    else setDraft({ ...value, settings: { ...value.settings, [f.key]: next } });
  };
  const save = async () => {
    if (!value) return;
    setSaving(true);
    try {
      const saved = await call<SettingsValue>("data.save_settings", {
        chat_id: value.chat_id,
        settings: value.settings,
        params: value.params,
        system_prompt: value.system_prompt,
        alias: value.alias,
      });
      setDraft(saved);
      setNotice("Settings saved to the shared runtime.");
    } catch (e) {
      report(e);
    } finally {
      setSaving(false);
    }
  };
  return (
    <WorkspacePage
      title="Settings"
      description="Your preferences, local services and permissions."
      actions={
        <button
          className="primary"
          hidden={
            !search &&
            [
              "Permissions",
              "Desktop Control",
              "Backup & Data",
              "Diagnostics",
            ].includes(category)
          }
          disabled={!value || saving}
          onClick={() => void save()}
        >
          {saving ? "Saving…" : "Save settings"}
        </button>
      }
    >
      <label className="search settings-search">
        <Search size={15} aria-hidden="true" />
        <input
          aria-label="Search settings"
          placeholder="Find a setting or category…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </label>
      {resource.error && (
        <p role="alert">
          {resource.error}
          <button onClick={() => void resource.refresh()}>Retry</button>
        </p>
      )}
      <div className="settings-layout">
        <nav aria-label="Settings categories">
          {categories
            .filter(
              (c) =>
                !search ||
                (c + " " + (categoryKeywords[c] || ""))
                  .toLowerCase()
                  .includes(search.toLowerCase()) ||
                fields.some((f) => f.category === c),
            )
            .map((c) => (
              <button
                key={c}
                className={category === c ? "selected" : ""}
                aria-current={category === c ? "page" : undefined}
                onClick={() => {
                  setCategory(c);
                  setSearch("");
                }}
              >
                {c}
              </button>
            ))}
        </nav>
        <div className="settings-content">
          {category === "Connections" && !search && <MailConnections/>}
          {category === "Browser" && !search && <BrowserSettings report={report}/>}
          {search && <p>Select a matching category to open its controls.</p>}
          {category === "Appearance" && !search && (
            <section>
              <h2>Appearance</h2>
              <label className="field">
                Text and interface size
                <select
                  aria-label="Text and interface size"
                  value={interfaceScale}
                  onChange={(e) => setInterfaceScale(Number(e.target.value))}
                >
                  {[1, 1.1, 1.25, 1.5].map((factor) => (
                    <option key={factor} value={factor}>
                      {Math.round(factor * 100)}%
                    </option>
                  ))}
                </select>
              </label>
              <LayoutControls resetNavigation={resetLayout} />
              <label className="check-field">
                <input
                  type="checkbox"
                  checked={developer}
                  onChange={(e) => setDeveloper(e.target.checked)}
                />
                Developer Mode
              </label>
              <p className="small muted">
                Adds a Diagnostics shortcut to navigation. Permissions,
                approvals and safety information stay the same.
              </p>
              <label className="field">
                Theme
                <select
                  value={theme}
                  onChange={(e) => setTheme(e.target.value)}
                >
                  <option value="dark">Dark</option>
                  <option value="light">Light</option>
                </select>
              </label>
              <label className="check-field">
                <input
                  type="checkbox"
                  checked={reduced}
                  onChange={(e) => setReduced(e.target.checked)}
                />
                Reduce motion
              </label>
              <label className="check-field">
                <input
                  type="checkbox"
                  checked={skip}
                  onChange={(e) => {
                    setSkip(e.target.checked);
                    localStorage.setItem(
                      "skipWelcome",
                      String(e.target.checked),
                    );
                  }}
                />
                Start on Home
              </label>
            </section>
          )}
          {fields.length > 0 && value && (
            <section>
              <h2>{search ? "Matching settings" : category}</h2>
              <div className="settings-fields">
                {fields.map((f) => {
                  const current =
                    f.target === "params"
                      ? value.params[f.key]
                      : f.target === "research"
                        ? (value.settings.research as Record<string, Value>)[
                            f.key
                          ]
                        : (value.settings[f.key] as Value);
                  return (
                    <label
                      className={f.kind === "bool" ? "check-field" : "field"}
                      key={`${f.target}.${f.key}`}
                    >
                      <span>
                        {f.label}
                        {search && (
                          <small className="muted"> · {f.category}</small>
                        )}
                      </span>
                      {f.kind === "bool" ? (
                        <input
                          type="checkbox"
                          checked={Boolean(current)}
                          onChange={(e) => edit(f, e.target.checked)}
                        />
                      ) : f.choices ? (
                        <select
                          value={String(current)}
                          onChange={(e) => edit(f, e.target.value)}
                        >
                          {f.choices.map((c) => (
                            <option key={c}>{c}</option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type={f.kind === "text" ? "text" : "number"}
                          value={String(current)}
                          min={f.minimum ?? undefined}
                          max={f.maximum ?? undefined}
                          step={f.kind === "number" ? 0.01 : 1}
                          onChange={(e) =>
                            edit(
                              f,
                              f.kind === "text"
                                ? e.target.value
                                : Number(e.target.value),
                            )
                          }
                        />
                      )}
                    </label>
                  );
                })}
              </div>
            </section>
          )}
          {category === "Chat" && !search && value && (
            <section>
              <p className="muted">
                Conversation:{" "}
                {value.chat_id === chatId
                  ? "current conversation"
                  : "conversation selected when Settings opened"}
              </p>
              <label className="field">
                Prompt preset
                <select
                  defaultValue=""
                  onChange={(e) =>
                    setDraft({
                      ...value,
                      system_prompt:
                        schema?.presets[e.target.value] || value.system_prompt,
                    })
                  }
                >
                  <option value="" disabled>
                    Choose a preset
                  </option>
                  {Object.keys(schema?.presets || {}).map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
              </label>
              <label className="field">
                System prompt
                <textarea
                  rows={7}
                  value={value.system_prompt}
                  onChange={(e) =>
                    setDraft({ ...value, system_prompt: e.target.value })
                  }
                />
              </label>
            </section>
          )}
          {category === "OCR" && !search && (
            <button
              onClick={() =>
                void window.olive
                  .fileAction({ action: "ocr" })
                  .then((path) => {
                    if (typeof path === "string" && value)
                      setDraft({
                        ...value,
                        settings: { ...value.settings, ocr_executable: path },
                      });
                  })
                  .catch(report)
              }
            >
              Choose OCR executable
            </button>
          )}
          {category === "Knowledge" && !search && value && (
            <button
              onClick={() =>
                setDraft({
                  ...value,
                  params: { ...value.params, rag_top_k: 6 },
                  settings: {
                    ...value.settings,
                    rag_semantic_weight: 0.65,
                    rag_lexical_weight: 0.35,
                    rag_minimum_score: 0.08,
                  },
                })
              }
            >
              Reset retrieval defaults
            </button>
          )}
          {value && (
            <div hidden={category !== "Permissions" || Boolean(search)}>
              <Permissions report={report} />
            </div>
          )}
          {value && (
            <div hidden={category !== "Desktop Control" || Boolean(search)}>
              <DesktopPolicies report={report} />
            </div>
          )}
          {value && (
            <div hidden={category !== "Models" || Boolean(search)}>
              <label className="field">
                Current model nickname
                <input
                  value={value.alias}
                  onChange={(e) =>
                    setDraft({ ...value, alias: e.target.value })
                  }
                />
              </label>
              <Models report={report} />
            </div>
          )}
          {category === "Diagnostics" && !search && (
            <Diagnostics chatId={chatId} report={report} />
          )}
          {category === "Backup & Data" && !search && (
            <section>
              <h2>Backup & Data</h2>
              <p>
                Choose a destination with the native file dialog. Restore
                creates a safety backup and requires a restart.
              </p>
              <div className="row">
                {(["backup", "restore", "export-memory"] as const).map(
                  (action) => (
                    <button
                      key={action}
                      disabled={action === "restore" && initializing}
                      title={
                        action === "restore" && initializing
                          ? "Restore becomes available after startup work finishes."
                          : undefined
                      }
                      onClick={() =>
                        void window.olive
                          .fileAction({ action })
                          .then((result) => {
                            if (result) setNotice(String(result));
                          })
                          .catch(report)
                      }
                    >
                      {
                        {
                          backup: "Create backup",
                          restore: "Restore backup",
                          "export-memory": "Export memories",
                        }[action]
                      }
                    </button>
                  ),
                )}
                {initializing && (
                  <p>
                    Startup checks are still running. Restore becomes available
                    when they finish.
                  </p>
                )}
                <button
                  onClick={() =>
                    void call("data.maintenance", {})
                      .then(setMaintenance)
                      .catch(report)
                  }
                >
                  Inspect data maintenance
                </button>
              </div>
              {maintenance !== undefined && (
                <Details value={maintenance} title="Maintenance findings" />
              )}
            </section>
          )}
          {search && !fields.length && (
            <p>Choose a matching category, or try another search.</p>
          )}
          <p role="status">{notice}</p>
        </div>
      </div>
    </WorkspacePage>
  );
}
