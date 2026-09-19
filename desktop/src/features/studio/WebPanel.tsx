import { useState } from "react";
import { Globe, Send } from "lucide-react";
import { call } from "../../services/api";
import { LocalPreview } from "./LocalPreview";
import { useTooling } from "./tooling";

interface RequestRecord {
  id: string;
  time: number;
  session_id: string;
  ok: boolean;
  method: string;
  url: string;
  status: number;
  reason?: string;
  duration_ms: number;
  headers?: Record<string, string>;
  body?: string;
  truncated?: boolean;
  error?: string;
  detail?: string;
}
const contentType = (record: RequestRecord) =>
  Object.entries(record.headers || {}).find(([name]) => name.toLowerCase() === "content-type")?.[1] || "";
// A small inspector for the endpoint the running program itself announced.
// Requests only ever go to that owned localhost origin; the runtime refuses
// anything else and never relaxes certificate checks.
export function WebPanel({
  workspaceId,
  report,
}: {
  workspaceId: string;
  report: (error: unknown) => void;
}) {
  const slice = useTooling(workspaceId);
  const runs = Object.values(slice.runs).filter((run) => run.local_url);
  const active = runs.find((run) => ["starting", "running"].includes(run.state));
  const [method, setMethod] = useState("GET");
  const [path, setPath] = useState("/");
  const [headers, setHeaders] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<RequestRecord[]>([]);
  const [selected, setSelected] = useState<RequestRecord | null>(null);
  const send = async () => {
    if (!active) return;
    setBusy(true);
    try {
      const parsedHeaders = Object.fromEntries(
        headers
          .split("\n")
          .map((line) => line.split(":"))
          .filter((parts) => parts.length >= 2 && parts[0].trim())
          .map(([name, ...rest]) => [name.trim(), rest.join(":").trim()]),
      );
      const record = await call<RequestRecord>("web.request", {
        workspace_id: workspaceId,
        session_id: active.id,
        method,
        path: path.startsWith("/") ? path : "/" + path,
        headers: parsedHeaders,
        body: ["GET", "HEAD"].includes(method) ? "" : body,
      });
      setHistory((items) => [record, ...items].slice(0, 50));
      setSelected(record);
    } catch (error) {
      report(error);
    } finally {
      setBusy(false);
    }
  };
  const pretty = (record: RequestRecord) => {
    const body = record.body || "";
    if (contentType(record).includes("json")) {
      try {
        return JSON.stringify(JSON.parse(body), null, 2);
      } catch {
        return body;
      }
    }
    return body;
  };
  return (
    <div className="dock-panel web-panel">
      <div className="dock-toolbar">
        <span className="small">
          <Globe size={14} aria-hidden="true" />{" "}
          {active ? (
            <>
              Listening at <code>{active.local_url}</code>
            </>
          ) : runs.length ? (
            "The last web run has stopped."
          ) : (
            "No running program has announced a local URL yet."
          )}
        </span>
        <LocalPreview sessionId={active?.id} report={report} />
      </div>
      <div className="web-body">
        <form
          className="web-request"
          onSubmit={(event) => {
            event.preventDefault();
            void send();
          }}
        >
          <div className="row">
            <select aria-label="Request method" value={method} onChange={(e) => setMethod(e.target.value)}>
              {["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"].map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
            <input
              aria-label="Request path"
              placeholder="/weatherforecast"
              value={path}
              onChange={(e) => setPath(e.target.value)}
            />
            <button type="submit" className="primary-action" disabled={!active || busy}>
              <Send size={14} aria-hidden="true" />
              Send
            </button>
          </div>
          <details>
            <summary className="small">Headers and body</summary>
            <label className="field small">
              Headers (one per line, <code>Name: value</code>)
              <textarea aria-label="Request headers" rows={2} value={headers} onChange={(e) => setHeaders(e.target.value)} />
            </label>
            <label className="field small">
              Body
              <textarea aria-label="Request body" rows={3} value={body} onChange={(e) => setBody(e.target.value)} disabled={["GET", "HEAD"].includes(method)} />
            </label>
          </details>
          {history.length > 0 && (
            <ul className="web-history" aria-label="Request history">
              {history.map((record) => (
                <li key={record.id}>
                  <button className={selected?.id === record.id ? "selected" : ""} onClick={() => setSelected(record)}>
                    <span className="web-status" data-ok={record.ok && record.status < 400}>
                      {record.status || "—"}
                    </span>
                    <span>
                      {record.method} {record.url.replace(/^https?:\/\/[^/]+/, "")}
                    </span>
                    <span className="small muted">{record.duration_ms} ms</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </form>
        <div className="web-response" aria-live="polite">
          {selected ? (
            <>
              <div className="row spread">
                <strong>
                  {selected.status || "No response"} {selected.reason || ""}
                </strong>
                <span className="small muted">
                  {selected.duration_ms} ms · {contentType(selected) || "no content type"}
                </span>
              </div>
              {selected.error && (
                <p role="alert">
                  {selected.error}
                  {selected.detail ? ` (${selected.detail})` : ""}
                </p>
              )}
              <details>
                <summary className="small">Response headers ({Object.keys(selected.headers || {}).length})</summary>
                <pre className="small">
                  {Object.entries(selected.headers || {})
                    .map(([name, value]) => `${name}: ${value}`)
                    .join("\n")}
                </pre>
              </details>
              <pre className="web-body-text">
                {pretty(selected)}
                {selected.truncated ? "\n… (truncated)" : ""}
              </pre>
            </>
          ) : (
            <p className="small muted">Responses are shown here with status, headers, timing and body.</p>
          )}
        </div>
      </div>
    </div>
  );
}
