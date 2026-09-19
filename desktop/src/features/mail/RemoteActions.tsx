import { useState } from "react";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import { Feedback, useOperation } from "../personal/shared";
import type { MailRecord } from "./types";

export function RemoteMessageActions({
  record,
  loaded,
}: {
  record: MailRecord;
  loaded: (r: MailRecord) => void;
}) {
  const [destination, setDestination] = useState("");
  const op = useOperation();
  const folders = useResource(() => call<{items: {id: string; name: string; role?: string; connection_id: string}[]}>("mail.folders", {connection_id: record.connection_id}), ["mail.changed"], record.connection_id);
  if (!record.remote) return null;
  const run = (action: string, args: Record<string, unknown>) =>
    void op.run(
      async () =>
        loaded(
          await call<MailRecord>("mail.remote_action", {
            record_id: record.id,
            revision: record.revision,
            action,
            arguments: args,
          }),
        ),
      "Server operation confirmed.",
    );
  return (
    <details className="mail-actions">
      <summary>Server actions</summary>
      <p>
        These change the connected mailbox. Local actions remain separate.
        Permanent deletion is unavailable.
      </p>
      <p>
        Remote state: {record.remote_state?.replaceAll("_", " ") || "cached"}
        {record.remote_operation &&
          ` · Last ${record.remote_operation.action} operation: ${record.remote_operation.state.replaceAll("_", " ")}. Refresh before repeating an uncertain change.`}
      </p>
      <div className="row wrap">
        <button
          disabled={op.busy}
          onClick={() => run("flags", { read: !record.read })}
        >
          Mark {record.read ? "unread" : "read"} on server
        </button>
        <button
          disabled={op.busy}
          onClick={() => run("flags", { starred: !record.starred })}
        >
          {record.starred ? "Unstar" : "Star"} on server
        </button>
      </div>
      <label>
        Destination mailbox
        <select
          aria-label="Server move destination"
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
        ><option value="">Choose an advertised folder</option>
          {folders.data?.items.filter(f => f.connection_id === record.connection_id && f.name !== record.remote?.mailbox).map(f => <option key={f.id} value={f.name}>{f.role && f.role !== f.name ? `${f.role} · ` : ""}{f.name}</option>)}
        </select>
      </label>
      <button
        disabled={op.busy || !destination}
        onClick={() => run("move", { destination })}
      >
        Review server move
      </button>
      <Feedback error={op.error || folders.error} notice={op.notice} />
    </details>
  );
}

export function ServerTools({
  connection,
  folder,
  query,
  open,
}: {
  connection: string;
  folder: string;
  query: string;
  open: (id: string) => void;
}) {
  const op = useOperation();
  const [results, setResults] = useState<{
    items: { id: string; subject: string }[];
    total: number;
    scope: string;
  }>();
  const [action, setAction] = useState("create"),
    [name, setName] = useState(""),
    [newName, setNewName] = useState("");
  return (
    <details className="mail-actions">
      <summary>Server search and folders</summary>
      <p>Explicit access to this connection only.</p>
      <button
        disabled={!query || op.busy}
        onClick={() =>
          void op.run(
            async () =>
              setResults(
                await call("mail.server_search", {
                  connection_id: connection,
                  folder,
                  query,
                }),
              ),
            "Server search completed.",
          )
        }
      >
        Search server for current query
      </button>
      {results && (
        <>
          <p>
            {results.scope} · {results.total} matches
          </p>
          {results.items.map((r) => (
            <button key={r.id} onClick={() => open(r.id)}>
              {r.subject || "(No subject)"}
            </button>
          ))}
        </>
      )}
      <label>
        Folder operation
        <select
          aria-label="Server folder operation"
          value={action}
          onChange={(e) => setAction(e.target.value)}
        >
          <option value="create">Create</option>
          <option value="rename">Rename</option>
        </select>
      </label>
      <input
        aria-label="Server folder name"
        placeholder="Exact server mailbox"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      {action === "rename" && (
        <input
          aria-label="New server folder name"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
      )}
      <button
        disabled={op.busy || !name || (action === "rename" && !newName)}
        onClick={() =>
          void op.run(
            () =>
              call("mail.folder_action", {
                connection_id: connection,
                action,
                name,
                new_name: newName,
              }),
            "Mailbox change confirmed. Refresh to update folders.",
          )
        }
      >
        Review folder operation
      </button>
      <Feedback error={op.error} notice={op.notice} />
    </details>
  );
}
