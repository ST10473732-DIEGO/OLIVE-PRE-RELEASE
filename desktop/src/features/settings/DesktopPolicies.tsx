import { useState } from "react";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import type { Value } from "./types";
export function DesktopPolicies({ report }: { report: (e: unknown) => void }) {
  const resource = useResource(() =>
    call<{ settings: Record<string, Value> }>("desktop.status", {}),
  );
  const [draft, setDraft] = useState<Record<string, Value>>();
  const [notice, setNotice] = useState("");
  const values = draft || resource.data?.settings;
  return (
    <section>
      <h2>Desktop Control policies</h2>
      <p>
        Focus guards, user takeover and action permissions remain active.
        Emergency stop is also available through Ctrl+Alt+Escape when Windows
        accepts the shortcut.
      </p>
      {resource.error && <p role="alert">{resource.error}</p>}
      {values && (
        <>
          <div className="settings-fields">
            {Object.entries(values).map(([key, value]) => (
              <label
                className={typeof value === "boolean" ? "check-field" : "field"}
                key={key}
              >
                <span>{key.replaceAll("_", " ")}</span>
                {typeof value === "boolean" ? (
                  <input
                    type="checkbox"
                    checked={value}
                    onChange={(e) =>
                      setDraft({ ...values, [key]: e.target.checked })
                    }
                  />
                ) : typeof value === "number" ? (
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={value}
                    onChange={(e) =>
                      setDraft({ ...values, [key]: Number(e.target.value) })
                    }
                  />
                ) : (
                  <select
                    value={value}
                    onChange={(e) =>
                      setDraft({ ...values, [key]: e.target.value })
                    }
                  >
                    {(key.endsWith("policy")
                      ? ["deny", "ask", "allow"]
                      : key === "emergency_shortcut"
                        ? ["Ctrl+Alt+Escape", ""]
                        : ["pause"]
                    ).map((option) => (
                      <option key={option} value={option}>
                        {option || "Disabled"}
                      </option>
                    ))}
                  </select>
                )}
              </label>
            ))}
          </div>
          <div className="row">
            <button
              onClick={() =>
                void call("desktop.configure", { settings: values })
                  .then(() => setNotice("Desktop policies saved."))
                  .catch(report)
              }
            >
              Save desktop policies
            </button>
            <button
              onClick={() =>
                void window.olive
                  .stopControl()
                  .then(() => setNotice("Emergency stop requested."))
                  .catch(report)
              }
            >
              Stop desktop control
            </button>
          </div>
        </>
      )}
      <p role="status">{notice}</p>
    </section>
  );
}
