import { LayoutControls } from "./LayoutControls";
import { useEffect, useState } from "react";
import {
  Activity,
  BookOpen,
  Brain,
  Code2,
  Cpu,
  Database,
  Globe,
  Mail,
  MessageSquare,
  Monitor,
  MonitorSmartphone,
  Palette,
  ScanText,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Telescope,
} from "lucide-react";
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
  navigate,
}: {
  /** Opens another space (Devices lives in its own workspace). */
  navigate?: (id: string) => void;
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
  // V2 grouping over the existing categories; ids are unchanged.
  const groups: { label: string; items: { id: string; label: string; icon: typeof Search }[] }[] = [
    { label: "", items: [{ id: "General", label: "General", icon: SlidersHorizontal }, { id: "Appearance", label: "Appearance", icon: Palette }] },
    {
      label: "AI",
      items: [
        { id: "Models", label: "Models", icon: Cpu },
        { id: "Chat", label: "Chat", icon: MessageSquare },
        { id: "Memory", label: "Memory", icon: Brain },
        { id: "Knowledge", label: "Knowledge", icon: BookOpen },
        { id: "Research", label: "Research", icon: Telescope },
        { id: "OCR", label: "OCR", icon: ScanText },
      ],
    },
    {
      label: "Workspaces",
      items: [
        { id: "Studio", label: "Studio", icon: Code2 },
        { id: "Browser", label: "OLIVE GO", icon: Globe },
        { id: "Desktop Control", label: "Desktop Control", icon: Monitor },
      ],
    },
    {
      label: "Connect & accounts",
      items: [
        { id: "Devices", label: "Devices", icon: MonitorSmartphone },
        { id: "Connections", label: "Mail connections", icon: Mail },
      ],
    },
    { label: "Privacy & Security", items: [{ id: "Permissions", label: "Permissions", icon: ShieldCheck }] },
    {
      label: "Data",
      items: [
        { id: "Backup & Data", label: "Backup & Data", icon: Database },
        { id: "Diagnostics", label: "Diagnostics", icon: Activity },
      ],
    },
  ];
  const categoryKeywords: Record<string, string> = {
    Devices: "devices connect pair paired permissions",
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
  // The unsaved-changes bar appears only while the draft differs from what
  // the runtime last returned.
  const dirty = Boolean(draft && resource.data && JSON.stringify(draft) !== JSON.stringify(resource.data.value));
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
      setDraft(undefined);
      resource.setData((current) => (current ? { ...current, value: saved } : current));
      setNotice("Settings saved to the shared runtime.");
    } catch (e) {
      report(e);
    } finally {
      setSaving(false);
    }
  };
  const categoryLabel = groups.flatMap((g) => g.items).find((i) => i.id === category)?.label || category;
  return (
    <WorkspacePage
      layout="fill"
      className="settings-v2"
      title="Settings"
      bare
      description="Your preferences, local services and permissions."
      rail={
        <aside className="ws-rail settings-rail" aria-label="Settings navigation">
          <label className="search settings-search">
            <Search size={14} aria-hidden="true" />
            <input
              aria-label="Search settings"
              placeholder="Find a setting"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <nav aria-label="Settings categories" className="settings-nav">
            {groups.map((group) => {
              const items = group.items.filter(
                (c) =>
                  !search ||
                  (c.id + " " + c.label + " " + (categoryKeywords[c.id] || ""))
                    .toLowerCase()
                    .includes(search.toLowerCase()) ||
                  fields.some((f) => f.category === c.id),
              );
              if (!items.length) return null;
              return (
                <div className="settings-nav-group" key={group.label || "top"}>
                  {group.label && <span className="settings-nav-label">{group.label}</span>}
                  {items.map((c) => (
                    <button
                      key={c.id}
                      className={category === c.id ? "selected" : ""}
                      aria-current={category === c.id ? "page" : undefined}
                      onClick={() => {
                        if (c.id === "Devices") {
                          navigate?.("devices");
                          return;
                        }
                        setCategory(c.id);
                        setSearch("");
                      }}
                    >
                      <c.icon size={15} aria-hidden="true" />
                      {c.label}
                    </button>
                  ))}
                </div>
              );
            })}
          </nav>
        </aside>
      }
    >
      <section className="ws-main scroll settings-main" aria-label={categoryLabel}>
      {resource.error && (
        <p role="alert" className="notice" data-tone="error">
          {resource.error}
          <button className="compact" onClick={() => void resource.refresh()}>Retry</button>
        </p>
      )}
      <div className="settings-layout">
        <div className="settings-content">
          {category === "Connections" && !search && <MailConnections/>}
          {category === "Browser" && !search && <BrowserSettings report={report}/>}
          {search && <p className="side-note">Select a matching category to open its controls.</p>}
          {category === "Appearance" && !search && (
            <section className="settings-section">
              <header className="settings-head">
                <h2>Appearance</h2>
                <p>How OLIVE looks on this device.</p>
              </header>
              <h3 className="settings-group-title">Theme</h3>
              <div className="settings-group theme-pick" role="group" aria-label="Theme">
                {(["system", "light", "dark"] as const).map((t) => (
                  <button key={t} className="theme-opt" data-theme-opt={t} aria-pressed={theme === t} onClick={() => setTheme(t)}>
                    <span className="theme-prev" aria-hidden="true">
                      <i />
                      <i />
                    </span>
                    {t === "system" ? "Match system" : t === "dark" ? "Dark" : "Light"}
                  </button>
                ))}
              </div>
              <h3 className="settings-group-title">Text</h3>
              <div className="settings-group">
                <label className="setting-row">
                  <span className="setting-text">
                    <strong>Text and interface size</strong>
                    <span>Scales every workspace, including Studio chrome.</span>
                  </span>
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
              </div>
              <h3 className="settings-group-title">Motion</h3>
              <div className="settings-group">
                <label className="setting-row">
                  <span className="setting-text">
                    <strong>Reduce motion</strong>
                    <span>Removes transitions and stops the compact Core from animating.</span>
                  </span>
                  <input type="checkbox" role="switch" className="switch" aria-label="Reduce motion" checked={reduced} onChange={(e) => setReduced(e.target.checked)} />
                </label>
              </div>
              <h3 className="settings-group-title">Startup and layout</h3>
              <div className="settings-group">
                <div className="setting-row">
                  <span className="setting-text">
                    <strong>OLIVE setup</strong>
                    <span>Check this computer, install runtimes and models, or repair them.</span>
                  </span>
                  <button type="button" onClick={() => window.dispatchEvent(new Event("olive:open-setup"))}>Open setup</button>
                </div>
                <label className="setting-row">
                  <span className="setting-text">
                    <strong>Start on Home</strong>
                    <span>Skip the Welcome screen when OLIVE opens.</span>
                  </span>
                  <input
                    type="checkbox"
                    role="switch"
                    className="switch"
                    aria-label="Start on Home"
                    checked={skip}
                    onChange={(e) => {
                      setSkip(e.target.checked);
                      localStorage.setItem("skipWelcome", String(e.target.checked));
                    }}
                  />
                </label>
                <label className="setting-row">
                  <span className="setting-text">
                    <strong>Developer Mode</strong>
                    <span>Adds a Diagnostics shortcut to navigation. Permissions, approvals and safety information stay the same.</span>
                  </span>
                  <input type="checkbox" role="switch" className="switch" aria-label="Developer Mode" checked={developer} onChange={(e) => setDeveloper(e.target.checked)} />
                </label>
                <div className="setting-row setting-row-block">
                  <LayoutControls resetNavigation={resetLayout} />
                </div>
              </div>
            </section>
          )}
          {fields.length > 0 && value && (
            <section className="settings-section">
              <header className="settings-head">
                <h2>{search ? "Matching settings" : categoryLabel}</h2>
              </header>
              <div className="settings-group">
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
                      className="setting-row"
                      key={`${f.target}.${f.key}`}
                    >
                      <span className="setting-text">
                        <strong>{f.label}</strong>
                        {search && <span>{f.category}</span>}
                      </span>
                      {f.kind === "bool" ? (
                        <input
                          type="checkbox"
                          role="switch"
                          className="switch"
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
          <p role="status" className="settings-notice">{notice}</p>
        </div>
      </div>
      </section>
      {dirty && (
        <div className="settings-savebar" role="region" aria-label="Unsaved settings">
          <span>Unsaved changes</span>
          <button className="compact quiet" disabled={saving} onClick={() => setDraft(undefined)}>
            Revert
          </button>
          <button className="compact primary" disabled={!value || saving} onClick={() => void save()}>
            {saving ? "Saving…" : "Save settings"}
          </button>
        </div>
      )}
    </WorkspacePage>
  );
}
