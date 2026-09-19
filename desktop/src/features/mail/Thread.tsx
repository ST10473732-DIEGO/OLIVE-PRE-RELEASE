import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import type { MailRecord } from "./types";
export default function Thread({
  id,
  open,
}: {
  id: string;
  open: (id: string) => void;
}) {
  const r = useResource(
    () =>
      call<{ items: MailRecord[]; total: number }>("mail.thread", {
        record_id: id,
      }),
    ["mail.changed"],
    id,
  );
  if (r.error) return <p role="alert">{r.error}</p>;
  if (!r.data || r.data.total < 2) return null;
  return (
    <details className="mail-thread">
      <summary>Thread · {r.data.total} related messages</summary>
      {r.data.total > r.data.items.length && (
        <p className="muted">
          Showing the latest {r.data.items.length} of {r.data.total} cached
          records.
        </p>
      )}
      <ul className="mail-thread-list">
        {r.data.items.map((m) => (
          <li key={m.id}>
            <button
              className={m.id === id ? "selected" : ""}
              aria-current={m.id === id ? "true" : undefined}
              onClick={() => open(m.id)}
            >
              <strong>{m.subject || "(No subject)"}</strong>
              <span className="muted">{m.from || "Local draft"}</span>
            </button>
          </li>
        ))}
      </ul>
    </details>
  );
}
