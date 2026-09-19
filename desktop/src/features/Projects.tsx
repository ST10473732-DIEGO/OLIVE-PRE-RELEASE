import { useEffect, useRef, useState } from "react";
import { call, type Workspace } from "../services/api";
import { useResource } from "../services/useResource";
import {
  WorkspacePage,
  Details,
  Rail,
  Main,
  Panel,
  EmptyState,
  SectionHead,
  Pill,
  Disclosure,
} from "../components/WorkspacePage";
import { Sheet } from "../components/Sheet";
import {
  FolderKanban,
  Search,
  Plus,
  RefreshCw,
  MessageSquare,
  Code2,
  Bot,
  FlaskConical,
  BookOpen,
  Globe,
  Brain,
  CalendarDays,
  ListChecks,
  Mail,
  FolderOpen,
  ShieldCheck,
} from "lucide-react";
const RELATION_ICONS: Record<string, typeof MessageSquare> = {
  Chats: MessageSquare,
  "Workspace/Files": Code2,
  Tasks: Bot,
  Research: FlaskConical,
  Knowledge: BookOpen,
  "Web Knowledge": Globe,
  Memories: Brain,
  Calendar: CalendarDays,
  "Personal Tasks": ListChecks,
  Mail,
};
interface Project {
  id: string;
  title: string;
  description: string;
}
interface Related {
  id: string;
  title?: string;
  subject?: string;
  display_name?: string;
  name?: string;
  request?: string;
  user_request?: string;
  content?: string;
  state?: string;
  root_path?: string;
  question?: string;
  session_id?: string;
  chat_id?: string;
}
export default function Projects({
  createRequest = 0,
  report,
  openRecord,
}: {
  createRequest?: number;
  report: (e: unknown) => void;
  openRecord: (
    feature: string,
    id: string,
    kind?: string,
    chat_id?: string,
  ) => void;
}) {
  const resource = useResource(
    async () => ({
      projects: await call<Project[]>("data.projects", {}),
      workspaces: await call<Workspace[]>("data.workspaces", {}),
    }),
    ["projects", "workspaces"],
  );
  const request = useRef(0);
  const [page, setPage] = useState(0);
  const [relatedPage, setRelatedPage] = useState(0);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Project>();
  const [detail, setDetail] = useState<Record<string, Related[] | Project>>();
  useEffect(() => {
    if (!selected) return;
    let active=true;
    const unsubscribe=window.olive.subscribe(event=>{
      if(event.topic!=="personal.changed")return;
      const generation=++request.current;
      void call<Record<string, Related[] | Project>>("data.project_detail",{project_id:selected.id})
        .then(value=>{if(active&&generation===request.current)setDetail(value);}).catch(report);
    });
    return ()=>{active=false;unsubscribe();};
  }, [selected,report]);
  const [tab, setTab] = useState("Chats");
  const [create, setCreate] = useState(false);
  useEffect(() => {
    if (createRequest) setCreate(true);
  }, [createRequest]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [trust, setTrust] = useState<"approved" | "trusted" | "untrusted">(
    "approved",
  );
  const load = async (p: Project) => {
    const generation = ++request.current;
    setRelatedPage(0);
    setSelected(p);
    setDetail(undefined);
    try {
      const value = await call<Record<string, Related[] | Project>>(
        "data.project_detail",
        { project_id: p.id },
      );
      if (generation === request.current) setDetail(value);
    } catch (e) {
      report(e);
    }
  };
  const rows =
    resource.data?.projects.filter((p) =>
      `${p.title} ${p.description}`.toLowerCase().includes(query.toLowerCase()),
    ) || [];
  const links: Record<string, string> = {
    Chats: "chat",
    "Workspace/Files": "studio",
    Tasks: "agent",
    Research: "research",
    Knowledge: "knowledge",
    "Web Knowledge": "knowledge",
    Memories: "memory",
    Calendar: "calendar",
    "Personal Tasks": "tasks",
    Mail: "mail",
  };
  const continueLabel = (key: string) =>
    key === "Workspace/Files"
      ? "Studio"
      : key === "Tasks"
        ? "Agent"
        : key === "Chats"
          ? "Chat"
          : key === "Web Knowledge"
            ? "Knowledge"
            : key === "Memories"
              ? "Memory"
              : key;
  const countOf = (key: string) => (detail && Array.isArray(detail[key]) ? (detail[key] as Related[]).length : undefined);
  const linkedWorkspaces = selected && detail ? countOf("Workspace/Files") || 0 : 0;
  const total = resource.data?.projects.length || 0;
  return (
    <WorkspacePage
      layout="fill"
      className="projects"
      icon={<FolderKanban size={18} />}
      title="Projects"
      description="Conversations, files and findings connected by project."
      status={total ? `${total} project${total === 1 ? "" : "s"}` : undefined}
      statusTone="idle"
      actions={
        <>
          <button className="icon-button" aria-label="Refresh projects" title="Refresh" onClick={() => void resource.refresh()}>
            <RefreshCw size={16} aria-hidden="true" />
          </button>
          <button className="primary" onClick={() => setCreate(true)}>
            <Plus size={16} aria-hidden="true" />
            New project
          </button>
        </>
      }
      rail={
        <Rail
          wide
          title="All projects"
          label="Project browser"
          foot={
            <Disclosure summary="Approved workspaces" badge={<Pill>{resource.data?.workspaces.length || 0}</Pill>} className="projects-workspaces">
              {resource.data?.workspaces.length ? (
                resource.data.workspaces.map((w) => (
                  <button
                    className="recent-row"
                    key={w.id}
                    onClick={() => openRecord("studio", w.id)}
                  >
                    {w.title}
                    <span className="muted">{w.root_path}</span>
                  </button>
                ))
              ) : (
                <p className="muted small">No approved workspace folders yet.</p>
              )}
            </Disclosure>
          }
        >
          <label className="search projects-search">
            <Search size={15} aria-hidden="true" />
            <input
              aria-label="Search projects"
              placeholder="Search projects…"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(0);
              }}
            />
          </label>
          {resource.error && <p role="alert">{resource.error}</p>}
          <div className="record-list projects-list">
            {rows.slice(page * 30, page * 30 + 30).map((p) => (
              <button
                className={`ws-row record-card project-card ${selected?.id === p.id ? "selected" : ""}`}
                key={p.id}
                aria-pressed={selected?.id === p.id}
                onClick={() => void load(p)}
              >
                <span className="ws-row-icon" aria-hidden="true">
                  <FolderKanban size={15} />
                </span>
                <span className="ws-row-text">
                  <strong>{p.title}</strong>
                  <span className="muted">{p.description || "Local project"}</span>
                </span>
              </button>
            ))}
            {rows.length > 30 && (
              <div className="row projects-paging">
                <button className="quiet" disabled={!page} onClick={() => setPage((p) => p - 1)}>
                  Previous projects
                </button>
                <span>Page {page + 1}</span>
                <button
                  className="quiet"
                  disabled={(page + 1) * 30 >= rows.length}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next projects
                </button>
              </div>
            )}
            {!rows.length && !resource.error && (
              <p className="projects-none">
                {resource.loading || !resource.data
                  ? "Loading projects…"
                  : query ? "No matching projects." : "No projects yet. Create a project to bring your work together."}
              </p>
            )}
          </div>
        </Rail>
      }
    >
      <Main className="projects-main" label="Project">
        {selected ? (
          <>
            <header className="projects-hero">
              <div className="projects-hero-text">
                <h2>{selected.title}</h2>
                {selected.description ? <p>{selected.description}</p> : <p className="muted">No description yet.</p>}
              </div>
              <div className="projects-hero-meta">
                <Pill tone={linkedWorkspaces ? "success" : undefined}>
                  <FolderOpen size={12} aria-hidden="true" />
                  {linkedWorkspaces ? `${linkedWorkspaces} workspace${linkedWorkspaces === 1 ? "" : "s"}` : "No workspace"}
                </Pill>
              </div>
            </header>
            <section className="projects-overview" aria-label="Project overview">
              <SectionHead>Connected work</SectionHead>
              <div className="projects-counts">
                {Object.keys(links).map((key) => {
                  const Icon = RELATION_ICONS[key] || FolderKanban;
                  const n = countOf(key);
                  return (
                    <button
                      key={key}
                      type="button"
                      className={`ws-card interactive projects-count ${tab === key ? "selected" : ""}`}
                      aria-pressed={tab === key}
                      onClick={() => {
                        setTab(key);
                        setRelatedPage(0);
                      }}
                    >
                      <span className="ws-card-icon" aria-hidden="true">
                        <Icon size={16} />
                      </span>
                      <span className="projects-count-number">{n === undefined ? "…" : n}</span>
                      <span className="projects-count-label">{key}</span>
                    </button>
                  );
                })}
              </div>
            </section>
            <div className="ws-grid main-side projects-detail">
              <Panel
                title={tab}
                sub={countOf(tab) === undefined ? "Loading…" : `${countOf(tab)} linked record${countOf(tab) === 1 ? "" : "s"}`}
                icon={(() => {
                  const Icon = RELATION_ICONS[tab] || FolderKanban;
                  return <Icon size={15} />;
                })()}
                className="projects-related"
              >
                <div
                  className="category-tabs projects-tabs"
                  role="navigation"
                  aria-label="Project relationships"
                >
                  {Object.keys(links).map((key) => (
                    <button
                      key={key}
                      className={tab === key ? "selected" : ""}
                      aria-current={tab === key ? "true" : undefined}
                      onClick={() => {
                        setTab(key);
                        setRelatedPage(0);
                      }}
                    >
                      {key}
                      {countOf(key) ? <span className="count" aria-hidden="true">{countOf(key)}</span> : null}
                    </button>
                  ))}
                </div>
                {!detail ? (
                  <p role="status">Loading project relationships…</p>
                ) : (
                  <>
                    {(detail[tab] as Related[]).length === 0 && (
                      <EmptyState
                        compact
                        headingLevel={3}
                        icon={(() => {
                          const Icon = RELATION_ICONS[tab] || FolderKanban;
                          return <Icon size={18} />;
                        })()}
                        title={`No linked ${tab.toLowerCase()}`}
                      >
                        Records linked to this project from {continueLabel(tab)} appear here.
                      </EmptyState>
                    )}
                    <div className="projects-records">
                      {(detail[tab] as Related[])
                        .slice(relatedPage * 30, relatedPage * 30 + 30)
                        .map((record, i) => (
                          <article className="record-card ws-card" key={record.id || i}>
                            <div className="ws-card-head">
                              <div className="ws-card-text">
                                <strong className="title">
                                  {record.title || record.subject ||
                                    record.display_name ||
                                    record.name ||
                                    record.user_request ||
                                    record.request ||
                                    record.question ||
                                    record.content ||
                                    record.id}
                                </strong>
                                {record.state && <p className="ws-card-sub">{record.state}</p>}
                              </div>
                              <button
                                onClick={() =>
                                  openRecord(
                                    links[tab],
                                    tab === "Research"
                                      ? record.session_id || record.id
                                      : record.id,
                                    tab,
                                    record.chat_id,
                                  )
                                }
                              >
                                Continue in {continueLabel(tab)}
                              </button>
                            </div>
                            <Details value={record} title="Linked record" />
                          </article>
                        ))}
                    </div>
                    {(detail[tab] as Related[]).length > 30 && (
                      <div className="row">
                        <button
                          className="quiet"
                          disabled={!relatedPage}
                          onClick={() => setRelatedPage((p) => p - 1)}
                        >
                          Previous records
                        </button>
                        <span>Page {relatedPage + 1}</span>
                        <button
                          className="quiet"
                          disabled={
                            (relatedPage + 1) * 30 >=
                            (detail[tab] as Related[]).length
                          }
                          onClick={() => setRelatedPage((p) => p + 1)}
                        >
                          Next records
                        </button>
                      </div>
                    )}
                  </>
                )}
              </Panel>
              <div className="projects-side">
                <Panel title="Workspace folder" sub="Where this project's code and files live" icon={<ShieldCheck size={15} />}>
                  <label className="field">
                    Workspace execution trust
                    <select
                      value={trust}
                      onChange={(e) => setTrust(e.target.value as typeof trust)}
                    >
                      <option value="approved">Approved local workspace</option>
                      <option value="trusted">Trusted workspace</option>
                      <option value="untrusted">
                        Untrusted code · requires isolation
                      </option>
                    </select>
                  </label>
                  <button
                    onClick={() =>
                      void window.olive
                        .fileAction({
                          action: "workspace",
                          title: selected.title,
                          project_id: selected.id,
                          trust_level: trust,
                        })
                        .then(() => {
                          void resource.refresh();
                          void load(selected);
                        })
                        .catch(report)
                    }
                  >
                    <FolderOpen size={14} aria-hidden="true" />
                    Link a workspace folder
                  </button>
                  <p className="muted small">
                    Linking approves the folder for Studio and the Agent at the chosen trust level. Nothing is copied.
                  </p>
                </Panel>
              </div>
            </div>
          </>
        ) : (
          <EmptyState
            icon={<FolderKanban size={26} />}
            title="Choose a project"
            actions={
              <button className="primary" onClick={() => setCreate(true)}>
                <Plus size={14} aria-hidden="true" />
                Create a project
              </button>
            }
          >
            Inspect its real conversations, workspaces, tasks, research and
            knowledge.
          </EmptyState>
        )}
      </Main>
      <Sheet
        open={create}
        onOpenChange={setCreate}
        title="New project"
        description="A local project connects your work without creating an online account."
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setBusy(true);
            void call<Project>("data.create_project", { title, description })
              .then(async (p) => {
                setCreate(false);
                setTitle("");
                setDescription("");
                await resource.refresh();
                await load(p);
              })
              .catch(report)
              .finally(() => setBusy(false));
          }}
        >
          <label className="field">
            Project title
            <input
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          <label className="field">
            Description
            <textarea
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <button className="primary" disabled={busy || !title.trim()}>
            Create project
          </button>
        </form>
      </Sheet>
    </WorkspacePage>
  );
}
