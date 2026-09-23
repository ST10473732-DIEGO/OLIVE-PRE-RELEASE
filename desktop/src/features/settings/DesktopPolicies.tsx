import { useState } from "react";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import type { Value } from "./types";
export function DesktopPolicies({ report }: { report: (e: unknown) => void }) {
  const resource = useResource(() =>
    call<{ settings: Record<string, Value>; platform_capabilities?: Record<string, unknown> }>("desktop.status", {}),
    ["desktop"],
  );
  const [draft, setDraft] = useState<Record<string, Value>>();
  const [notice, setNotice] = useState("");
  const values = draft || resource.data?.settings;
  return (
    <section>
      <h2>Desktop Control policies</h2>
      <p>
        Focus guards and action permissions remain active. Linux cannot detect all
        physical input; use Chat Stop before taking over. KDE access is provisioned
        for this installation and can be revoked independently. A global shortcut
        is optional.
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
      {resource.data?.platform_capabilities && <details>
        <summary>Capability diagnostics</summary>
        <p>Read-only status. A new Chat task checks the current permission and starts its own input session.</p>
        <pre>{JSON.stringify(resource.data.platform_capabilities, null, 2)}</pre>
      </details>}
    </section>
  );
}
