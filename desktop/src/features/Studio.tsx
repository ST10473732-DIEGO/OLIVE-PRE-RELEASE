import { RemoteStudio } from "./studio/RemoteStudio";
import type { ComponentProps } from "react";
import { usePanelLayout } from "./studio/panelLayout";
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import * as monaco from "monaco-editor";
import EditorWorker from "monaco-editor/editor/editor.worker?worker";
import JsonWorker from "monaco-editor/language/json/json.worker?worker";
import CssWorker from "monaco-editor/language/css/css.worker?worker";
import HtmlWorker from "monaco-editor/language/html/html.worker?worker";
import TsWorker from "monaco-editor/language/typescript/ts.worker?worker";
import {
  FolderOpen,
  FileCode2,
  Play,
  Square,
  FlaskConical,
  Save,
  GitCompare,
  X,
  ChevronsUpDown,
  FilePlus2,
  Bug,
  Hammer,
  PanelLeft,
  Sparkles,
  TerminalSquare,
  AlertCircle,
  ListChecks,
  ScrollText,
  GitBranch,
  Globe,
  Search,
  RefreshCw,
  Link2,
} from "lucide-react";
import { call, type Workspace, type FileBuffer, type Chat } from "../services/api";
import { StudioAssistant, type AssistantSeed, type StudioSubmit } from "./studio/Assistant";
import { ActionMenu } from "../components/ActionMenu";
import { Sheet } from "../components/Sheet";
import { LocalPreview } from "./studio/LocalPreview";
import { WorkspaceTools } from "./studio/WorkspaceTools";
import { GitPanel } from "./studio/GitPanel";
import { Explorer } from "../components/Explorer";
import { TaskResult } from "../components/TaskResult";
import type { OutputChannel } from "../services/studioOutput";
import { Compare } from "./Compare";
import { NewProjectWizard } from "./studio/NewProjectWizard";
import { ProgramInput } from "./studio/ProgramInput";
import { WinFormsDesigner } from "./studio/WinFormsDesigner";
import {
  forgetSession,
  loadOpenWorkspaces,
  saveOpenWorkspaces,
  sessionUi,
  updateSessionUi,
} from "./studio/sessions";
import { Packages } from "./Packages";
import { NewFile } from "./NewFile";
import { tooling, useTooling, relativePath, absolutePath, samePath, type WorkspaceEdit } from "./studio/tooling";
import {
  applyDiagnostics,
  documentSaved,
  findReferences,
  languageFor,
  modelUri,
  prepareRename,
  registerLanguageProviders,
  renameSymbol,
  syncDocument,
  workspaceSymbols,
  type Reference,
} from "./studio/languageClient";
import { decorateModel, useDebugger } from "./studio/debugClient";
import { TerminalPanel } from "./studio/TerminalPanel";
import { ProblemsPanel, useProblems } from "./studio/ProblemsPanel";
import { TestsPanel } from "./studio/TestsPanel";
import { DebugPanel } from "./studio/DebugPanel";
import { WebPanel } from "./studio/WebPanel";
import { EditPreview } from "./studio/EditPreview";
import { ProjectPanel, useProjectScan } from "./studio/ProjectPanel";
const Output = lazy(() => import("./Output"));
self.MonacoEnvironment = {
  getWorker: (_id, label) =>
    label === "json"
      ? new JsonWorker()
      : ["css", "scss", "less"].includes(label)
        ? new CssWorker()
        : ["html", "handlebars", "razor"].includes(label)
          ? new HtmlWorker()
          : ["typescript", "javascript"].includes(label)
            ? new TsWorker()
            : new EditorWorker(),
};
interface OpenFile {
  path: string;
  workspace: string;
  model: monaco.editor.ITextModel;
  hash: string;
  saved: string;
  view?: monaco.editor.ICodeEditorViewState | null;
  unsync?: () => void;
}
const retained = new Map<string, OpenFile>();
const lastPaths = new Map<string, string>();
// Buffers discarded or saved in this session must not be restored from a
// runtime snapshot taken before the discard; the host no longer holds them.
const discarded = new Set<string>();
interface FileState {
  relative_path: string;
  text: string;
  loaded_hash: string;
  saved_text: string;
}
type DockTab = "terminal" | "problems" | "tests" | "output" | "git" | "debug" | "web" | "references";
const DOCK_TABS: { id: DockTab; label: string; icon: typeof Bug }[] = [
  { id: "terminal", label: "Terminal", icon: TerminalSquare },
  { id: "problems", label: "Problems", icon: AlertCircle },
  { id: "tests", label: "Tests", icon: ListChecks },
  { id: "output", label: "Output", icon: ScrollText },
  { id: "git", label: "Git", icon: GitBranch },
  { id: "debug", label: "Debug", icon: Bug },
  { id: "web", label: "Web", icon: Globe },
  { id: "references", label: "References", icon: Link2 },
];
const LANGUAGE_IDS: Record<string, string> = {
  py: "python",
  java: "java",
  xml: "xml",
  gradle: "groovy",
  c: "c",
  cpp: "cpp",
  rs: "rust",
  go: "go",
  yaml: "yaml",
  yml: "yaml",
  ts: "typescript",
  tsx: "typescript",
  js: "javascript",
  json: "json",
  cs: "csharp",
  csproj: "xml",
  sln: "plaintext",
  slnx: "xml",
  props: "xml",
  targets: "xml",
  md: "markdown",
  css: "css",
  html: "html",
  cshtml: "html",
  razor: "html",
};
function LocalStudio({
  chat,
  submit,
  interactionBusy,
  workspaces,
  workspaceId,
  setWorkspaceId,
  selectRequest,
  newProjectRequest = 0,
  visible = true,
  output,
  channels,
  selectedOutput,
  selectOutput,
  setOutput,
  report,
  theme,
  buffers,
}: {
  chat: Chat | null;
  submit: StudioSubmit;
  interactionBusy: boolean;
  workspaces: Workspace[];
  workspaceId: string;
  setWorkspaceId: (id: string) => void;
  /** Bumped when something outside Studio asks for a specific workspace. */
  selectRequest?: { id: string; revision: number };
  /** Bumped when something outside Studio asks for the New project wizard. */
  newProjectRequest?: number;
  // Studio stays mounted while the route is visited; it re-measures on return.
  visible?: boolean;
  output: string;
  channels: OutputChannel[];
  selectedOutput: string;
  selectOutput: (id: string) => void;
  setOutput: (text: string) => void;
  report: (e: unknown) => void;
  theme: string;
  buffers: FileBuffer[];
}) {
  // Studio keeps its own set of open workspaces. Opening another one never
  // replaces the current session; both stay alive with their own state.
  const [openIds, setOpenIds] = useState<string[]>(() => {
    const stored = loadOpenWorkspaces();
    return workspaceId && !stored.includes(workspaceId) ? [...stored, workspaceId] : stored;
  });
  useEffect(() => {
    saveOpenWorkspaces(openIds);
  }, [openIds]);
  const openWorkspace = useCallback(
    (id: string) => {
      if (!id) return;
      setOpenIds((current) => (current.includes(id) ? current : [...current, id]));
      setWorkspaceId(id);
    },
    [setWorkspaceId],
  );
  useEffect(() => {
    if (workspaceId) setOpenIds((current) => (current.includes(workspaceId) ? current : [...current, workspaceId]));
  }, [workspaceId]);
  const [wizard, setWizard] = useState(false);
  const [designerOpen, setDesignerOpen] = useState(false);
  const [closingWorkspace, setClosingWorkspace] = useState<{
    id: string;
    title: string;
    dirty: number;
    running: string[];
  } | null>(null);
  useEffect(() => {
    if (newProjectRequest) setWizard(true);
  }, [newProjectRequest]);
  useEffect(() => {
    if (selectRequest?.id) openWorkspace(selectRequest.id);
  }, [selectRequest?.revision]);
  const [entries, setEntries] = useState<{ path: string; directory: boolean }[]>([]);
  const [active, setActive] = useState(() => sessionUi(workspaceId).activePath || lastPaths.get(workspaceId) || "");
  const [, render] = useState(0);
  const [busy, setBusy] = useState(false);
  const [closing, setClosing] = useState<OpenFile | null>(null);
  const [saveStatus, setSaveStatus] = useState("");
  const validation = [...channels]
    .reverse()
    .find((c) => c.validation && ["running", "cancelling"].includes(c.validation.state))?.validation;
  const selectedValidation = channels.find((c) => c.id === selectedOutput)?.validation;
  const [switching, setSwitching] = useState(false);
  const activeCommand = [...channels]
    .reverse()
    .find((channel) => ["running", "cancelling"].includes(channel.commandState || "") && !channel.id.startsWith("job:"));
  const latestRun = [...channels].reverse().find((c) => c.runState);
  const session = latestRun?.id || "";
  const activeRun = [...channels].reverse().find((c) => ["starting", "running"].includes(c.runState || ""));
  const [comparison, setComparison] = useState<{ disk_text: string; disk_hash: string; file: OpenFile } | null>(null);
  const host = useRef<HTMLDivElement>(null);
  const editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const decorations = useRef<monaco.editor.IEditorDecorationsCollection | null>(null);
  const current = useRef("");
  const diagnostics = useRef<{ file?: string; line?: number; column?: number; severity: string; message: string }[]>([]);
  const workspace = workspaces.find((w) => w.id === workspaceId);
  const root = workspace?.root_path || "";
  const editorPreferences = useRef({ fontSize: 13, fontFamily: "Consolas", tabSize: 4 });
  const key = (path: string) => workspaceId + ":" + path;
  // ---- layout state --------------------------------------------------
  const [explorer, setExplorer] = useState(localStorage.getItem("studioExplorer") !== "false");
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [assistantPinned, setAssistantPinned] = useState<Record<string, boolean>>(() => {
    try {
      return JSON.parse(localStorage.getItem("studioAssistantPinned") || "{}");
    } catch {
      return {};
    }
  });
  const [dock, setDock] = useState<DockTab | "">("");
  const [assistantSeed, setAssistantSeed] = useState<AssistantSeed>();
  useEffect(() => {
    localStorage.setItem("studioExplorer", String(explorer));
  }, [explorer]);
  useEffect(() => {
    localStorage.setItem("studioAssistantPinned", JSON.stringify(assistantPinned));
  }, [assistantPinned]);
  const openDock = useCallback((tab: DockTab) => setDock(tab), []);
  // ---- tooling state ---------------------------------------------------
  const slice = useTooling(workspaceId);
  const { scan, refresh: rescan } = useProjectScan(workspaceId, report);
  const isDotnet = scan?.kind === "dotnet";
  const structuredTests = isDotnet || scan?.kind === "python";
  useEffect(() => {
    if (workspaceId) void tooling.hydrate(workspaceId).catch(report);
  }, [workspaceId, report]);
  const [references, setReferences] = useState<{ symbol: string; items: Reference[] } | null>(null);
  const [renaming, setRenaming] = useState<{ position: monaco.IPosition; range: monaco.IRange; placeholder: string } | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [proposedEdit, setProposedEdit] = useState<WorkspaceEdit | null>(null);
  const [symbolQuery, setSymbolQuery] = useState("");
  const [symbolResults, setSymbolResults] = useState<{ name: string; containerName: string; path: string; range: { start: { line: number } } }[] | null>(null);
  useEffect(() => {
    if (!proposedEdit && slice.proposedEdits.length) {
      const next = slice.proposedEdits[0];
      setProposedEdit(next);
      tooling.dismissEdit(workspaceId, next);
    }
  }, [slice.proposedEdits, proposedEdit, workspaceId]);
  const languageState = useMemo(() => {
    const sessions = Object.values(slice.languages);
    if (!sessions.length) return "";
    return sessions
      .map((s) => `${s.language === "csharp" ? "C#" : "Python"} · ${s.provider.replace(/\.exe$/i, "")} ${s.state}${s.detail && s.state !== "ready" ? ` · ${s.detail}` : ""}`)
      .join(" · ");
  }, [slice.languages]);
  const languageFailed = Object.values(slice.languages).some((s) => ["failed", "stopped"].includes(s.state));
  const problems = useProblems(workspaceId, root);
  const problemCount = problems.filter((p) => p.severity !== "info").length;
  const runningJobs = Object.values(slice.jobs).filter((job) => job.state === "running");
  const terminalCount = Object.keys(slice.terminals).length;
  const activeWebRun = Object.values(slice.runs).find((run) => run.local_url && ["starting", "running"].includes(run.state));
  // ---- editor plumbing (unchanged safety model) -------------------------
  const markProblems = () => {
    for (const file of retained.values())
      if (file.workspace === workspaceId)
        monaco.editor.setModelMarkers(
          file.model,
          "olive-run",
          diagnostics.current
            .filter((problem) => problem.file === file.path)
            .slice(0, 500)
            .map((problem) => ({
              startLineNumber: Math.max(1, problem.line || 1),
              endLineNumber: Math.max(1, problem.line || 1),
              startColumn: Math.max(1, problem.column || 1),
              endColumn: Math.max(2, (problem.column || 1) + 1),
              message: problem.message,
              severity: problem.severity === "warning" ? monaco.MarkerSeverity.Warning : monaco.MarkerSeverity.Error,
              source: "Run output",
            })),
        );
  };
  const panelRoot = usePanelLayout(Boolean(workspace));
  useEffect(() => {
    if (!workspaceId) return;
    let live = true;
    const refresh = () =>
      void call<{ problems: typeof diagnostics.current }[]>("studio.diagnostics", { workspace_id: workspaceId })
        .then((records) => {
          if (live) {
            diagnostics.current = records.at(-1)?.problems || [];
            markProblems();
          }
        })
        .catch(report);
    refresh();
    const unsubscribe = window.olive.subscribe((event) => {
      const data = event.data as { workspace_id?: string; state?: string };
      if (event.topic === "run" && data.workspace_id === workspaceId && !["running", "starting", "created"].includes(data.state || ""))
        refresh();
    });
    return () => {
      live = false;
      unsubscribe();
    };
  }, [workspaceId]);
  useEffect(() => {
    // Restore this workspace's own view state rather than resetting it.
    const ui = sessionUi(workspaceId);
    setActive(ui.activePath || lastPaths.get(workspaceId) || "");
    setDock(ui.dock as DockTab | "");
    setExplorer(ui.explorerOpen);
    setAssistantOpen(ui.assistantOpen);
    setEntries([]);
    setReferences(null);
    setSymbolResults(null);
  }, [workspaceId]);
  // Remember it as it changes, so a later switch back is exact.
  useEffect(() => {
    updateSessionUi(workspaceId, {
      activePath: active,
      dock,
      explorerOpen: explorer,
      assistantOpen,
    });
  }, [workspaceId, active, dock, explorer, assistantOpen]);
  const flushBuffers = async () => {
    for (const file of retained.values())
      if (file.workspace === workspaceId)
        await call("studio.buffer", {
          workspace_id: workspaceId,
          path: file.path,
          text: file.model.getValue(),
          expected_hash: file.hash,
        });
  };
  const refreshTree = useCallback(async () => {
    if (!workspaceId) return;
    const result = await call<{ entries: typeof entries }>("studio.tree", { workspace_id: workspaceId });
    setEntries(result.entries);
  }, [workspaceId]);
  useEffect(() => {
    if (!workspaceId) return;
    let stale = false;
    void call<{ entries: typeof entries }>("studio.tree", { workspace_id: workspaceId })
      .then((v) => {
        if (!stale) setEntries(v.entries);
      })
      .catch(report);
    return () => {
      stale = true;
    };
  }, [workspaceId]);
  useEffect(() => {
    if (!host.current) return;
    const instance = monaco.editor.create(host.current, {
      theme: theme === "light" ? "vs" : "vs-dark",
      automaticLayout: true,
      fontSize: editorPreferences.current.fontSize,
      fontFamily: editorPreferences.current.fontFamily,
      minimap: { enabled: false },
      padding: { top: 16 },
      scrollBeyondLastLine: false,
      smoothScrolling: false,
      accessibilitySupport: "on",
      ariaLabel: "Source editor",
      glyphMargin: true,
      lightbulb: { enabled: monaco.editor.ShowLightbulbIconMode.OnCode },
      model: null,
    });
    editor.current = instance;
    decorations.current = instance.createDecorationsCollection();
    const glyph = instance.onMouseDown((event) => {
      if (event.target.type === monaco.editor.MouseTargetType.GUTTER_GLYPH_MARGIN && event.target.position) {
        const model = instance.getModel();
        const location = model ? retained.get(current.current) : null;
        if (location && languageFor(location.path)) void debuggerRef.current?.toggleBreakpoint(location.path, event.target.position.lineNumber);
      }
    });
    instance.addAction({
      id: "olive.rename",
      label: "Rename symbol (with preview)",
      keybindings: [monaco.KeyCode.F2],
      contextMenuGroupId: "1_modification",
      contextMenuOrder: 1.1,
      run: async (ed) => {
        const model = ed.getModel();
        const position = ed.getPosition();
        if (!model || !position || !languageFor(retained.get(current.current)?.path || "")) return;
        const prepared = await prepareRename(model, position).catch((error) => {
          report(error);
          return null;
        });
        if (!prepared) return;
        setRenameDraft(prepared.placeholder);
        setRenaming({ position, ...prepared });
      },
    });
    instance.addAction({
      id: "olive.references",
      label: "Find all references (OLIVE)",
      keybindings: [monaco.KeyMod.Shift | monaco.KeyCode.F12],
      contextMenuGroupId: "navigation",
      contextMenuOrder: 1.6,
      run: async (ed) => {
        const model = ed.getModel();
        const position = ed.getPosition();
        if (!model || !position) return;
        const word = model.getWordAtPosition(position)?.word || "symbol";
        try {
          const items = await findReferences(model, position);
          setReferences({ symbol: word, items });
          setDock("references");
        } catch (error) {
          report(error);
        }
      },
    });
    return () => {
      const file = retained.get(current.current);
      if (file) file.view = instance.saveViewState();
      glyph.dispose();
      decorations.current = null;
      instance.dispose();
      editor.current = null;
    };
  }, [Boolean(workspace)]);
  useEffect(() => {
    if (visible) editor.current?.layout();
  }, [visible]);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const tokens = getComputedStyle(document.documentElement);
      const colour = (name: string) => tokens.getPropertyValue(name).trim();
      monaco.editor.defineTheme("olive", {
        base: theme === "light" ? "vs" : "vs-dark",
        inherit: true,
        rules: [],
        colors: {
          "editor.background": colour("--bg"),
          "editor.foreground": colour("--text"),
          "editorLineNumber.foreground": colour("--muted"),
          "editorLineNumber.activeForeground": colour("--accent"),
          "editor.lineHighlightBackground": colour("--surface"),
          "editor.selectionBackground": colour("--elevated"),
          "editorWidget.background": colour("--surface"),
          "editorWidget.border": colour("--line"),
        },
      });
      monaco.editor.setTheme("olive");
    });
    return () => cancelAnimationFrame(frame);
  }, [theme, Boolean(workspace)]);
  useEffect(() => {
    let live = true;
    const apply = (value: { settings: Record<string, unknown> }) => {
      if (!live) return;
      editorPreferences.current = {
        fontSize: Number(value.settings.editor_size) || 13,
        fontFamily: String(value.settings.editor_font || "Consolas"),
        tabSize: Number(value.settings.editor_tab_width) || 4,
      };
      editor.current?.updateOptions(editorPreferences.current);
      for (const file of retained.values()) file.model.updateOptions({ tabSize: editorPreferences.current.tabSize });
    };
    void call<{ settings: Record<string, unknown> }>("data.settings", {}).then(apply).catch(report);
    const unsubscribe = window.olive.subscribe((event) => {
      if (event.topic === "settings") apply(event.data as { settings: Record<string, unknown> });
    });
    return () => {
      live = false;
      unsubscribe();
    };
  }, [theme, Boolean(workspace)]);
  useEffect(() => {
    const instance = editor.current;
    if (!instance) return;
    const previous = retained.get(current.current);
    if (previous) previous.view = instance.saveViewState();
    const file = retained.get(key(active));
    current.current = key(active);
    instance.setModel(file?.model || null);
    file?.model.updateOptions({ tabSize: editorPreferences.current.tabSize });
    if (file?.view) instance.restoreViewState(file.view);
    if (
      document.activeElement === document.body ||
      document.activeElement?.closest(".explorer,.file-tabs,.monaco-editor,.navigation,.studio-head,.problem-list,.test-list,.reference-list")
    )
      instance.focus();
  }, [active, workspaceId, Boolean(workspace)]);
  const open = useCallback(
    async (path: string, line?: number, column?: number) => {
      if (!retained.has(key(path))) {
        if (retained.size >= 32) throw new Error("Close a tab before opening more files.");
        const file = await call<FileState>("studio.open", { workspace_id: workspaceId, path });
        const extension = path.split(".").pop();
        const language = LANGUAGE_IDS[extension || ""] || "plaintext";
        const retainedBuffer = discarded.has(key(path)) ? undefined : buffers.find((b) => b.workspace_id === workspaceId && b.path === path);
        const model = monaco.editor.createModel(retainedBuffer?.text ?? file.text, language, modelUri(workspaceId, path));
        const record: OpenFile = {
          path,
          workspace: workspaceId,
          model,
          hash: retainedBuffer?.expected_hash ?? file.loaded_hash,
          saved: file.saved_text,
        };
        retained.set(key(path), record);
        let timer: ReturnType<typeof setTimeout>;
        model.onDidChangeContent(() => {
          render((n) => n + 1);
          clearTimeout(timer);
          timer = setTimeout(() => {
            discarded.delete(record.workspace + ":" + path);
            void call("studio.buffer", {
              workspace_id: record.workspace,
              path,
              text: model.getValue(),
              expected_hash: record.hash,
            }).catch(report);
          }, 300);
        });
        model.onWillDispose(() => clearTimeout(timer));
        // Code intelligence follows the buffer, not the file on disk.
        record.unsync = syncDocument(workspaceId, path, model, report);
        const known = Object.entries(tooling.slice(workspaceId).diagnostics).find(([abs]) => samePath(abs, absolutePath(root, path)));
        if (known) applyDiagnostics(model, known[1]);
      }
      lastPaths.set(workspaceId, path);
      markProblems();
      setActive(path);
      render((n) => n + 1);
      if (line)
        requestAnimationFrame(() => {
          editor.current?.setPosition({ lineNumber: line, column: column || 1 });
          editor.current?.revealLineInCenter(line);
          editor.current?.focus();
        });
    },
    [workspaceId, buffers, report, root],
  );
  const openRef = useRef(open);
  openRef.current = open;
  // Language-server diagnostics become editor markers for open buffers.
  useEffect(() => {
    for (const file of retained.values()) {
      if (file.workspace !== workspaceId || !languageFor(file.path)) continue;
      const entry = Object.entries(slice.diagnostics).find(([abs]) => samePath(abs, absolutePath(root, file.path)));
      applyDiagnostics(file.model, entry ? entry[1] : []);
    }
  }, [slice.diagnostics, workspaceId, root]);
  useEffect(() => {
    registerLanguageProviders({
      openFile: (ws, path, line, column) => (ws === workspaceId ? openRef.current(path, line, column) : Promise.resolve()),
      proposeEdit: (_ws, edit) => setProposedEdit(edit),
      rootFor: (ws) => (ws === workspaceId ? root : ""),
    });
  }, [workspaceId, root]);
  // ---- debugger --------------------------------------------------------
  const debug = useDebugger(workspaceId, root, (path, line) => openRef.current(path, line), report);
  const debuggerRef = useRef(debug);
  debuggerRef.current = debug;
  useEffect(() => {
    const instance = editor.current;
    const collection = decorations.current;
    if (!instance || !collection) return;
    const file = retained.get(key(active));
    if (!file) {
      collection.clear();
      return;
    }
    decorateModel(instance, collection, debug.breakpointsFor(file.path), debug.current && debug.current.path === file.path ? debug.current : null);
  }, [active, debug.breakpoints, debug.current, workspaceId]);
  useEffect(() => {
    if (debug.active && slice.debugEvents.at(-1)?.event === "stopped") setDock("debug");
  }, [debug.active, slice.debugEvents]);
  // ---- file operations ---------------------------------------------------
  const save = async (target?: OpenFile) => {
    const file = target || retained.get(key(active));
    if (!file || busy) return;
    setBusy(true);
    try {
      const state = await call<FileState>("studio.save", {
        workspace_id: workspaceId,
        path: file.path,
        text: file.model.getValue(),
        expected_hash: file.hash,
      });
      file.hash = state.loaded_hash;
      file.saved = state.saved_text;
      render((n) => n + 1);
      setSaveStatus("Saved · hash checked");
      documentSaved(workspaceId, file.path);
      return true;
    } catch (e) {
      report(e);
      setSaveStatus("Save blocked · editor changes retained");
    } finally {
      setBusy(false);
    }
  };
  const closeFile = async (file: OpenFile) => {
    await call("studio.discard_buffer", { workspace_id: file.workspace, path: file.path });
    file.unsync?.();
    file.model.dispose();
    retained.delete(file.workspace + ":" + file.path);
    discarded.add(file.workspace + ":" + file.path);
    if (active === file.path) {
      const next = [...retained.values()].find((item) => item.workspace === workspaceId)?.path || "";
      setActive(next);
      lastPaths.set(workspaceId, next);
    }
    setClosing(null);
    render((n) => n + 1);
  };
  const saveAll = async () => {
    for (const file of retained.values())
      if (file.workspace === workspaceId && file.saved !== file.model.getValue()) if (!(await save(file))) break;
  };
  const compare = async () => {
    const file = retained.get(key(active));
    if (!file) return;
    const disk = await call<{ disk_text: string; disk_hash: string }>("studio.compare", { workspace_id: workspaceId, path: active });
    setComparison({ ...disk, file });
  };
  const reconcile = async () => {
    if (!comparison) return;
    const file = comparison.file;
    await call("studio.rebase", { workspace_id: file.workspace, path: file.path, expected_hash: file.hash, disk_hash: comparison.disk_hash });
    file.hash = comparison.disk_hash;
    file.saved = comparison.disk_text;
    setComparison(null);
    render((n) => n + 1);
    setSaveStatus("Comparison accepted · save your unsaved editor changes");
  };
  const validate = async (review = false) => {
    setBusy(true);
    setDock("output");
    try {
      await call("studio.validate", { workspace_id: workspaceId, review });
    } catch (e) {
      report(e);
    } finally {
      setBusy(false);
    }
  };
  // ---- tooling actions --------------------------------------------------
  const runJob = async (label: string, work: () => Promise<unknown>, tab: DockTab = "output") => {
    setBusy(true);
    setDock(tab);
    try {
      await work();
      setSaveStatus(label);
    } catch (e) {
      report(e);
    } finally {
      setBusy(false);
    }
  };
  const build = (mode: string, target?: string) =>
    void runJob(`${mode[0].toUpperCase()}${mode.slice(1)} started`, () =>
      call("project.build", { workspace_id: workspaceId, mode, ...(target ? { target } : {}) }),
    );
  const runProgram = () =>
    void runJob(
      "Run started",
      () =>
        isDotnet
          ? call("project.run", { workspace_id: workspaceId })
          : call<{ session_id: string }>("studio.run", { workspace_id: workspaceId }),
      "terminal",
    );
  // The toolbar Test runs the reviewed validation (approval-bound, streamed to
  // Output). The Tests dock offers the structured runner (discover, run
  // all/failed/selected, click-to-source).
  const runTests = () => void validate();
  const startDebug = () =>
    void runJob(
      "Debugger starting",
      async () => {
        await saveAll();
        await debug.launch();
      },
      "debug",
    );
  // Builds that fail land the person in Problems, not in a log they have to scroll.
  const lastJobRef = useRef<string>("");
  useEffect(() => {
    const finished = Object.values(slice.jobs)
      .filter((job) => job.state !== "running" && job.kind === "build")
      .sort((a, b) => (a.ended_at || 0) - (b.ended_at || 0))
      .at(-1);
    if (finished && finished.id !== lastJobRef.current) {
      lastJobRef.current = finished.id;
      if (finished.state === "failed") setDock("problems");
    }
  }, [slice.jobs]);
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if (!visible) return;
      if ((event.ctrlKey || event.metaKey) && event.key === "s") {
        event.preventDefault();
        void (event.shiftKey ? saveAll() : save());
      } else if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "b" && isDotnet) {
        event.preventDefault();
        build("build");
      } else if (event.key === "F5" && !event.ctrlKey) {
        event.preventDefault();
        if (event.shiftKey) void debug.stop();
        else if (debug.active?.suspended) void debug.step("continue");
        else if (!debug.active) startDebug();
      } else if (event.key === "F10" && debug.active?.suspended) {
        event.preventDefault();
        void debug.step("next");
      } else if (event.key === "F11" && debug.active?.suspended) {
        event.preventDefault();
        void debug.step(event.shiftKey ? "stepOut" : "stepIn");
      } else if ((event.ctrlKey || event.metaKey) && event.altKey && event.key.toLowerCase() === "n") {
        event.preventDefault();
        setWizard(true);
      } else if (event.ctrlKey && event.key === "`") {
        event.preventDefault();
        setDock((value) => (value === "terminal" ? "" : "terminal"));
      } else if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "m") {
        event.preventDefault();
        setDock((value) => (value === "problems" ? "" : "problems"));
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  });
  // Closing a workspace names what would be lost first; nothing is discarded
  // until the person chooses, and running work is stopped explicitly.
  const dropWorkspace = useCallback(
    (id: string) => {
      for (const [key, file] of [...retained.entries()]) {
        if (file.workspace !== id) continue;
        file.unsync?.();
        file.model.dispose();
        retained.delete(key);
      }
      lastPaths.delete(id);
      forgetSession(id);
      setClosingWorkspace(null);
      setOpenIds((current) => {
        const next = current.filter((item) => item !== id);
        if (id === workspaceId) setWorkspaceId(next[next.length - 1] || "");
        return next;
      });
    },
    [workspaceId, setWorkspaceId],
  );
  const requestCloseWorkspace = (id: string) => {
    const slice = tooling.slice(id);
    const dirty = [...retained.values()].filter(
      (f) => f.workspace === id && f.saved !== f.model.getValue(),
    ).length;
    const running: string[] = [];
    const terminals = Object.keys(slice.terminals).length;
    if (terminals) running.push(`${terminals} terminal ${terminals === 1 ? "session" : "sessions"} will be closed`);
    if (slice.debug && ["starting", "running", "suspended"].includes(slice.debug.state))
      running.push("A debug session will be stopped");
    const jobs = Object.values(slice.jobs).filter((job) => job.state === "running").length;
    if (jobs) running.push(`${jobs} running ${jobs === 1 ? "job" : "jobs"} will be cancelled`);
    if (!dirty && running.length === 0) {
      dropWorkspace(id);
      return;
    }
    const title = workspaces.find((w) => w.id === id)?.title || "This workspace";
    setSwitching(false);
    setClosingWorkspace({ id, title, dirty, running });
  };
  const finishCloseWorkspace = async (id: string, saveFirst: boolean) => {
    try {
      if (saveFirst) {
        for (const file of [...retained.values()]) {
          if (file.workspace !== id || file.saved === file.model.getValue()) continue;
          const state = await call<FileState>("studio.save", {
            workspace_id: file.workspace,
            path: file.path,
            text: file.model.getValue(),
            expected_hash: file.hash,
          });
          file.hash = state.loaded_hash;
          file.saved = state.saved_text;
        }
      }
      const slice = tooling.slice(id);
      for (const session of Object.values(slice.terminals))
        await call("terminal.close", { session_id: session.session_id }).catch(() => undefined);
      if (slice.debug && ["starting", "running", "suspended"].includes(slice.debug.state))
        await call("dap.stop", { session_id: slice.debug.session_id }).catch(() => undefined);
      for (const job of Object.values(slice.jobs))
        if (job.state === "running")
          await call("project.cancel", { job_id: job.id }).catch(() => undefined);
      dropWorkspace(id);
    } catch (e) {
      report(e);
    }
  };
  const selectionText = () => {
    const editorSelection = editor.current?.getSelection();
    return editorSelection ? editor.current?.getModel()?.getValueInRange(editorSelection).slice(0, 12000) || "" : "";
  };
  const askAssistant = (text: string) => {
    setAssistantOpen(true);
    setAssistantSeed({ text, revision: Date.now() });
  };
  const openModelFor = async (path: string) => {
    await openRef.current(path);
    const file = retained.get(key(path));
    if (!file) throw new Error(`Could not open ${path}`);
    return file.model;
  };
  if (!workspace)
    return (
      <div className="studio-empty">
        <FileCode2 size={32} aria-hidden="true" />
        <h1>Your next idea starts here.</h1>
        <p className="muted">Open a folder to edit real files, build, test and debug your project.</p>
        <button
          className="primary"
          onClick={() =>
            void window.olive
              .openWorkspace()
              .then((w) => {
                if (w) openWorkspace(w.id);
              })
              .catch(report)
          }
        >
          <FolderOpen size={18} />
          Open Workspace
        </button>
        <button onClick={() => setWizard(true)}>
          <FilePlus2 size={18} aria-hidden="true" />
          New project
        </button>
        <div className="studio-recent">
          {workspaces.length > 0 && <span className="eyebrow">Recent workspaces</span>}
          {workspaces.map((w) => (
            <button className="recent-row" key={w.id} aria-label={w.title} title={w.root_path} onClick={() => openWorkspace(w.id)}>
              <span className="recent-icon">
                <FolderOpen size={15} aria-hidden="true" />
              </span>
              <span>
                <strong>{w.title}</strong>
                <small>{w.root_path}</small>
              </span>
            </button>
          ))}
        </div>
        <NewProjectWizard
          open={wizard}
          onOpenChange={setWizard}
          workspaceId={workspaceId}
          onCreated={(created) => openWorkspace(created.id)}
          report={report}
        />
      </div>
    );
  const openFiles = [...retained.values()].filter((f) => f.workspace === workspaceId);
  const dirtyCount = openFiles.filter((f) => f.saved !== f.model.getValue()).length;
  const debugState = debug.status?.state || "";
  const stopTarget = validation ? "tests" : activeCommand ? "command" : activeRun ? "program" : debug.active ? "debugger" : runningJobs.length ? "job" : "";
  return (
    <div className="studio" data-dock={dock || undefined} data-explorer={explorer} data-assistant={assistantOpen}>
      <header className="studio-bar">
        <div className="studio-title">
          <button
            className={`icon-button studio-explorer-toggle ${explorer ? "selected" : ""}`}
            aria-label={explorer ? "Hide Files" : "Show Files"}
            aria-pressed={explorer}
            title={explorer ? "Hide the Files pane" : "Show the Files pane"}
            onClick={() => setExplorer((value) => !value)}
          >
            <PanelLeft size={16} aria-hidden="true" />
          </button>
          <button
            className="workspace-selector"
            aria-label={`Workspace: ${workspace.title}. Switch workspace`}
            aria-haspopup="dialog"
            title={workspace.root_path}
            onClick={() => setSwitching(true)}
          >
            <span className="workspace-name">{workspace.title}</span>
            {openIds.length > 1 && <span className="workspace-count">{openIds.length}</span>}
            <ChevronsUpDown size={14} aria-hidden="true" />
          </button>
          {active && (
            <span className="small muted studio-active-path" title={active}>
              {active}
            </span>
          )}
        </div>
        <div className="studio-actions">
          <button
            className="new-project-action"
            onClick={() => setWizard(true)}
            title="Create another project and open it as its own workspace (Ctrl+Alt+N)"
          >
            <FilePlus2 size={15} aria-hidden="true" />
            New project
          </button>
          <div className="toolbar-group" aria-label="File">
            {isDotnet && <button disabled={busy} onClick={() => setDesignerOpen(true)}>Design form</button>}
            <button className="primary-action" onClick={() => void save()} disabled={busy || !active} title="Save (Ctrl+S)">
              <Save size={15} aria-hidden="true" />
              Save
            </button>
            <button disabled={!active || busy} title="Compare the editor with the file on disk" onClick={() => void compare().catch(report)}>
              <GitCompare size={15} aria-hidden="true" />
              Compare
            </button>
          </div>
          <div className="toolbar-group" aria-label="Run">
            {isDotnet && scan && (
              <>
                <select
                  className="run-select"
                  aria-label="Startup project"
                  title="Startup project"
                  value={scan.run_configuration.startup_project}
                  onChange={(e) =>
                    void call("project.config_save", { workspace_id: workspaceId, config: { ...scan.run_configuration, startup_project: e.target.value, launch_profile: "" } })
                      .then(rescan)
                      .catch(report)
                  }
                >
                  {!scan.run_configuration.startup_project && <option value="">Startup project…</option>}
                  {scan.projects
                    .filter((p) => p.is_executable && !p.is_test)
                    .map((p) => (
                      <option key={p.path} value={p.path}>
                        {p.name}
                      </option>
                    ))}
                </select>
                <select
                  className="run-select"
                  aria-label="Build configuration"
                  title="Build configuration"
                  value={scan.run_configuration.configuration}
                  onChange={(e) =>
                    void call("project.config_save", { workspace_id: workspaceId, config: { ...scan.run_configuration, configuration: e.target.value } })
                      .then(rescan)
                      .catch(report)
                  }
                >
                  <option value="Debug">Debug build</option>
                  <option value="Release">Release build</option>
                </select>
                <button onClick={() => build("build")} disabled={busy} title="Build the solution or startup project (Ctrl+Shift+B)">
                  <Hammer size={15} aria-hidden="true" />
                  Build
                </button>
              </>
            )}
            <button onClick={runTests} disabled={busy} title={structuredTests ? "Run the tests and show structured results" : "Run the detected tests"}>
              <FlaskConical size={15} aria-hidden="true" />
              Test
            </button>
            <button className="primary-action" title="Run the project without the debugger" onClick={runProgram} disabled={busy || Boolean(activeRun)}>
              <Play size={15} aria-hidden="true" />
              Run
            </button>
            {(isDotnet || scan?.kind === "python") && (
              <button
                title="Start the program under the debugger (F5)"
                onClick={startDebug}
                disabled={busy || Boolean(debug.active)}
              >
                <Bug size={15} aria-hidden="true" />
                Start Debugging
              </button>
            )}
            <button
              className={stopTarget ? "danger-action" : ""}
              aria-label={
                validation ? "Stop tests" : activeCommand ? "Stop command" : debug.active && !activeRun ? "Stop debugging" : runningJobs.length && !activeRun ? "Stop job" : "Stop program"
              }
              title={
                validation
                  ? "Cancel the active validation and stop its process"
                  : activeCommand
                    ? "Cancel the reviewed command and stop its process"
                    : activeRun
                      ? "Stop the active program"
                      : debug.active
                        ? "Stop the debug session"
                        : runningJobs.length
                          ? "Cancel the running build or test job"
                          : "No cancellable operation is running"
              }
              disabled={validation?.state === "cancelling" || activeCommand?.commandState === "cancelling" || !stopTarget}
              onClick={() =>
                validation
                  ? void call("studio.cancel_validation", { validation_id: validation.id }).catch(report)
                  : activeCommand
                    ? void call("studio.cancel_command", { command_id: activeCommand.id }).catch(report)
                    : activeRun
                      ? void call("studio.stop", { session_id: activeRun.id }).catch(report)
                      : debug.active
                        ? void debug.stop().catch(report)
                        : runningJobs[0] && void call("project.cancel", { job_id: runningJobs[0].id }).catch(report)
              }
            >
              <Square size={15} aria-hidden="true" />
              {validation?.state === "cancelling" || activeCommand?.commandState === "cancelling" ? "Stopping…" : "Stop"}
            </button>
          </div>
          <ActionMenu>
            {isDotnet && (
              <>
                <button disabled={busy} onClick={() => build("rebuild")}>
                  Rebuild
                </button>
                <button disabled={busy} onClick={() => build("clean")}>
                  Clean
                </button>
                <button disabled={busy} onClick={() => build("restore")}>
                  Restore packages
                </button>
              </>
            )}
            <LocalPreview sessionId={activeRun?.id} report={report} />
            <Packages workspaceId={workspaceId} report={report} setOutput={setOutput} />
            <button disabled={busy} onClick={() => void validate(true)} title="Review the detected commands before approving a test run">
              Review tests
            </button>
            <button
              disabled={busy || !session}
              onClick={() => {
                setBusy(true);
                void call<{ session_id: string }>("studio.restart", { workspace_id: workspaceId, session_id: session })
                  .catch(report)
                  .finally(() => setBusy(false));
              }}
            >
              Restart
            </button>
            <button disabled={busy || dirtyCount === 0} onClick={() => void saveAll()}>
              Save all files{dirtyCount ? ` (${dirtyCount})` : ""}
            </button>
            <WorkspaceTools workspaceId={workspaceId} path={active} openFile={open} report={report} beforeMutation={flushBuffers} />
            <button
              disabled={!Object.keys(slice.languages).length}
              onClick={() => {
                for (const language of Object.keys(slice.languages))
                  void call("lsp.restart", { workspace_id: workspaceId, language }).catch(report);
              }}
            >
              Restart code intelligence
            </button>
          </ActionMenu>
          <button
            className={`assistant-toggle ${assistantOpen ? "selected" : ""}`}
            aria-pressed={assistantOpen}
            title={assistantOpen ? "Hide the assistant (drafts are kept)" : "Ask OLIVE about this workspace"}
            onClick={() => setAssistantOpen((value) => !value)}
          >
            <Sparkles size={15} aria-hidden="true" />
            Ask OLIVE
          </button>
        </div>
      </header>
      <div className="studio-body" ref={panelRoot}>
        <aside className="explorer" hidden={!explorer} aria-label="Files and project">
          <div className="explorer-scroll">
            <ProjectPanel workspaceId={workspaceId} scan={scan} refresh={rescan} openFile={(path) => void open(path).catch(report)} report={report} build={build} busy={busy} />
            <div className="explorer-head">
              <span className="eyebrow">Files</span>
              <div className="explorer-actions">
                <NewFile
                  workspaceId={workspaceId}
                  report={report}
                  created={async (path) => {
                    await refreshTree();
                    await rescan();
                    await open(path);
                  }}
                />
                <button className="icon-button" aria-label="Refresh files" title="Re-read the workspace file tree" onClick={() => void refreshTree().then(rescan).catch(report)}>
                  <RefreshCw size={14} aria-hidden="true" />
                </button>
              </div>
            </div>
            <Explorer entries={entries} active={active} open={(path) => void open(path).catch(report)} />
            {Object.keys(slice.languages).length > 0 && (
              <div className="symbol-search">
                <label className="search">
                  <Search size={14} aria-hidden="true" />
                  <input
                    aria-label="Find symbol in workspace"
                    placeholder="Find symbol…"
                    value={symbolQuery}
                    onChange={(e) => setSymbolQuery(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && symbolQuery.trim()) {
                        const language = Object.keys(slice.languages)[0];
                        void workspaceSymbols(workspaceId, language, symbolQuery.trim())
                          .then((items) => setSymbolResults(items.map((item) => ({ ...item, path: relativePath(root, item.path) }))))
                          .catch(report);
                      }
                    }}
                  />
                </label>
                {symbolResults && (
                  <ul className="symbol-results" aria-label="Symbol results">
                    {symbolResults.slice(0, 40).map((item, index) => (
                      <li key={index}>
                        <button className="tree-like" onClick={() => void open(item.path, item.range.start.line + 1).catch(report)} title={`${item.path}:${item.range.start.line + 1}`}>
                          <span>{item.name}</span>
                          <span className="small muted">{item.containerName || item.path}</span>
                        </button>
                      </li>
                    ))}
                    {symbolResults.length === 0 && <li className="small muted">No symbols match.</li>}
                  </ul>
                )}
              </div>
            )}
          </div>
        </aside>
        <section className="editor-stack">
          <div className="file-tabs">
            {openFiles.map((f) => (
              <div className={f.path === active ? "file-tab active" : "file-tab"} key={f.path}>
                <button
                  onClick={() => {
                    setActive(f.path);
                    lastPaths.set(workspaceId, f.path);
                  }}
                  title={f.path}
                >
                  {f.path.split("/").pop()}
                  {f.saved !== f.model.getValue() && (
                    <span className="dirty" title="Unsaved changes">
                      ●
                    </span>
                  )}
                </button>
                <button
                  aria-label={`Close ${f.path}`}
                  onClick={() => {
                    if (f.saved !== f.model.getValue()) setClosing(f);
                    else void closeFile(f).catch(report);
                  }}
                >
                  <X size={13} />
                </button>
              </div>
            ))}
          </div>
          <div className="editor-area">
            <div className="editor-host" ref={host} />
            {!active && (
              <div className="editor-empty" role="note">
                <FileCode2 size={22} aria-hidden="true" />
                <strong>No file open</strong>
                <p className="muted">Choose a file in Files, create one with New File, or run the project&apos;s tests. Unsaved editor buffers survive navigation.</p>
              </div>
            )}
          </div>
          <div className="studio-dock" hidden={!dock} aria-label="Workspace tools" role="region">
            <div className="dock-head">
              <h3 className="dock-title">
                {DOCK_TABS.find((tab) => tab.id === dock)?.label || "Tools"}
              </h3>
              <button className="icon-button" aria-label="Close panel" title="Close panel" onClick={() => setDock("")}>
                <X size={15} aria-hidden="true" />
              </button>
            </div>
            <div className="dock-body">
              <div hidden={dock !== "terminal"} className="dock-host">
                <TerminalPanel workspaceId={workspaceId} visible={dock === "terminal" && visible} report={report} />
              </div>
              {dock === "problems" && (
                <div className="dock-host">
                  <ProblemsPanel problems={problems} openFile={(path, line, column) => void open(path, line, column).catch(report)} languageState={languageState} />
                </div>
              )}
              {dock === "tests" && (
                <div className="dock-host">
                  <TestsPanel workspaceId={workspaceId} structured={Boolean(structuredTests)} openFile={(path, line) => void open(path, line).catch(report)} report={report} legacyRun={() => void validate()} />
                </div>
              )}
              <div hidden={dock !== "output"} className="dock-host">
                <div className="dock-panel output-panel">
                  <div className="dock-toolbar output-header" aria-label="Studio daily tools">
                    <label>
                      <span className="output-title">Output</span>
                      <select aria-label="Output channel" value={selectedOutput} onChange={(e) => selectOutput(e.target.value)}>
                        {!channels.length && <option value="">No output yet</option>}
                        {channels.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <span className="small" title="Output is read-only and shows authorised runs, builds and tests">
                      Read-only
                    </span>
                  </div>
                  {selectedValidation && <TaskResult value={selectedValidation} />}
                  <Suspense fallback={<p>Loading output…</p>}>
                    <Output text={output} />
                  </Suspense>
                  {channels.find((c) => c.id === selectedOutput && c.runState === "running" && c.acceptsInput) &&
                    <ProgramInput key={selectedOutput} workspaceId={workspaceId} sessionId={selectedOutput} report={report} />}
                </div>
              </div>
              {dock === "git" && (
                <div className="dock-host">
                  <div className="dock-panel git-dock">
                    <GitPanel workspaceId={workspaceId} path={active} report={report} beforeMutation={flushBuffers} />
                  </div>
                </div>
              )}
              {dock === "debug" && (
                <div className="dock-host">
                  <DebugPanel debug={debug} root={root} launch={startDebug} busy={busy} launchable={isDotnet ? "Debug the startup project with netcoredbg" : scan?.kind === "python" ? "Debug main.py with debugpy" : ""} />
                </div>
              )}
              {dock === "web" && (
                <div className="dock-host">
                  <WebPanel workspaceId={workspaceId} report={report} />
                </div>
              )}
              {dock === "references" && (
                <div className="dock-host">
                  <div className="dock-panel references-panel">
                  <div className="dock-toolbar">
                    <span className="small">
                      {references ? `${references.items.length} ${references.items.length === 1 ? "reference" : "references"} to ${references.symbol}` : "Find all references from the editor (Shift+F12)."}
                    </span>
                  </div>
                  {references && (
                    <ul className="reference-list">
                      {references.items.map((item, index) => (
                        <li key={index}>
                          <button className="problem-row" onClick={() => void open(item.relative, item.range.start.line + 1, item.range.start.character + 1).catch(report)}>
                            <span className="problem-message">{item.text || item.relative}</span>
                            <span className="problem-where small muted">
                              {item.relative}:{item.range.start.line + 1}:{item.range.start.character + 1}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>
        <aside className="studio-assistant" hidden={!assistantOpen} aria-label="Assistant">
          {chat && (
            <StudioAssistant
              key={workspaceId}
              workspaceId={workspaceId}
              path={active}
              selection={selectionText}
              chat={chat}
              busy={interactionBusy}
              submit={submit}
              seed={assistantSeed}
              close={() => setAssistantOpen(false)}
              pinned={Boolean(assistantPinned[workspaceId])}
              setPinned={(value) => setAssistantPinned((all) => ({ ...all, [workspaceId]: value }))}
              quick={[
                {
                  label: "Ask about selection",
                  title: "Explain the selected code",
                  disabled: !active,
                  run: () => askAssistant("Explain the selected code and anything surprising about it."),
                },
                {
                  label: "Explain error",
                  title: "Explain the first problem in Problems",
                  disabled: problems.length === 0,
                  run: () => {
                    const first = problems[0];
                    askAssistant(`Explain this error and how to fix it:\n${first.file}:${first.line} ${first.message}`);
                    if (first.file) void open(first.file, first.line || undefined).catch(report);
                  },
                },
                {
                  label: "Review changes",
                  title: "Review the uncommitted Git changes",
                  run: () => {
                    void call<unknown>("studio.diff", { workspace_id: workspaceId })
                      .then((value) => askAssistant(`Review these uncommitted changes for defects and risks:\n\n${JSON.stringify(value, null, 2).slice(0, 12000)}`))
                      .catch(report);
                  },
                },
              ]}
            />
          )}
        </aside>
      </div>
      <footer className="studio-strip" aria-label="Studio status">
        <div className="strip-tools" role="group" aria-label="Tool panels">
          {DOCK_TABS.filter((tab) => tab.id !== "references" && (tab.id !== "web" || activeWebRun || Object.values(slice.runs).some((run) => run.local_url))).map((tab) => {
            const count =
              tab.id === "terminal" ? terminalCount : tab.id === "problems" ? problemCount : tab.id === "tests" ? slice.tests?.summary.failed || 0 : 0;
            const live =
              (tab.id === "debug" && Boolean(debug.active)) ||
              (tab.id === "output" && Boolean(activeRun || validation || runningJobs.length)) ||
              (tab.id === "web" && Boolean(activeWebRun));
            return (
              <button
                key={tab.id}
                className={`strip-button ${dock === tab.id ? "selected" : ""}`}
                aria-pressed={dock === tab.id}
                aria-label={`${dock === tab.id ? "Hide" : "Show"} ${tab.label}`}
                data-live={live || undefined}
                onClick={() => setDock(dock === tab.id ? "" : tab.id)}
                title={`${tab.label}${count ? ` (${count})` : ""}`}
              >
                <tab.icon size={13} aria-hidden="true" />
                <span>{tab.label}</span>
                {count > 0 && <span className="strip-count" data-tone={tab.id === "problems" || tab.id === "tests" ? "attention" : undefined}>{count}</span>}
              </button>
            );
          })}
        </div>
        <div className="strip-status">
          <span className="save-status" role="status">
            {saveStatus}
          </span>
          {debugState && (
            <span className="strip-item" data-state={debugState}>
              <Bug size={12} aria-hidden="true" />
              {debugState === "suspended" ? "Paused" : debugState === "running" ? "Debugging" : debugState === "starting" ? "Debugger starting" : `Debugger ${debugState}`}
            </span>
          )}
          {languageState && (
            <button className={`strip-item text-button ${languageFailed ? "attention" : ""}`} onClick={() => openDock("problems")} title="Code intelligence status · open Problems">
              {languageState}
            </button>
          )}
          {scan && (
            <span className="strip-item muted" title="Run configuration">
              {isDotnet
                ? `${scan.projects.find((p) => p.path.toLowerCase() === scan.run_configuration.startup_project.toLowerCase())?.name || "No startup project"} · ${scan.run_configuration.configuration}`
                : scan.kind === "python"
                  ? `Python ${scan.tooling.python.version}`
                  : ""}
            </span>
          )}
        </div>
      </footer>
      <Sheet
        open={switching}
        onOpenChange={setSwitching}
        title="Workspaces"
        description="Each open workspace keeps its own files, terminals, tests and debug session. Switching never discards another one."
      >
        <div className="studio-recent">
          <span className="eyebrow">Open in Studio</span>
          {openIds
            .map((id) => workspaces.find((w) => w.id === id))
            .filter((w): w is Workspace => Boolean(w))
            .map((w) => (
              <div className="workspace-row" key={w.id}>
                <button
                  className={`recent-row ${w.id === workspaceId ? "selected" : ""}`}
                  aria-label={w.title}
                  aria-current={w.id === workspaceId ? "true" : undefined}
                  title={w.root_path}
                  onClick={() => {
                    setSwitching(false);
                    openWorkspace(w.id);
                  }}
                >
                  <span className="recent-icon">
                    <FolderOpen size={15} aria-hidden="true" />
                  </span>
                  <span>
                    <strong>{w.title}</strong>
                    <small>{w.root_path}</small>
                  </span>
                </button>
                {openIds.length > 1 && (
                  <button
                    className="icon-button"
                    aria-label={`Close ${w.title}`}
                    title="Close this workspace in Studio"
                    onClick={() => requestCloseWorkspace(w.id)}
                  >
                    <X size={15} aria-hidden="true" />
                  </button>
                )}
              </div>
            ))}
          {workspaces.filter((w) => !openIds.includes(w.id)).length > 0 && (
            <>
              <span className="eyebrow">Other approved folders</span>
              {workspaces
                .filter((w) => !openIds.includes(w.id))
                .map((w) => (
                  <button
                    className="recent-row"
                    key={w.id}
                    aria-label={w.title}
                    title={w.root_path}
                    onClick={() => {
                      setSwitching(false);
                      openWorkspace(w.id);
                    }}
                  >
                    <span className="recent-icon">
                      <FolderOpen size={15} aria-hidden="true" />
                    </span>
                    <span>
                      <strong>{w.title}</strong>
                      <small>{w.root_path}</small>
                    </span>
                  </button>
                ))}
            </>
          )}
        </div>
        <div className="row wrap" style={{ marginTop: 14 }}>
          <button
            className="primary"
            onClick={() => {
              setSwitching(false);
              setWizard(true);
            }}
          >
            <FilePlus2 size={16} aria-hidden="true" />
            New project
          </button>
          <button
            onClick={() =>
              void window.olive
                .openWorkspace()
                .then((w) => {
                  if (w) {
                    setSwitching(false);
                    openWorkspace(w.id);
                  }
                })
                .catch(report)
            }
          >
            <FolderOpen size={16} aria-hidden="true" />
            Open an existing folder
          </button>
        </div>
      </Sheet>
      <Sheet
        open={Boolean(closing)}
        onOpenChange={(value) => {
          if (!value) setClosing(null);
        }}
        title="Unsaved changes"
        description={closing ? `Keep, save, or discard your editor changes to ${closing.path}. Discard leaves the file on disk untouched.` : ""}
      >
        <div className="row">
          <button onClick={() => setClosing(null)}>Keep editing</button>
          <button
            disabled={busy}
            onClick={() => {
              if (closing) void closeFile(closing).catch(report);
            }}
          >
            Discard buffer
          </button>
          <button
            className="primary"
            disabled={busy}
            onClick={() => {
              if (closing)
                void save(closing)
                  .then((saved) => {
                    if (saved) return closeFile(closing);
                  })
                  .catch(report);
            }}
          >
            Save and close
          </button>
        </div>
      </Sheet>
      <Sheet
        open={Boolean(renaming)}
        onOpenChange={(value) => {
          if (!value) setRenaming(null);
        }}
        title="Rename symbol"
        description="The language server computes every affected location. You review the edits before they reach any buffer."
      >
        {renaming && (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const model = editor.current?.getModel();
              if (!model || !renameDraft.trim() || renameDraft === renaming.placeholder) return;
              const position = renaming.position;
              setRenaming(null);
              void renameSymbol(model, position, renameDraft.trim())
                .then((edit) => {
                  if (!edit.total) {
                    setSaveStatus("The language server returned no edits for that rename");
                    return;
                  }
                  setProposedEdit({ ...edit, label: `Rename ${renaming.placeholder} to ${renameDraft.trim()}` });
                })
                .catch(report);
            }}
          >
            <label className="field">
              New name for <code>{renaming.placeholder}</code>
              <input aria-label="New symbol name" value={renameDraft} onChange={(e) => setRenameDraft(e.target.value)} autoFocus />
            </label>
            <div className="row">
              <button type="button" onClick={() => setRenaming(null)}>
                Cancel
              </button>
              <button type="submit" className="primary" disabled={!renameDraft.trim() || renameDraft === renaming.placeholder}>
                Preview edits
              </button>
            </div>
          </form>
        )}
      </Sheet>
      <NewProjectWizard
        open={wizard}
        onOpenChange={setWizard}
        workspaceId={workspaceId}
        onCreated={(created) => openWorkspace(created.id)}
        report={report}
      />
      <WinFormsDesigner key={workspaceId} workspaceId={workspaceId} open={designerOpen} onOpenChange={setDesignerOpen}
        openCode={async path => {await refreshTree(); await open(path);}}
        run={() => runJob("Native app started", async () => {await saveAll(); await call("project.run", {workspace_id: workspaceId});}, "output")} />
      <Sheet
        open={Boolean(closingWorkspace)}
        onOpenChange={(value) => {
          if (!value) setClosingWorkspace(null);
        }}
        title="Close workspace"
        description={
          closingWorkspace
            ? `${closingWorkspace.title} has work that would be lost. Nothing is discarded until you choose.`
            : ""
        }
      >
        {closingWorkspace && (
          <>
            <ul className="close-summary">
              {closingWorkspace.dirty > 0 && (
                <li>
                  {closingWorkspace.dirty} unsaved {closingWorkspace.dirty === 1 ? "file" : "files"}
                </li>
              )}
              {closingWorkspace.running.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <div className="row">
              <button onClick={() => setClosingWorkspace(null)}>Cancel</button>
              <button onClick={() => void finishCloseWorkspace(closingWorkspace.id, false)}>
                Close and discard
              </button>
              <button className="primary" onClick={() => void finishCloseWorkspace(closingWorkspace.id, true)}>
                Save and close
              </button>
            </div>
          </>
        )}
      </Sheet>
      <EditPreview edit={proposedEdit} root={root} workspaceId={workspaceId} openModel={openModelFor} close={() => setProposedEdit(null)} report={report} />
      {comparison && <Compare disk={comparison.disk_text} model={comparison.file.model} close={() => setComparison(null)} reconcile={() => void reconcile().catch(report)} />}
    </div>
  );
}

export default function Studio(props: ComponentProps<typeof LocalStudio>) {
  const [remote, setRemote] = useState(false);
  const [remoteVisited, setRemoteVisited] = useState(false);
  return <div style={{height: "100%", display: "flex", flexDirection: "column"}}>
    <div className="studio-bar" role="group" aria-label="Studio workspace location">
      <button aria-pressed={!remote} onClick={() => setRemote(false)}>Local</button>
      <button aria-pressed={remote} onClick={() => { setRemoteVisited(true); setRemote(true); }}>Remote</button>
    </div>
    <div style={{display: remote ? "none" : "contents"}}><LocalStudio {...props} visible={props.visible !== false && !remote} /></div>
    <div style={{display: remote ? "block" : "none", flex: 1, minHeight: 0}}>{remoteVisited && <RemoteStudio theme={props.theme} visible={props.visible !== false && remote} />}</div>
  </div>;
}
