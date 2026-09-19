import { useEffect, useState } from "react";
import { call } from "../../services/api";
import { GrowingComposer } from "../../components/GrowingComposer";
export function ReviewedCommand({
  workspaceId,
  report,
}: {
  workspaceId: string;
  report: (e: unknown) => void;
}) {
  const [command, setCommand] = useState("");
  const [shell, setShell] = useState<"powershell" | "cmd" | "python">(
    "powershell",
  );
  const [windowsShells, setWindowsShells] = useState(true);
  useEffect(() => {
    let active = true;
    void call<{ terminal: { shells: string[] } }>("tooling.inventory", {}).then(value => {
      if (active && !value.terminal.shells.includes("powershell")) { setWindowsShells(false); setShell("python"); }
    }).catch(report);
    return () => { active = false; };
  }, [report]);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <h3>Reviewed local command</h3>
      <p>
        This runs one explicit command through the existing execution policy.
        Output is read-only; no interactive shell session is open. Each output stream retains its latest 12,000 characters. An approved
        working directory does not isolate a command from other files or
        networking.
      </p>
      <label className="field">
        Environment
        <select
          value={shell}
          onChange={(e) => setShell(e.target.value as typeof shell)}
        >
          {windowsShells && <><option value="powershell">PowerShell</option><option value="cmd">CMD</option></>}
          <option value="python">Python</option>
        </select>
      </label>
      <label className="field">
        Command
        <GrowingComposer
          aria-label="Reviewed command"
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          maxLength={32000}
        />
      </label>
      <button
        disabled={busy || !command.trim()}
        onClick={() => {
          setBusy(true);
          void call("studio.command", {
            workspace_id: workspaceId,
            command,
            shell,
          })
            .catch(report)
            .finally(() => setBusy(false));
        }}
      >
        Review command
      </button>
      {busy && (
        <p role="status">
          Command request active. Review its approval, or use Stop command in
          Studio. Output remains available after navigation.
        </p>
      )}
    </>
  );
}
