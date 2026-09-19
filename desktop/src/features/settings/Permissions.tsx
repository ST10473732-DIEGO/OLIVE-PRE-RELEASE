import { useState } from "react";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import { Details } from "../../components/WorkspacePage";
type Decision = "allow" | "ask" | "deny";
interface Scope {
  permission: string;
  decision: Decision;
  path?: string;
  application?: string;
}
interface Policy {
  permissions: Record<string, Decision>;
  scopes: Scope[];
  trusted_actions?: unknown[];
}
export function Permissions({ report }: { report: (e: unknown) => void }) {
  const resource = useResource(() => call<Policy>("data.permissions", {}));
  const [draft, setDraft] = useState<Policy>();
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState("");
  const value = draft || resource.data;
  if (!value)
    return <p role="status">{resource.error || "Loading permissions…"}</p>;
  const choices = (
    <>
      <option value="allow">Allow</option>
      <option value="ask">Ask</option>
      <option value="deny">Deny</option>
    </>
  );
  return (
    <section>
      <h2>Permissions and execution</h2>
      <p>
        Rules apply to every route. Native execution requires an approved
        workspace; untrusted code requires an available isolation provider.
      </p>
      <label className="field">
        Find a permission
        <input value={query} onChange={(e) => setQuery(e.target.value)} />
      </label>
      <div className="settings-fields">
        {Object.entries(value.permissions)
          .filter(([name]) => name.includes(query))
          .map(([name, decision]) => (
            <label className="field" key={name}>
              <span>{name}</span>
              <select
                value={decision}
                onChange={(e) =>
                  setDraft({
                    ...value,
                    permissions: {
                      ...value.permissions,
                      [name]: e.target.value as Decision,
                    },
                  })
                }
              >
                {choices}
              </select>
            </label>
          ))}
      </div>
      <h3>Folder and application rules</h3>
      {value.scopes.map((scope, index) => (
        <div className="scope-row" key={index}>
          <label className="field">
            Permission
            <select
              value={scope.permission}
              onChange={(e) =>
                setDraft({
                  ...value,
                  scopes: value.scopes.map((s, i) =>
                    i === index ? { ...s, permission: e.target.value } : s,
                  ),
                })
              }
            >
              {Object.keys(value.permissions).map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>
          <label className="field">
            Application
            <input
              value={scope.application || ""}
              onChange={(e) =>
                setDraft({
                  ...value,
                  scopes: value.scopes.map((s, i) =>
                    i === index ? { ...s, application: e.target.value } : s,
                  ),
                })
              }
            />
          </label>
          <label className="field">
            Absolute folder
            <input
              value={scope.path || ""}
              onChange={(e) =>
                setDraft({
                  ...value,
                  scopes: value.scopes.map((s, i) =>
                    i === index ? { ...s, path: e.target.value } : s,
                  ),
                })
              }
            />
          </label>
          <label className="field">
            Decision
            <select
              value={scope.decision}
              onChange={(e) =>
                setDraft({
                  ...value,
                  scopes: value.scopes.map((s, i) =>
                    i === index
                      ? { ...s, decision: e.target.value as Decision }
                      : s,
                  ),
                })
              }
            >
              {choices}
            </select>
          </label>
          <button
            onClick={() =>
              setDraft({
                ...value,
                scopes: value.scopes.filter((_, i) => i !== index),
              })
            }
          >
            Remove rule {index + 1}
          </button>
        </div>
      ))}
      <div className="row">
        <button
          onClick={() =>
            setDraft({
              ...value,
              scopes: [
                ...value.scopes,
                { permission: "filesystem.read", decision: "ask", path: "" },
              ],
            })
          }
        >
          Add rule
        </button>
        <button
          className="primary"
          onClick={() =>
            void call<Policy>("data.save_permissions", {
              permissions: value.permissions,
              scopes: value.scopes,
            })
              .then((saved) => {
                setDraft(saved);
                setNotice("Permission rules saved.");
              })
              .catch(report)
          }
        >
          Save permission rules
        </button>
      </div>
      <Details
        value={value.trusted_actions || []}
        title="Remembered approvals"
      />
      <button
        onClick={() =>
          void call("data.clear_approvals", {})
            .then(() => {
              setDraft(undefined);
              setNotice("Remembered approvals cleared.");
              return resource.refresh();
            })
            .catch(report)
        }
      >
        Clear remembered approvals
      </button>
      <p role="status">{notice}</p>
    </section>
  );
}
