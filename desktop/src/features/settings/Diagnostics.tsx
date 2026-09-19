import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import { Details } from "../../components/WorkspacePage";
export function Diagnostics({
  chatId,
  report,
}: {
  chatId: string;
  report: (e: unknown) => void;
}) {
  const { data, loading, error, refresh } = useResource(() =>
    call<Record<string, unknown>>("data.diagnostics", { chat_id: chatId }),
  );
  return (
    <section>
      <div className="row">
        <h2>Diagnostics</h2>
        <button disabled={loading} onClick={() => void refresh()}>
          Refresh diagnostics
        </button>
        <button
          disabled={!data}
          onClick={() =>
            void navigator.clipboard
              .writeText(JSON.stringify(data, null, 2))
              .catch(report)
          }
        >
          Copy diagnostics
        </button>
        <button
          disabled={!data}
          onClick={() =>
            void window.olive
              .fileAction({ action: "diagnostics", chat_id: chatId })
              .catch(report)
          }
        >
          Export diagnostics
        </button>
      </div>
      <p className="muted">
        Local service and execution availability. Developer presentation does
        not change permission rules.
      </p>
      {loading && <p role="status">Checking local services…</p>}
      {error && <p role="alert">{error}</p>}
      {data && (
        <dl className="diagnostics-list">
          {Object.entries(data).map(([key, value]) => (
            <div key={key}>
              <dt>{key.replaceAll("_", " ")}</dt>
              <dd>
                {value !== null && typeof value === "object" ? (
                  <Details value={value} title="Inspect" />
                ) : (
                  String(value)
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
