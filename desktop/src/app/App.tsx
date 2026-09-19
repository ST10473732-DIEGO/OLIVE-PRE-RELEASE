import type { RecordTarget } from "../services/handoff";
import { HomePage } from "../features/Home";
import { Welcome } from "../features/Welcome";
import {
  Fragment,
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
  useReducer,
} from "react";
import { MotionConfig } from "motion/react";
import { ArrowRight, Moon, Plug, Search, Square, Sun, X } from "lucide-react";
import { Navigation } from "./Navigation";
import { NarrowBar } from "./NarrowBar";
import { featureById, features, searchFeatures } from "../navigation/features";
import {
  outputReducer,
  validationChannel,
  commandChannel,
  jobChannel,
  type CommandOutput,
  type JobOutput,
  type Validation,
} from "../services/studioOutput";
import { ApprovalSummary } from "../components/ApprovalSummary";
import { runtimeState as describeRuntime } from "../services/runtimeState";
import { tooling } from "../features/studio/tooling";
import { loadActiveWorkspace, saveActiveWorkspace } from "../features/studio/sessions";
import { Core } from "../components/Core";
import { Sheet } from "../components/Sheet";
import { Chat } from "../features/Chat";
import { Connections } from "../features/Connections";
import { Go } from '../features/go/Go';
import {
  call,
  type Approval,
  type Chat as ChatRecord,
  type Snapshot,
  type WireEvent,
  type Workspace,
} from "../services/api";
const Studio = lazy(() => import("../features/Studio"));
const SettingsPage = lazy(() => import("../features/settings/Settings"));
const MemoryPage = lazy(() => import("../features/Memory"));
const ProjectsPage = lazy(() => import("../features/Projects"));
const KnowledgePage = lazy(() => import("../features/Knowledge"));
const AgentPage = lazy(() => import("../features/Agent"));
const ResearchPage = lazy(() => import("../features/research/Research"));
const DesktopPage = lazy(() => import("../features/desktop/Desktop"));
const CalendarPage = lazy(() => import("../features/personal/Calendar"));
const TasksPage = lazy(() => import("../features/personal/Tasks"));
const RemindersPage = lazy(() => import("../features/personal/Reminders"));
const MailPage = lazy(() => import("../features/mail/Mail"));
import "../features/personal/personal.css";
import Today from "../features/personal/Today";
type Route = string;
export default function App() {
  const [entered, setEntered] = useState(
    localStorage.getItem("skipWelcome") === "true",
  );
  const [interfaceScale, setInterfaceScale] = useState(() => {
    const stored = Number(localStorage.getItem("interfaceScale"));
    return [1, 1.1, 1.25, 1.5].includes(stored) ? stored : 1;
  });
  useEffect(() => {
    void window.olive
      .setInterfaceScale(interfaceScale)
      .then(() =>
        localStorage.setItem("interfaceScale", String(interfaceScale)),
      )
      .catch(() => setError("The interface size could not be updated."));
  }, [interfaceScale]);
  const [route, setRoute] = useState<Route>("home");
  // A visited route stays mounted (hidden) so drafts, terminals and debugger
  // views survive navigating away and back.
  const [visited, setVisited] = useState<string[]>(["home"]);
  const mounted = (id: string) => visited.includes(id);
  const [navCompact, setNavCompact] = useState(
    () => localStorage.getItem("navigationCompact") === "true",
  );
  useEffect(() => {
    localStorage.setItem("navigationCompact", String(navCompact));
  }, [navCompact]);
  const [navOverlay, setNavOverlay] = useState(false);
  // Narrow windows use the same pane as a dismissable overlay.
  // Keep this in step with the narrow shell media query in workspaces.css.
  const [narrow, setNarrow] = useState(() => window.innerWidth < 940);
  useEffect(() => {
    const measure = () => setNarrow(window.innerWidth < 940);
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);
  useEffect(() => {
    if (!narrow) setNavOverlay(false);
  }, [narrow]);
  const [projectCreate, setProjectCreate] = useState(0);
  // Studio requests: select a workspace, or open the New project wizard.
  const [studioRequest, setStudioRequest] = useState({ id: "", revision: 0 });
  const [newProjectRequest, setNewProjectRequest] = useState(0);
  const [diagnosticsRequest, setDiagnosticsRequest] = useState(0);
  const [browserSettingsRequest, setBrowserSettingsRequest] = useState(0);
  const [handoffs, setHandoffs] = useState<Record<string, RecordTarget>>({});
  const [nativeCreate,setNativeCreate]=useState<Record<string,number>>({});
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [chat, setChat] = useState<ChatRecord | null>(null);
  const [error, setError] = useState("");
  const [state, setState] = useState("Starting");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");
  // Studio reopens the workspace that was showing, but never resumes what was
  // running inside it: terminals, debuggers and commands all start closed.
  const [workspace, setWorkspace] = useState(loadActiveWorkspace);
  const [outputs, updateOutput] = useReducer(outputReducer, {
    channels: [],
    selected: {},
  });
  useEffect(() => {
    saveActiveWorkspace(workspace);
  }, [workspace]);
  useEffect(() => {
    // A remembered workspace the runtime no longer knows is simply forgotten.
    const known = snapshot?.workspaces;
    if (workspace && known && !known.some((w) => w.id === workspace)) setWorkspace("");
  }, [snapshot?.workspaces, workspace]);
  const channels = outputs.channels.filter((c) => c.workspace_id === workspace);
  const selectedOutput = channels.find(
    (c) => c.id === outputs.selected[workspace],
  );
  const output = selectedOutput?.text || "";
  const setOutput = (text: string) =>
    updateOutput({
      channel: {
        id: `details:${workspace}`,
        workspace_id: workspace,
        label: "Workspace details",
        text,
      },
    });
  const [activity, setActivity] = useState(false);
  const [palette, setPalette] = useState(false);
  // The palette query is its own state and starts empty every time it opens.
  const [paletteQuery, setPaletteQuery] = useState("");
  const openPalette = useCallback((open: boolean) => {
    if (open) setPaletteQuery("");
    setPalette(open);
  }, []);
  const [developer, setDeveloper] = useState(
    localStorage.getItem("developerMode") === "true",
  );
  useEffect(() => {
    localStorage.setItem("developerMode", String(developer));
  }, [developer]);
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "dark");
  const [reduced, setReduced] = useState(
    localStorage.getItem("reducedMotion") === "true",
  );
  const [coreMotion, setCoreMotion] = useState(() => {
    const saved = localStorage.getItem("coreMotion");
    return saved === "play" || saved === "pause" ? saved : "system";
  });
  useEffect(() => {
    document.documentElement.dataset.coreMotion = coreMotion;
    localStorage.setItem("coreMotion", coreMotion);
  }, [coreMotion]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [connections, setConnections] = useState(false);
  const chatRef = useRef(chat);
  chatRef.current = chat;
  const inFlight = useRef(false);
  const sequence = useRef(0);
  const report = useCallback((e: unknown) => {
    setError(
      e instanceof Error ? e.message : "The request could not complete.",
    );
  }, []);
  const refresh = useCallback(async () => {
    const next = await call<Snapshot>("runtime.snapshot", {});
    setSnapshot(next);
    if (next.activity) {
      setState(next.activity.state);
      setBusy(
        next.activity.items.some(
          (item) =>
            item.chat_id === next.chat.id &&
            item.method.startsWith("interaction."),
        ) || next.chat.generating,
      );
    }
    for (const command of next.commands || [])
      updateOutput({ channel: commandChannel(command), restore: true });
    for (const validation of next.validations || [])
      updateOutput({ channel: validationChannel(validation), restore: true });
    for (const run of next.runs || [])
      updateOutput({
        channel: {
          id: run.id,
          workspace_id: run.workspace_id,
          runState: run.state,
          acceptsInput: Boolean(run.accepts_input),
          label: `Run · ${run.state} · ${run.id.slice(0, 6)}`,
          text: `${run.stdout || ""}${run.stderr || ""}\nState: ${run.state}`,
        },
        restore: true,
      });
    setApprovals(next.approvals);
    setChat((current) =>
      current?.id === next.chat.id
        ? current.generating
          ? current
          : { ...next.chat, draft: current.draft }
        : next.chat,
    );
  }, []);
  useEffect(() => {
    const unsubscribe = window.olive.subscribe((event: WireEvent) => {
      if (event.topic === 'native.notification_failure') {
        setError('Desktop notifications are unavailable. Review completion and reminder history in OLIVE.');
      }
      if (event.topic === "runtime.lost") {
        setState("Disconnected");
        setBusy(false);
        setError(
          "Python disconnected. No actions were replayed. Restart OLIVE after reviewing any uncertain work.",
        );
        return;
      }
      tooling.handle(event);
      if (event.seq <= sequence.current) return;
      sequence.current = event.seq;
      const data = event.data as Record<string, unknown>;
      if (event.topic === "runtime.activity") {
        setState(String(data.state));
        setSnapshot(previous => previous ? {...previous, activity: event.data as Snapshot["activity"]} : previous);
        const items = data.items as { chat_id?: string; method: string }[];
        setBusy(
          items.some(
            (item) =>
              item.chat_id === chatRef.current?.id &&
              item.method.startsWith("interaction."),
          ) || Boolean(chatRef.current?.generating),
        );
      }
      if (event.topic === "chat") {
        const value = event.data as ChatRecord;
        if (!chatRef.current || value.id === chatRef.current.id) {
          setChat((current) =>
            current?.id === value.id
              ? { ...value, draft: current.draft }
              : value,
          );
          setBusy(value.generating);
        }
      }
      if (event.topic === "chat_stream")
        setChat((c) =>
          c && c.id === data.chat_id
            ? { ...c, partial: String(data.text), generating: true }
            : c,
        );
      if (event.topic === "approval") {
        setApprovals((a) => [
          ...a.filter((x) => x.id !== data.id),
          event.data as Approval,
        ]);
        setState("Approval required");
      }
      if (event.topic === "approval.closed")
        setApprovals((a) => a.filter((x) => x.id !== data.id));
      if (event.topic === "run")
        updateOutput({
          channel: {
            id: String(data.id),
            workspace_id: String(data.workspace_id),
            runState: String(data.state),
            acceptsInput: Boolean(data.accepts_input),
            label: `Run · ${data.state} · ${String(data.id).slice(0, 6)}`,
            text: `${data.stdout || ""}${data.stderr || ""}\nState: ${data.state}`,
          },
        });
      if (event.topic === "studio.command")
        updateOutput({ channel: commandChannel(event.data as CommandOutput) });
      if (event.topic === "studio.validation")
        updateOutput({ channel: validationChannel(event.data as Validation) });
      if (event.topic === "build.progress" || event.topic === "build.result")
        updateOutput({ channel: jobChannel(event.data as JobOutput) });
      if (event.topic === "workspaces")
        setSnapshot((s) =>
          s ? { ...s, workspaces: event.data as Workspace[] } : s,
        );
      if (event.topic === "studio.selection" && typeof data.workspace_id === "string") {
        const id = data.workspace_id;
        setWorkspace(id);
        setStudioRequest((current) => ({ id, revision: current.revision + 1 }));
      }
      if (
        ["runtime.ready", "runtime.initialized", "chats", "models"].includes(
          event.topic,
        )
      )
        void refresh().catch(report);
    });
    void refresh().catch(report);
    return unsubscribe;
  }, [refresh, report]);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.reduced = String(reduced);
    localStorage.setItem("theme", theme);
    localStorage.setItem("reducedMotion", String(reduced));
  }, [theme, reduced]);
  useEffect(() => {
    const listener = (e: KeyboardEvent) => {
      if (
        (e.ctrlKey || e.metaKey) &&
        e.shiftKey &&
        e.key.toLowerCase() === "p"
      ) {
        e.preventDefault();
        if (palette) setPalette(false);
        else openPalette(true);
      }
      if (
        (e.ctrlKey || e.metaKey) &&
        e.shiftKey &&
        e.key.toLowerCase() === "o"
      ) {
        e.preventDefault();
        setNavOverlay((value) => !value);
      }
      if (!entered && e.key === "Enter") setEntered(true);
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [entered, palette, openPalette]);
  const openChat = useCallback((record: ChatRecord) => {
    setChat(record);
    setRoute("chat");
    setVisited((current) => (current.includes("chat") ? current : [...current, "chat"]));
    setPalette(false);
    setNavOverlay(false);
  }, []);
  // Studio owns its open workspaces; navigating there selects one without
  // discarding any other open workspace session.
  const openStudio = useCallback((id: string) => {
    if (id) setWorkspace(id);
    setStudioRequest((value) => (id ? { id, revision: value.revision + 1 } : value));
    setRoute("studio");
    setVisited((current) => (current.includes("studio") ? current : [...current, "studio"]));
    setPalette(false);
    setNavOverlay(false);
  }, []);
  const navigate = (id: string) => {
    setPalette(false);
    setNavOverlay(false);
    if (id === "connections") {
      setConnections(true);
      return;
    }
    if (id === "diagnostics") {
      setRoute("settings");
      setDiagnosticsRequest((value) => value + 1);
      setVisited((current) => (current.includes("settings") ? current : [...current, "settings"]));
      return;
    }
    const feature = featureById(id);
    if (!feature) {
      setError("That feature is not available in this application.");
      return;
    }
    if (id === "chat") {
      const current = chatRef.current;
      if (current) {
        openChat(current);
        return;
      }
    }
    setRoute(id);
    setVisited((current) => (current.includes(id) ? current : [...current, id]));
  };
  const submit = async (
    text: string,
    context?: {
      workspace_id: string;
      project_id: string;
      path?: string;
      selection?: string;
    },
    researchMode?: "Quick" | "Deep",
  ) => {
    if (!chat || inFlight.current || busy || !text.trim()) return;
    inFlight.current = true;
    setBusy(true);
    setState("Thinking");
    setError("");
    try {
      if (context?.path !== undefined)
        await call("interaction.studio", {
          chat_id: chat.id,
          text,
          workspace_id: context.workspace_id,
          project_id: context.project_id,
          path: context.path,
          selection: context.selection || "",
        });
      else if (context)
        await call("interaction.launch", {
          chat_id: chat.id,
          text,
          ...context,
        });
      else await call("interaction.submit", { chat_id: chat.id, text, ...(researchMode ? {research_mode: researchMode} : {}) });
      await refresh();
    } catch (e) {
      report(e);
    } finally {
      inFlight.current = false;
      setBusy(false);
      await refresh().catch(report);
    }
  };
  const cancel = () => {
    if (chat)
      void call("interaction.cancel", { chat_id: chat.id })
        .then(refresh)
        .catch(report);
  };
  const runtimeState = describeRuntime(state, snapshot, approvals.length, busy);
  const currentApproval = approvals[0];
  return (
    <MotionConfig reducedMotion={reduced ? "always" : "user"}>
      <div className="app">
        {!entered ? (
          <Welcome
            state={state}
            ready={Boolean(snapshot)}
            runtime={runtimeState}
            enter={() => setEntered(true)}
          />
        ) : (
          <>
            {narrow && (
              <NarrowBar
                route={route}
                activity={state}
                state={runtimeState.label}
                detail={runtimeState.detail}
                openNavigation={() => setNavOverlay(true)}
                openActivity={() => setActivity(true)}
              />
            )}
            {(!narrow || navOverlay) && (
              <Navigation
                route={route}
                navigate={navigate}
                activity={state}
                state={runtimeState.label}
                detail={runtimeState.detail}
                approvals={approvals.length}
                compact={navCompact}
                setCompact={setNavCompact}
                developer={developer}
                overlay={narrow && navOverlay}
                closeOverlay={() => setNavOverlay(false)}
                openPalette={() => openPalette(true)}
                openActivity={() => setActivity(true)}
              />
            )}
            <div className="page">
              {route === "home" && (
                <HomePage
                  openRecord={(feature,id)=>{setHandoffs(current=>({...current,[feature]:{id,revision:(current[feature]?.revision||0)+1}}));navigate(feature);}}
                  reduced={reduced}
                  draft={draft}
                  setDraft={setDraft}
                  navigate={navigate}
                  submit={submit}
                  snapshot={snapshot}
                  setActivity={setActivity}
                  busy={busy || !!snapshot?.initializing}
                  cancel={cancel}
                  openChat={openChat}
                  openStudio={openStudio}
                  report={report}
                  approvals={approvals.length}
                  runtimeState={runtimeState}
                />
              )}
              {route === "chat" && snapshot && chat && (
                <Chat
                  key={chat.id}
                  snapshot={snapshot}
                  chat={chat}
                  setChat={setChat}
                  busy={busy || chat.generating || !!snapshot.initializing}
                  submit={(text, mode) => submit(text, undefined, mode)}
                  cancel={cancel}
                  report={report}
                />
              )}
              {route === 'browser' && <Go ask={text => {setRoute('chat'); void submit(text);}} openSettings={() => {setBrowserSettingsRequest(n => n + 1); navigate('settings');}} report={report} />}
              {mounted("agent") && chat && (
                <div className="route-host" hidden={route !== "agent"}>
                  <Suspense
                    fallback={<div className="loading">Opening Agent…</div>}
                  >
                    <AgentPage
                      target={handoffs.agent}
                      chat={chat}
                      workspaces={snapshot?.workspaces || []}
                      workspaceId={workspace}
                      setWorkspaceId={setWorkspace}
                      runtimeState={state}
                      busy={busy}
                      submit={submit}
                      cancel={cancel}
                      report={report}
                    />
                  </Suspense>
                </div>
              )}
              {mounted("desktop") && chat && (
                <div className="route-host" hidden={route !== "desktop"}>
                  <Suspense
                    fallback={
                      <div className="loading">Opening Desktop Control…</div>
                    }
                  >
                    <DesktopPage
                      chat={chat}
                      submit={submit}
                      busy={busy}
                      report={report}
                      settings={() => navigate("settings")}
                    />
                  </Suspense>
                </div>
              )}
              {mounted("research") && chat && (
                <div className="route-host" hidden={route !== "research"}>
                  <Suspense
                    fallback={<div className="loading">Opening Research…</div>}
                  >
                    <ResearchPage
                      target={handoffs.research}
                      chatId={chat.id}
                      report={report}
                    />
                  </Suspense>
                </div>
              )}
              {mounted("memory") && (
                <div className="route-host" hidden={route !== "memory"}>
                  <Suspense
                    fallback={<div className="loading">Opening Memory…</div>}
                  >
                    <MemoryPage target={handoffs.memory} report={report} />
                  </Suspense>
                </div>
              )}
              {mounted("mail") && <div className="route-host" hidden={route!=="mail"}><Suspense fallback={<p>Opening Mail…</p>}><MailPage target={handoffs.mail}/></Suspense></div>}
              {mounted("calendar") && <div className="route-host" hidden={route!=="calendar"}><Suspense fallback={<p>Opening Calendar…</p>}><CalendarPage target={handoffs.calendar} createRequest={nativeCreate.calendar}/></Suspense></div>}
              {mounted("tasks") && <div className="route-host" hidden={route!=="tasks"}><Suspense fallback={<p>Opening Tasks…</p>}><TasksPage target={handoffs.tasks} createRequest={nativeCreate.tasks}/></Suspense></div>}
              {mounted("reminders") && <div className="route-host" hidden={route!=="reminders"}><Suspense fallback={<p>Opening Reminders…</p>}><RemindersPage openRecord={(kind,id)=>{const feature=kind==="event"?"calendar":"tasks";setHandoffs(current=>({...current,[feature]:{id,revision:(current[feature]?.revision||0)+1}}));navigate(feature);}}/></Suspense></div>}
              {mounted("knowledge") && chat && (
                <div className="route-host" hidden={route !== "knowledge"}>
                  <Suspense
                    fallback={<div className="loading">Opening Knowledge…</div>}
                  >
                    <KnowledgePage
                      target={handoffs.knowledge}
                      chatId={chat.id}
                      report={report}
                    />
                  </Suspense>
                </div>
              )}
              {mounted("projects") && (
                <div className="route-host" hidden={route !== "projects"}>
                  <Suspense
                    fallback={<div className="loading">Opening Projects…</div>}
                  >
                    <ProjectsPage
                      createRequest={projectCreate}
                      report={report}
                      openRecord={(feature, id, kind, chat_id) => {
                        if (
                          ["agent", "research", "knowledge", "memory", "calendar", "tasks", "mail"].includes(
                            feature,
                          )
                        ) {
                          setHandoffs((current) => ({
                            ...current,
                            [feature]: {
                              id,
                              kind,
                              chat_id,
                              revision: (current[feature]?.revision || 0) + 1,
                            },
                          }));
                          navigate(feature);
                        }
                        if (feature === "studio") openStudio(id);
                        if (feature === "chat")
                          void call<ChatRecord>("chat.select", { chat_id: id })
                            .then(openChat)
                            .catch(report);
                      }}
                    />
                  </Suspense>
                </div>
              )}
              {mounted("settings") && chat && (
                <div className="route-host" hidden={route !== "settings"}>
                  <Suspense
                    fallback={<div className="loading">Opening Settings…</div>}
                  >
                    <SettingsPage
                      interfaceScale={interfaceScale}
                      setInterfaceScale={setInterfaceScale}
                      resetLayout={() => setInterfaceScale(1)}
                      initializing={snapshot?.initializing ?? true}
                      developer={developer}
                      setDeveloper={setDeveloper}
                      chatId={chat.id}
                      report={report}
                      theme={theme}
                      setTheme={setTheme}
                      reduced={reduced}
                      setReduced={setReduced}
                      diagnosticsRequest={diagnosticsRequest}
                      browserRequest={browserSettingsRequest}
                    />
                  </Suspense>
                </div>
              )}
              {mounted("studio") && (
                <div className="route-host" hidden={route !== "studio"}>
                  <Suspense
                    fallback={<div className="loading">Opening Studio…</div>}
                  >
                    <Studio
                      chat={chat}
                      submit={submit}
                      interactionBusy={busy}
                      workspaces={snapshot?.workspaces || []}
                      buffers={snapshot?.buffers || []}
                      workspaceId={workspace}
                      setWorkspaceId={setWorkspace}
                      selectRequest={studioRequest}
                      newProjectRequest={newProjectRequest}
                      visible={route === "studio"}
                      output={output}
                      channels={channels}
                      selectedOutput={selectedOutput?.id || ""}
                      selectOutput={(id) =>
                        updateOutput({ workspace, select: id })
                      }
                      setOutput={setOutput}
                      report={report}
                      theme={theme}
                    />
                  </Suspense>
                </div>
              )}
            </div>
          </>
        )}
        <Connections
          open={connections}
          close={setConnections}
          report={report}
        />
        {error && (
          <div className="toast" role="alert">
            <span>{error}</span>
            <button
              className="icon-button"
              aria-label="Dismiss notice"
              onClick={() => setError("")}
            >
              <X size={18} />
            </button>
          </div>
        )}
        <Sheet
          open={activity}
          onOpenChange={setActivity}
          title="Activity"
          description="Real work, context and approvals in this session."
        >
          <div className="ws-scope activity-panel">
            <section className="ws-panel raised activity-state" aria-label="Current state">
              <Core state={state} />
              <div className="activity-state-text">
                <h3>
                  {runtimeState.label}
                  {runtimeState.detail ? ` · ${runtimeState.detail}` : ""}
                </h3>
                <p>{runtimeState.full}</p>
                {snapshot?.activity?.summary && (
                  <p className="activity-summary">{snapshot.activity.summary}</p>
                )}
              </div>
            </section>
            <section className="activity-section" aria-label="Controls">
              <p className="ws-eyebrow">Controls</p>
              <div className="activity-actions">
                {busy && (
                  <button onClick={cancel}>
                    <Square size={15} aria-hidden="true" />
                    Cancel current request
                  </button>
                )}
                <button
                  className="danger-action"
                  onClick={() => void window.olive.stopControl().catch(report)}
                >
                  <Square size={15} aria-hidden="true" />
                  Stop desktop control
                </button>
                <span className="activity-shortcut small muted">
                  Emergency shortcut <kbd className="kbd">Ctrl+Alt+Escape</kbd>
                </span>
              </div>
            </section>
            <Today
              compact
              navigate={(id) => {
                setActivity(false);
                navigate(id);
              }}
            />
            <section className="activity-section" aria-label="Context">
              <p className="ws-eyebrow">Context</p>
              <div className="ws-panel activity-context">
                <div className="ws-row-text">
                  <strong>
                    {snapshot?.home.context.file ||
                      snapshot?.home.context.workspace ||
                      "No file or project selected."}
                  </strong>
                  <span>
                    {snapshot?.home.context.file || snapshot?.home.context.workspace
                      ? "Used by Chat and the Agent for this session."
                      : "Open a workspace or file to give OLIVE something to work with."}
                  </span>
                </div>
                <button
                  className="quiet"
                  disabled={!chat || busy}
                  onClick={() => {
                    if (chat)
                      void call("context.clear", { chat_id: chat.id })
                        .then(refresh)
                        .catch(report);
                  }}
                >
                  Clear context
                </button>
              </div>
            </section>
            <section className="activity-section" aria-label="Appearance">
              <p className="ws-eyebrow">Appearance</p>
              <div className="ws-panel activity-settings">
                <div className="activity-setting">
                  <div className="ws-row-text">
                    <strong>Theme</strong>
                    <span>{theme === "dark" ? "Dark ink" : "Light"}</span>
                  </div>
                  <button
                    className="quiet"
                    aria-label="Toggle theme"
                    onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                  >
                    {theme === "dark" ? (
                      <Sun size={15} aria-hidden="true" />
                    ) : (
                      <Moon size={15} aria-hidden="true" />
                    )}
                    {theme === "dark" ? "Light theme" : "Dark theme"}
                  </button>
                </div>
                <label className="setting-row activity-setting">
                  <span className="ws-row-text">
                    <strong>Reduced motion</strong>
                    <span>Turns off page and Core animation.</span>
                  </span>
                  <input
                    type="checkbox"
                    className="ws-switch"
                    aria-label="Reduced motion"
                    checked={reduced}
                    onChange={(e) => setReduced(e.target.checked)}
                  />
                </label>
                <label className="setting-row activity-setting">
                  <span className="ws-row-text">
                    <strong>Core animation</strong>
                    <span>The olive mark in the rail and on Home.</span>
                  </span>
                  <select
                    aria-label="Core animation"
                    value={coreMotion}
                    onChange={(e) => setCoreMotion(e.target.value)}
                    disabled={reduced}
                  >
                    <option value="system">Follow system motion preference</option>
                    <option value="play">Animate Core only</option>
                    <option value="pause">Pause Core animation</option>
                  </select>
                </label>
                <label className="setting-row activity-setting">
                  <span className="ws-row-text">
                    <strong>Show Welcome on startup</strong>
                    <span>The start screen before the workspace.</span>
                  </span>
                  <input
                    type="checkbox"
                    className="ws-switch"
                    aria-label="Show Welcome on startup"
                    defaultChecked={localStorage.getItem("skipWelcome") !== "true"}
                    onChange={(e) =>
                      localStorage.setItem("skipWelcome", String(!e.target.checked))
                    }
                  />
                </label>
              </div>
            </section>
            <section className="activity-section" aria-label="System">
              <p className="ws-eyebrow">System</p>
              <div className="ws-panel activity-context">
                <div className="ws-row-text">
                  <strong>Connections</strong>
                  <span>Mail accounts, messaging and other optional services.</span>
                </div>
                <button className="quiet" onClick={() => setConnections(true)}>
                  <Plug size={15} aria-hidden="true" />
                  Connections
                </button>
              </div>
            </section>
          </div>
        </Sheet>
        <Sheet
          open={palette}
          onOpenChange={openPalette}
          title="Commands"
          description="Go somewhere or start something. Ctrl+Shift+P opens this anywhere."
        >
          <label className="search">
            <Search size={17} aria-hidden="true" />
            <input
              aria-label="Search commands"
              value={paletteQuery}
              onChange={(e) => setPaletteQuery(e.target.value)}
              placeholder="Find a command…"
              autoFocus
            />
          </label>
          <div className="palette-list">
          {[
            { id: "new-chat", name: "New conversation", group: "Start" },
            { id: "new-project", name: "New code project (Studio)", group: "Start" },
            { id: "new-olive-project", name: "New OLIVE Project (group related work)", group: "Start" },
            { id: "new-event", name: "New calendar event", group: "Start" },
            { id: "new-personal-task", name: "New task", group: "Start" },
            { id: "compose-mail", name: "Compose mail", group: "Start" },
            { id: "open-workspace", name: "Open an existing folder in Studio", group: "Start" },
            ...searchFeatures(paletteQuery, features).map((f) => ({
              id: f.id,
              name: `Open ${f.label}`,
              group: "Go to",
            })),
          ]
            .filter((c) => c.group !== "Start" || c.name.toLowerCase().includes(paletteQuery.toLowerCase()))
            .map((c, index, list) => (
              <Fragment key={c.id}>
              {(index === 0 || list[index - 1].group !== c.group) && (
                <span className="palette-group" aria-hidden="true">
                  {c.group}
                </span>
              )}
              <button
                className="recent-row"
                title={featureById(c.id)?.description}
                onClick={() => {
                  if (c.id === "new-chat") {
                    void call<ChatRecord>("chat.new", {})
                      .then(openChat)
                      .catch(report);
                  } else if (c.id === "compose-mail") {
                    setPalette(false);
                    void call<{id:string}>("mail.save_draft",{body:{to:[],subject:"",text:""}})
                      .then(value=>{setHandoffs(current=>({...current,mail:{id:value.id,revision:(current.mail?.revision||0)+1}}));navigate("mail");})
                      .catch(report);
                  } else if (c.id === "new-project") {
                    // A code project on disk, created by the Studio wizard.
                    setNewProjectRequest((value) => value + 1);
                    navigate("studio");
                  } else if (c.id === "new-olive-project") {
                    // An organisational grouping of chats, files and records.
                    setProjectCreate(Date.now());
                    navigate("projects");
                  } else if(c.id==='new-event'||c.id==='new-personal-task'){
                    const feature=c.id==='new-event'?'calendar':'tasks';
                    setNativeCreate(current=>({...current,[feature]:(current[feature]||0)+1}));
                    navigate(feature);
                  } else if (c.id === "open-workspace") {
                    setPalette(false);
                    void window.olive
                      .openWorkspace()
                      .then((value) => {
                        if (value) openStudio(value.id);
                      })
                      .catch(report);
                  } else navigate(c.id);
                }}
              >
                {c.name}
                <ArrowRight size={15} aria-hidden="true" />
              </button>
              </Fragment>
            ))}
          </div>
        </Sheet>
        <Sheet
          open={Boolean(currentApproval)}
          onOpenChange={(open) => {
            if (!open && currentApproval)
              void call("approval.respond", {
                approval_id: currentApproval.id,
                fingerprint: currentApproval.fingerprint,
                approved: false,
              }).catch(report);
          }}
          title="Your approval is needed"
          description="Review the exact action before OLIVE continues. Closing this cancels it."
        >
          {currentApproval && (
            <>
              <ApprovalSummary approval={currentApproval} />
              <div className="approval-actions">
                <button
                  onClick={() =>
                    void call("approval.respond", {
                      approval_id: currentApproval.id,
                      fingerprint: currentApproval.fingerprint,
                      approved: false,
                    }).catch(report)
                  }
                >
                  Cancel
                </button>
                <button
                  className="primary"
                  onClick={() =>
                    void call("approval.respond", {
                      approval_id: currentApproval.id,
                      fingerprint: currentApproval.fingerprint,
                      approved: true,
                    }).catch(report)
                  }
                >
                  Approve this action
                </button>
              </div>
            </>
          )}
        </Sheet>
      </div>
    </MotionConfig>
  );
}
