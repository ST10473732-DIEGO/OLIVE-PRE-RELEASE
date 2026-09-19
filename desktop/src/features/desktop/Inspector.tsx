import { useState } from "react";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import { Details } from "../../components/WorkspacePage";
import type { DesktopState, Operation } from "./types";
import LaunchTarget from "./LaunchTarget";

export default function Inspector({
  state,
  operation,
  busy,
  objective,
}: {
  state?: DesktopState;
  operation: Operation;
  busy: boolean;
  objective: string;
}) {
  const [windows, setWindows] = useState<
    { id: string; application: string; title: string }[]
  >([]);
  const [windowId, setWindowId] = useState("");
  const [selected, setSelected] = useState("");
  const [action, setAction] = useState<
    | "set_text"
    | "invoke"
    | "select"
    | "expand"
    | "collapse"
    | "scroll"
    | "search"
  >("invoke");
  const [text, setText] = useState("");
  const [expected, setExpected] = useState("");
  const [plan, setPlan] = useState<unknown>();
  const [permission, setPermission] = useState("communication.send");
  const [bindings, setBindings] = useState<Record<string, string>>({});
  const fields = useResource(() =>
    call<Record<string, string[]>>("desktop.consequence_fields", {}),
  );
  const controls = (state?.observation.controls || []).filter(
    (c) => !c.password,
  );
  const control = controls.find(
    (c) => JSON.stringify(c.runtime_id) === selected,
  );
  const options = controls.map((c) => (
    <option
      key={JSON.stringify(c.runtime_id)}
      value={JSON.stringify(c.runtime_id)}
    >
      {c.name || c.control_type} · {c.control_type}
    </option>
  ));
  return (
    <section aria-label="Application inspector">
      <LaunchTarget state={state} operation={operation} busy={busy} />
      <h2>Inspect an application</h2>
      <p>General discovery requests permission to read all visible window titles and process metadata. Use the owned launch above for target-only access.</p>
      <div className="row">
        <button
          disabled={busy}
          onClick={() =>
            void operation(async () => {
              setWindows(await call("desktop.list_windows", {}));
            }, "Window list refreshed.")
          }
        >
          List running windows
        </button>
        <select
          aria-label="Running window"
          value={windowId}
          onChange={(e) => setWindowId(e.target.value)}
        >
          <option value="">Select a window</option>
          {windows.map((w) => (
            <option key={w.id} value={w.id}>
              {w.application} — {w.title}
            </option>
          ))}
        </select>
        <button
          disabled={busy || !windowId}
          onClick={() =>
            void operation(async () => {
              await call("desktop.inspect", { window_id: windowId });
              setSelected("");
              setBindings({});
            }, "Window inspected. Choose an observed control.")
          }
        >
          Inspect selected window
        </button>
      </div>
      <label className="field">
        Observed control
        <select
          aria-label="Observed control"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          <option value="">Select a control</option>
          {options}
        </select>
      </label>
      {control && (
        <>
          <p>
            Supported actions:{" "}
            {control.actions.join(", ") || "No actions reported"}
          </p>
          <Details value={control} title="Observed control details" />
        </>
      )}
      <div className="row">
        <select
          aria-label="Control action"
          value={action}
          onChange={(e) => setAction(e.target.value as typeof action)}
        >
          {[
            "set_text",
            "invoke",
            "select",
            "expand",
            "collapse",
            "scroll",
            "search",
          ].map((a) => (
            <option key={a}>{a}</option>
          ))}
        </select>
        <input
          aria-label="Control text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Requested text or search query"
          maxLength={32000}
        />
        <input
          aria-label="Expected visible control"
          value={expected}
          onChange={(e) => setExpected(e.target.value)}
          placeholder="Expected visible control after action"
        />
      </div>
      <button
        disabled={
          busy || !control || (action !== "set_text" && !expected.trim())
        }
        onClick={() =>
          void operation(
            () =>
              call("desktop.perform", {
                action,
                target: { runtime_id: control!.runtime_id },
                arguments: ["set_text", "search"].includes(action)
                  ? { text }
                  : action === "scroll"
                    ? { direction: "down" }
                    : {},
                expected:
                  action === "set_text"
                    ? { runtime_id: control!.runtime_id, value: text }
                    : { name: expected },
              }),
            "Operation returned. Inspect the verification state above.",
          )
        }
      >
        Review and perform action
      </button>
      <details>
        <summary>Plan in inspected applications</summary>
        <p>
          The objective above is used for the plan. Reviewing a plan does not
          grant permission to execute its actions.
        </p>
        <button
          disabled={busy || !objective.trim()}
          onClick={() =>
            void operation(async () => {
              setPlan(await call("desktop.plan", { objective }));
            }, "Plan ready for inspection.")
          }
        >
          Create plan
        </button>
        {plan !== undefined && (
          <>
            <Details value={plan} title="Planned steps" />
            <button
              disabled={busy}
              onClick={() =>
                void operation(async () => {
                  await call("desktop.execute_plan", {});
                  setPlan(undefined);
                }, "Plan finished; inspect each observed result.")
              }
            >
              Execute reviewed plan
            </button>
          </>
        )}
      </details>
      <details>
        <summary>Review a consequential action</summary>
        <p>
          Select observed fields as evidence. The backend reads them again and
          requests a separate exact-action approval.
        </p>
        <label className="field">
          Action type
          <select
            value={permission}
            onChange={(e) => {
              setPermission(e.target.value);
              setBindings({});
            }}
          >
            {[
              ["communication.send", "Send message"],
              ["software.install", "Install free software"],
              ["application.delete", "Delete object"],
              ["application.submit", "Submit form"],
              ["application.security_settings", "Change security setting"],
            ].map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        {(fields.data?.[permission] || [])
          .filter(
            (key) => !(permission === "software.install" && key === "source"),
          )
          .map((key) => (
            <label className="field" key={key}>
              {key.replaceAll("_", " ")}
              <select
                value={bindings[key] || ""}
                onChange={(e) =>
                  setBindings({ ...bindings, [key]: e.target.value })
                }
              >
                <option value="">Select evidence control</option>
                {options}
              </select>
            </label>
          ))}
        <button
          disabled={
            busy ||
            !control ||
            !expected.trim() ||
            !fields.data ||
            fields.data[permission]
              .filter(
                (key) =>
                  !(permission === "software.install" && key === "source"),
              )
              .some(
                (key) =>
                  !controls.some(
                    (c) => JSON.stringify(c.runtime_id) === bindings[key],
                  ),
              )
          }
          onClick={() =>
            void operation(
              () =>
                call("desktop.consequence", {
                  permission,
                  target: { runtime_id: control!.runtime_id },
                  bindings: Object.fromEntries(
                    Object.entries(bindings).map(([key, id]) => [
                      key,
                      {
                        runtime_id: controls.find(
                          (c) => JSON.stringify(c.runtime_id) === id,
                        )!.runtime_id,
                      },
                    ]),
                  ),
                  expected: { name: expected },
                }),
              "Operation returned; inspect verification before considering it complete.",
            )
          }
        >
          Review bound action
        </button>
      </details>
    </section>
  );
}
