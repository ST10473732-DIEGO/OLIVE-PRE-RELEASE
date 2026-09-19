import { useState } from "react";
import type { ReactNode } from "react";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import { EmptyState } from "../../components/WorkspacePage";
import type { ProjectOption, Contact, Page, BaseRecord } from "./types";
export function useOperation(refresh?: () => Promise<unknown>) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const run = async (
    fn: () => Promise<unknown>,
    message = "Saved locally.",
  ) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      await refresh?.();
      setNotice(message);
      return true;
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "The operation failed. Your changes were not confirmed.",
      );
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, notice, run };
}
export function Feedback({
  error,
  notice,
  loading,
}: {
  error?: string;
  notice?: string;
  loading?: boolean;
}) {
  return (
    <>
      {loading && <p role="status">Loading local records…</p>}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
    </>
  );
}
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="personal-field">
      <span>{label}</span>
      {children}
    </label>
  );
}
export function ProjectSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const r = useResource(
    () => call<ProjectOption[]>("data.projects", {}),
    ["projects"],
  );
  return (
    <Field label="Project">
      <select
        aria-label="Project"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">No project</option>
        {r.data?.map((p) => (
          <option key={p.id} value={p.id}>
            {p.title}
          </option>
        ))}
      </select>
    </Field>
  );
}
export function ProjectLinks({
  values,
  onChange,
}: {
  values: string[];
  onChange: (values: string[]) => void;
}) {
  const r = useResource(
    () => call<ProjectOption[]>("data.projects", {}),
    ["projects"],
  );
  return (
    <fieldset>
      <legend>Linked projects</legend>
      {r.data?.length ? (
        r.data.map((p) => (
          <label className="personal-check" key={p.id}>
            <input
              type="checkbox"
              checked={values.includes(p.id)}
              onChange={(e) =>
                onChange(
                  e.target.checked
                    ? [...values, p.id]
                    : values.filter((id) => id !== p.id),
                )
              }
            />
            {p.title}
          </label>
        ))
      ) : (
        <p>No saved projects. Create one in Projects to link it.</p>
      )}
      {r.error && <p role="alert">{r.error}</p>}
    </fieldset>
  );
}
export function Blank({
  title,
  children,
  icon,
  actions,
  compact,
}: {
  title: string;
  children: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  compact?: boolean;
}) {
  return (
    <EmptyState className="personal-empty" icon={icon} title={title} actions={actions} compact={compact}>
      {children}
    </EmptyState>
  );
}
export function ContactLinks({
  values,
  onChange,
}: {
  values: string[];
  onChange: (values: string[]) => void;
}) {
  const [query, setQuery] = useState("");
  const found = useResource(
    () => call<Page<Contact>>("contacts.search", { query, limit: 10 }),
    ["personal.changed"],
    query,
  );
  const selected = useResource(
    () =>
      Promise.all(
        values.map((record_id) => call<Contact>("contacts.get", { record_id })),
      ),
    ["personal.changed"],
    values.join("|"),
  );
  const rows = [
    ...new Map(
      [...(selected.data || []), ...(found.data?.items || [])].map((c) => [
        c.id,
        c,
      ]),
    ).values(),
  ];
  return (
    <fieldset>
      <legend>Linked contacts</legend>
      <input
        aria-label="Find linked contacts"
        placeholder="Search names or aliases"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {rows.map((c) => (
        <label className="personal-check" key={c.id}>
          <input
            type="checkbox"
            checked={values.includes(c.id)}
            onChange={(e) =>
              onChange(
                e.target.checked
                  ? [...values, c.id]
                  : values.filter((id) => id !== c.id),
              )
            }
          />
          {c.display_name}
          {c.organization && ` · ${c.organization}`}
        </label>
      ))}
      <Feedback error={found.error || selected.error} />
    </fieldset>
  );
}
export function AgentAttemptLink({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const [query, setQuery] = useState("");
  const r = useResource(
    () =>
      call<{ id: string; user_request: string; state: string }[]>(
        "agent.history",
        { query, offset: 0 },
      ),
    ["agent"],
    query,
  );
  return (
    <details>
      <summary>Link an Agent execution attempt</summary>
      <p>This reference never starts, completes or resumes an Agent task.</p>
      <input
        aria-label="Search Agent attempts"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <Field label="Agent attempt">
        <select
          aria-label="Agent attempt"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">No linked attempt</option>
          {value && !r.data?.some((t) => t.id === value) && (
            <option value={value}>Linked attempt: {value}</option>
          )}
          {r.data?.map((t) => (
            <option key={t.id} value={t.id}>
              {t.user_request} · {t.state}
            </option>
          ))}
        </select>
      </Field>
      <Feedback error={r.error} />
    </details>
  );
}
export function RecordSource({ record }: { record: BaseRecord }) {
  return (
    <details>
      <summary>Record source and revision</summary>
      <p>
        Revision {record.revision} · ID {record.id}
      </p>
      {Object.entries(record.provenance || {}).map(([phase, source]) => (
        <div key={phase}>
          <strong>{phase}</strong>
          <dl>
            {source !== null &&
              typeof source === "object" &&
              Object.entries(source).map(([key, value]) => (
                <div key={key}>
                  <dt>{key.replaceAll("_", " ")}</dt>
                  <dd className="personal-note">{String(value)}</dd>
                </div>
              ))}
          </dl>
        </div>
      ))}
    </details>
  );
}
