import { useState } from "react";
import { call } from "../../services/api";

export function ProgramInput({ workspaceId, sessionId, report }: {
  workspaceId: string; sessionId: string; report: (error: unknown) => void;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [closed, setClosed] = useState(false);
  const send = async (eof: boolean) => {
    if (busy || closed) return;
    setBusy(true);
    try {
      await call("studio.input", { workspace_id: workspaceId, session_id: sessionId, text: text + (eof ? "" : "\n"), eof });
      setText("");
      if (eof) setClosed(true);
    } catch (error) { report(error); } finally { setBusy(false); }
  };
  return <form className="toolbar" onSubmit={(event) => { event.preventDefault(); void send(false); }}>
    <input aria-label="Program input" value={text} maxLength={3999} disabled={busy || closed}
      placeholder="Input for this program" onChange={(event) => setText(event.target.value)} />
    <button disabled={busy || closed} type="submit">Send input</button>
    <button disabled={busy || closed} type="button" onClick={() => void send(true)}>End input</button>
  </form>;
}
