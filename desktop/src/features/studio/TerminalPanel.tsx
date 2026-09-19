import { useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { Plus, X, ShieldAlert } from "lucide-react";
import { call } from "../../services/api";
import { tooling, useTooling, type TerminalStatus } from "./tooling";

function terminalTheme() {
  const tokens = getComputedStyle(document.documentElement);
  const colour = (name: string) => tokens.getPropertyValue(name).trim();
  return {
    background: colour("--bg") || "#0c121c",
    foreground: colour("--text") || "#bdc9db",
    cursor: colour("--accent") || "#7cc4ff",
    selectionBackground: colour("--accent-glow") || "#7cc4ff44",
  };
}
// One xterm per native session. Keystrokes go to the ConPTY through
// `terminal.write`; output arrives as coalesced `terminal.data` events. The
// process is a real shell with the user's own permissions.
function TerminalView({
  session,
  visible,
  report,
}: {
  session: TerminalStatus;
  visible: boolean;
  report: (error: unknown) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const termRef = useRef<Terminal | null>(null);
  const running = useRef(session.state === "running");
  running.current = session.state === "running";
  useEffect(() => {
    const term = new Terminal({
      convertEol: false,
      scrollback: 5000,
      fontSize: 13,
      fontFamily: '"Cascadia Mono", Consolas, monospace',
      theme: terminalTheme(),
      allowProposedApi: false,
      cursorBlink: true,
      windowsPty: { backend: "conpty" },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(host.current!);
    fit.fit();
    termRef.current = term;
    fitRef.current = fit;
    const replay = tooling.terminalReplay(session.session_id);
    if (replay) term.write(replay);
    const unsubscribe = tooling.onTerminalData(session.session_id, (chunk) => term.write(chunk));
    const data = term.onData((value) => {
      if (!running.current) return;
      void call("terminal.write", { session_id: session.session_id, data: value }).catch(report);
    });
    const resize = term.onResize(({ cols, rows }) => {
      void call("terminal.resize", { session_id: session.session_id, columns: cols, rows }).catch(() => undefined);
    });
    term.attachCustomKeyEventHandler((event) => {
      if (event.type !== "keydown") return true;
      if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "c") {
        const selection = term.getSelection();
        if (selection) void navigator.clipboard.writeText(selection).catch(() => undefined);
        return false;
      }
      if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "v") {
        void navigator.clipboard
          .readText()
          .then((text) => running.current && call("terminal.write", { session_id: session.session_id, data: text }))
          .catch(() => undefined);
        return false;
      }
      return true;
    });
    const paste = (event: MouseEvent) => {
      if (event.button === 2) {
        event.preventDefault();
        void navigator.clipboard
          .readText()
          .then((text) => running.current && text && call("terminal.write", { session_id: session.session_id, data: text }))
          .catch(() => undefined);
      }
    };
    const element = host.current!;
    const contextMenu = (event: MouseEvent) => event.preventDefault();
    element.addEventListener("contextmenu", contextMenu);
    element.addEventListener("mouseup", paste);
    const observer = new ResizeObserver(() => {
      if (host.current && host.current.clientWidth > 0) fit.fit();
    });
    observer.observe(host.current!);
    const themes = new MutationObserver(() => {
      term.options.theme = terminalTheme();
    });
    themes.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      unsubscribe();
      data.dispose();
      resize.dispose();
      observer.disconnect();
      themes.disconnect();
      element.removeEventListener("contextmenu", contextMenu);
      element.removeEventListener("mouseup", paste);
      term.dispose();
      termRef.current = null;
    };
  }, [session.session_id]);
  useEffect(() => {
    if (termRef.current) termRef.current.options.disableStdin = session.state !== "running";
  }, [session.state]);
  useEffect(() => {
    if (visible) {
      requestAnimationFrame(() => {
        fitRef.current?.fit();
        termRef.current?.focus();
      });
    }
  }, [visible]);
  return (
    <div
      className="terminal-view"
      data-session-id={session.session_id}
      ref={host}
      hidden={!visible}
      aria-label={`${session.title} (${session.shell})`}
    />
  );
}
export function TerminalPanel({
  workspaceId,
  visible,
  report,
}: {
  workspaceId: string;
  visible: boolean;
  report: (error: unknown) => void;
}) {
  const slice = useTooling(workspaceId);
  const sessions = Object.values(slice.terminals).sort((a, b) => a.created_at - b.created_at);
  const [selected, setSelected] = useState("");
  const [choosing, setChoosing] = useState(false);
  const [opening, setOpening] = useState(false);
  const latestProgram = sessions.filter((s) => s.shell === "program").at(-1)?.session_id;
  useEffect(() => {
    if (latestProgram) setSelected(latestProgram);
  }, [latestProgram]);
  const current = sessions.find((s) => s.session_id === selected) || sessions.at(-1);
  const open = async (shell: string) => {
    setOpening(true);
    setChoosing(false);
    try {
      const status = await call<TerminalStatus>("terminal.open", { workspace_id: workspaceId, shell });
      setSelected(status.session_id);
    } catch (error) {
      report(error);
    } finally {
      setOpening(false);
    }
  };
  const close = async (id: string) => {
    try {
      await call("terminal.close", { session_id: id });
    } catch (error) {
      report(error);
    }
  };
  return (
    <div className="dock-panel terminal-panel">
      <div className="dock-toolbar">
        <div className="dock-tabs" role="tablist" aria-label="Terminal sessions">
          {sessions.map((session) => (
            <div
              className={`dock-tab ${current?.session_id === session.session_id ? "selected" : ""}`}
              key={session.session_id}
            >
              <button
                role="tab"
                aria-selected={current?.session_id === session.session_id}
                onClick={() => setSelected(session.session_id)}
                title={`${session.shell} · pid ${session.pid ?? "?"} · ${session.cwd}`}
              >
                {session.title}
                {session.state !== "running" && (
                  <span className="muted"> · exited {session.exit_code ?? ""}</span>
                )}
              </button>
              <button
                className="icon-button"
                aria-label={`Close ${session.title}`}
                onClick={() => void close(session.session_id)}
              >
                <X size={13} aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
        <div className="row">
          <button
            className="quiet"
            aria-label="New terminal"
            aria-expanded={choosing}
            disabled={opening}
            onClick={() => setChoosing((value) => !value)}
          >
            <Plus size={14} aria-hidden="true" />
            New terminal
          </button>
        </div>
      </div>
      {choosing && (
        <div className="terminal-choice" role="group" aria-label="Choose a shell">
          <p className="small">
            <ShieldAlert size={14} aria-hidden="true" />
            A native shell runs with your Windows user account and everything it
            can do. Its start folder is this workspace, but it is not limited to it.
            OLIVE never types into this terminal on its own.
          </p>
          <div className="row wrap">
            <button className="primary" onClick={() => void open("powershell")}>
              Open PowerShell
            </button>
            <button onClick={() => void open("cmd")}>Open Command Prompt</button>
            <button className="quiet" onClick={() => setChoosing(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}
      <div className="terminal-stage">
        {sessions.map((session) => (
          <TerminalView
            key={session.session_id}
            session={session}
            visible={visible && current?.session_id === session.session_id}
            report={report}
          />
        ))}
        {sessions.length === 0 && !choosing && (
          <div className="dock-empty">
            <p className="muted">
              No terminal is open. Open one to run commands yourself; program
              and test output stay in Output and Tests.
            </p>
          </div>
        )}
      </div>
      {current && (
        <div className="terminal-foot small muted">
          Native {current.shell} · pid {current.pid ?? "?"} · {current.cwd} · your
          user permissions · Ctrl+Shift+C copy · Ctrl+Shift+V or right-click paste
        </div>
      )}
    </div>
  );
}
