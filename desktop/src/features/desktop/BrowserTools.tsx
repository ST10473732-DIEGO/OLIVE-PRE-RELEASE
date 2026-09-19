import { useState } from "react";
import { call } from "../../services/api";
import { Details } from "../../components/WorkspacePage";
import type { Operation } from "./types";
interface Control {
  id: string;
  name: string;
  role: string;
  type: string;
  password?: boolean;
}
interface Observation {
  title: string;
  url: string;
  controls: Control[];
  message?: string;
  verified?: boolean;
}
export default function BrowserTools({
  operation,
  busy,
}: {
  operation: Operation;
  busy: boolean;
}) {
  const [tabs, setTabs] = useState<
    { id: string; title: string; url: string }[]
  >([]);
  const [tab, setTab] = useState("");
  const [url, setUrl] = useState("");
  const [observation, setObservation] = useState<Observation>();
  const [target, setTarget] = useState("");
  const [action, setAction] = useState<"click" | "fill" | "select" | "scroll">(
    "click",
  );
  const [value, setValue] = useState("");
  const [expected, setExpected] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [download, setDownload] = useState<{
    id: string;
    filename: string;
    size: number;
  }>();
  const [dialog, setDialog] = useState<{ pending: boolean; message: string }>();
  const [result, setResult] = useState<unknown>();
  const controls = (observation?.controls || []).filter(
    (c) => !c.password && c.type !== "password",
  );
  const observe = (value: Observation) => {
    setObservation(value);
    setTarget("");
    setFields({});
  };
  const options = controls.map((c) => (
    <option key={c.id} value={c.id}>
      {c.name || c.type || c.role || "Unnamed control"}
    </option>
  ));
  return (
    <section>
      <h2>Interactive browser</h2>
      <p>
        This uses the existing separately controlled browser. Its pages receive
        no OLIVE application bridge.
      </p>
      <button
        disabled={busy}
        onClick={() =>
          void operation(
            async () => setTabs(await call("desktop.browser_launch", {})),
            "Interactive browser opened; select a tab.",
          )
        }
      >
        Open interactive browser
      </button>
      <label className="field">
        Browser tab
        <select value={tab} onChange={(e) => setTab(e.target.value)}>
          <option value="">Select a tab</option>
          {tabs.map((t) => (
            <option key={t.id} value={t.id}>
              {t.title || t.url}
            </option>
          ))}
        </select>
      </label>
      <input
        aria-label="Browser URL"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="https://… or authorised local test page"
      />
      <div className="row">
        <button
          disabled={busy || !tab || !url.trim()}
          onClick={() =>
            void operation(
              async () =>
                observe(
                  await call("desktop.browser_navigate", { tab_id: tab, url }),
                ),
              "Navigation returned; inspect the observed page.",
            )
          }
        >
          Navigate
        </button>
        <button
          disabled={busy || !tab}
          onClick={() =>
            void operation(
              async () =>
                observe(await call("desktop.browser_observe", { tab_id: tab })),
              "Tab inspected.",
            )
          }
        >
          Inspect tab
        </button>
        <button
          disabled={busy}
          onClick={() =>
            void operation(
              async () =>
                setTabs(
                  await call("desktop.browser_tab", { action: "new_tab", url: url.trim() || "about:blank" }),
                ),
              "New tab created.",
            )
          }
        >
          New tab
        </button>
        <button
          disabled={busy || !tab}
          onClick={() =>
            void operation(
              async () =>
                observe(
                  await call("desktop.browser_tab", {
                    action: "switch_tab",
                    tab_id: tab,
                  }),
                ),
              "Tab selected.",
            )
          }
        >
          Switch tab
        </button>
        <button
          disabled={busy || !tab}
          onClick={() =>
            void operation(async () => {
              setTabs(
                await call("desktop.browser_tab", {
                  action: "close_tab",
                  tab_id: tab,
                }),
              );
              setTab("");
              setObservation(undefined);
            }, "Tab closed.")
          }
        >
          Close tab
        </button>
      </div>
      {observation && (
        <>
          <h3>{observation.title}</h3>
          <p>{observation.message || observation.url}</p>
          <label className="field">
            Observed browser control
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="">Select a control</option>
              {options}
            </select>
          </label>
          <div className="row">
            <select
              aria-label="Browser control action"
              value={action}
              onChange={(e) => setAction(e.target.value as typeof action)}
            >
              {["click", "fill", "select", "scroll"].map((a) => (
                <option key={a}>{a}</option>
              ))}
            </select>
            <input
              aria-label="Browser control value"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="Requested value"
            />
            <input
              aria-label="Browser expected result"
              value={expected}
              onChange={(e) => setExpected(e.target.value)}
              placeholder="Expected visible completion control"
            />
            <button
              disabled={busy || !target}
              onClick={() =>
                void operation(
                  async () =>
                    observe(
                      await call("desktop.browser_action", {
                        target_id: target,
                        action,
                        value,
                        expected,
                      }),
                    ),
                  "Browser action returned; inspect verification.",
                )
              }
            >
              Review browser action
            </button>
          </div>
          <details>
            <summary>Attachments and downloads</summary>
            <div className="row">
              <button
                disabled={busy || !target}
                onClick={() =>
                  void operation(async () => {
                    const result = await window.olive.fileAction({
                      action: "browser-upload",
                      target_id: target,
                    });
                    if (result) observe(result as Observation);
                  }, "File selection finished; inspect upload state.")
                }
              >
                Select file for reviewed upload
              </button>
              <button
                disabled={busy || !target}
                onClick={() =>
                  void operation(async () => {
                    const result = await call<{
                      download: { id: string; filename: string; size: number };
                    }>("desktop.browser_download", { target_id: target });
                    setDownload(result.download);
                  }, "Download stored in quarantine.")
                }
              >
                Download to quarantine
              </button>
              {download && (
                <>
                  <span>
                    {download.filename} · {download.size} bytes
                  </span>
                  <button
                    disabled={busy}
                    onClick={() =>
                      void operation(
                        () =>
                          window.olive.fileAction({
                            action: "desktop-export-download",
                            download_id: download.id,
                          }),
                        "Export request finished; inspect any cancellation or failure notice.",
                      )
                    }
                  >
                    Export reviewed download
                  </button>
                </>
              )}
            </div>
          </details>
          <details>
            <summary>Review a browser message</summary>
            <p>
              Select the visible draft fields. OLIVE reads them back for a
              separate bound approval. Use supported bot/application
              integrations for Discord messaging.
            </p>
            {["destination", "subject", "body", "send"].map((key) => (
              <label className="field" key={key}>
                {key}
                <select
                  value={fields[key] || ""}
                  onChange={(e) =>
                    setFields({ ...fields, [key]: e.target.value })
                  }
                >
                  <option value="">Select the visible control</option>
                  {options}
                </select>
              </label>
            ))}
            <button
              disabled={
                busy ||
                !expected.trim() ||
                ["destination", "subject", "body", "send"].some(
                  (key) => !controls.some((c) => c.id === fields[key]),
                )
              }
              onClick={() =>
                void operation(
                  async () =>
                    setResult(
                      await call("desktop.browser_send", { fields, expected }),
                    ),
                  "Message operation returned; inspect actual verification before considering it sent.",
                )
              }
            >
              Read draft and request send review
            </button>
          </details>
          <Details value={observation} title="Browser observation details" />
        </>
      )}
      <details>
        <summary>Browser dialog</summary>
        <button
          disabled={busy}
          onClick={() =>
            void operation(
              async () => setDialog(await call("desktop.browser_dialog", {})),
              "Browser dialog state inspected.",
            )
          }
        >
          Inspect pending dialog
        </button>
        {dialog && (
          <>
            <p>
              {dialog.pending
                ? dialog.message
                : "No browser dialog is pending."}
            </p>
            {dialog.pending && (
              <button
                disabled={busy}
                onClick={() =>
                  void operation(async () => {
                    await call("desktop.browser_dialog", { dismiss: true });
                    setDialog(undefined);
                  }, "Browser dialog dismissed.")
                }
              >
                Review dismissal
              </button>
            )}
          </>
        )}
      </details>
      {result !== undefined && (
        <Details value={result} title="Browser operation result" />
      )}
    </section>
  );
}
