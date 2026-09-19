import { Search } from "lucide-react";
import { useEffect, useState } from "react";
import { WorkspacePage } from "../../components/WorkspacePage";
import { Sheet } from "../../components/Sheet";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import { body, type Contact, type Page, type Labelled } from "./types";
import {
  Blank,
  Field,
  Feedback,
  ProjectLinks,
  RecordSource,
  useOperation,
} from "./shared";
import Interchange from "./Interchange";
type Merge = {
  keep_id: string;
  remove_id: string;
  keep_revision: number;
  remove_revision: number;
  proposed: Omit<
    Contact,
    "id" | "uid" | "revision" | "kind" | "created_at" | "updated_at"
  >;
  conflicts: { field: string; keep: string; remove: string }[];
  scope: string;
};
const empty = {
  id: "",
  uid: "",
  kind: "contact",
  revision: 0,
  created_at: "",
  updated_at: "",
  display_name: "",
  emails: [],
  phones: [],
  organization: "",
  aliases: [],
  notes: "",
  external_ids: [],
  project_ids: [],
  unsupported: [],
} satisfies Contact;
function Identifiers({
  title,
  values,
  onChange,
}: {
  title: string;
  values: Labelled[];
  onChange: (values: Labelled[]) => void;
}) {
  return (
    <fieldset>
      <legend>{title}</legend>
      {values.map((entry, i) => (
        <div className="personal-identifier" key={i}>
          <input
            aria-label={`${title} label ${i + 1}`}
            value={entry.label}
            onChange={(e) =>
              onChange(
                values.map((x, n) =>
                  n === i ? { ...x, label: e.target.value } : x,
                ),
              )
            }
          />
          <input
            aria-label={`${title} value ${i + 1}`}
            value={entry.value}
            onChange={(e) =>
              onChange(
                values.map((x, n) =>
                  n === i ? { ...x, value: e.target.value } : x,
                ),
              )
            }
          />
          <button
            type="button"
            aria-label={`Remove ${title} ${i + 1}`}
            onClick={() => onChange(values.filter((_, n) => n !== i))}
          >
            Remove
          </button>
        </div>
      ))}
      <button
        type="button"
        disabled={values.length >= 20}
        onClick={() => onChange([...values, { label: "other", value: "" }])}
      >
        Add {title.toLowerCase()}
      </button>
    </fieldset>
  );
}
export default function Contacts({
  target,
}: {
  target?: { id: string; revision: number };
}) {
  const [query, setQuery] = useState(""),
    [page, setPage] = useState(0),
    [selected, setSelected] = useState<Contact>(),
    [edit, setEdit] = useState<Contact>(),
    [merge, setMerge] = useState<Merge>(),
    [reviewed, setReviewed] = useState(false);
  const r = useResource(
    () =>
      call<Page<Contact>>("contacts.search", {
        query,
        limit: 30,
        offset: page * 30,
      }),
    ["personal.changed"],
    query + page,
  );
  const op = useOperation(r.refresh);
  const [targetError, setTargetError] = useState("");
  useEffect(() => {
    if (!target) return;
    let active = true;
    void call<Contact>("contacts.get", { record_id: target.id })
      .then((value) => {
        if (active) setSelected(value);
      })
      .catch((error) => {
        if (active)
          setTargetError(
            error instanceof Error
              ? error.message
              : "The linked record could not be opened.",
          );
      });
    return () => {
      active = false;
    };
  }, [target]);

  const duplicates = useResource(
    () =>
      selected
        ? call<{
            items: { id: string; display_name: string; reason: string }[];
          }>("contacts.duplicates", { record_id: selected.id })
        : Promise.resolve({ items: [] }),
    ["personal.changed"],
    selected?.id || "",
  );
  return (
    <WorkspacePage
      title="Contacts"
      description="People and relationships, stored on your device."
      actions={
        <button className="primary" onClick={() => setEdit({ ...empty })}>
          Add Contact
        </button>
      }
    >
      <div className="row spread personal-toolbar">
        <label className="search">
          <Search size={15} aria-hidden="true" />
          <input
            aria-label="Search contacts"
            placeholder="Search people, aliases or organisations"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
          />
        </label>
        <Interchange kind="contact" onChanged={r.refresh} />
      </div>
      <Feedback
        error={targetError || op.error || r.error}
        notice={op.notice}
        loading={r.loading}
      />
      <div className="personal-split">
        <section aria-label="Contact list">
          {!r.loading && !r.error && !r.data?.items.length ? (
            <Blank
              title={
                query ? "No matching contacts" : "Your people, in one place"
              }
            >
              {query
                ? "Try a name, alias or organisation."
                : "Add a contact or import a local CSV/vCard file. No online account is needed."}
            </Blank>
          ) : (
            <div className="personal-list">
              {r.data?.items.map((c) => (
                <button
                  className={`personal-list-item ${selected?.id === c.id ? "selected" : ""}`}
                  key={c.id}
                  aria-current={selected?.id === c.id ? "true" : undefined}
                  title={c.display_name}
                  onClick={() => setSelected(c)}
                >
                  <span className="personal-initial" aria-hidden="true">
                    {(c.display_name || "?").trim().charAt(0).toUpperCase()}
                  </span>
                  <span className="personal-list-text">
                    <strong>{c.display_name}</strong>
                    <span className="muted">
                      {c.organization || c.emails[0]?.value || "Local contact"}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          )}
          {(page > 0 || r.data?.has_more) && (
            <div className="row personal-paging">
              <button disabled={!page} onClick={() => setPage(page - 1)}>
                Previous
              </button>
              <button
                disabled={!r.data?.has_more}
                onClick={() => setPage(page + 1)}
              >
                Next
              </button>
            </div>
          )}
        </section>
        <section aria-label="Contact detail" className="personal-detail">
          {selected ? (
            <>
              <header className="row spread">
                <h2>{selected.display_name}</h2>
                <button onClick={() => setEdit(selected)}>Edit Contact</button>
              </header>
              <p>{selected.organization}</p>
              {[
                ...selected.emails,
                ...selected.phones,
                ...selected.external_ids,
              ].map((x, i) => (
                <p key={i}>
                  <span className="muted">{x.label}</span> · {x.value}
                </p>
              ))}
              <RecordSource record={selected} />
              <p>Aliases: {selected.aliases.join(", ") || "None"}</p>
              <p className="personal-note">{selected.notes}</p>
              <p className="muted">
                External identifiers are metadata, not permission to
                communicate.
              </p>
              {!!duplicates.data?.items.length && (
                <section>
                  <h3>Possible duplicates</h3>
                  {duplicates.data.items.map((d) => (
                    <button
                      className="personal-list-item"
                      key={d.id}
                      onClick={() =>
                        void op.run(async () => {
                          setMerge(
                            await call<Merge>("contacts.merge_preview", {
                              keep_id: selected.id,
                              remove_id: d.id,
                            }),
                          );
                          setReviewed(false);
                        }, "Merge preview only; no records changed.")
                      }
                    >
                      <strong>{d.display_name}</strong>
                      <span>{d.reason} · Review merge</span>
                    </button>
                  ))}
                </section>
              )}
              <button
                onClick={() =>
                  void op.run(async () => {
                    await call("contacts.delete", {
                      record_id: selected.id,
                      revision: selected.revision,
                    });
                    setSelected(undefined);
                  }, "Contact deleted; local references updated.")
                }
              >
                Delete Contact…
              </button>
            </>
          ) : (
            <Blank title="Select a person">
              Contact details and contextual actions appear here.
            </Blank>
          )}
        </section>
      </div>
      <Sheet
        open={!!edit}
        onOpenChange={(open) => {
          if (!open) setEdit(undefined);
        }}
        title={edit?.id ? "Edit Contact" : "Add Contact"}
        description="Save directly to your local address book. This sends no communication."
      >
        {edit && (
          <form
            className="personal-form"
            onSubmit={(e) => {
              e.preventDefault();
              void op.run(async () => {
                const saved = await call<Contact>(
                  edit.id ? "contacts.update" : "contacts.create",
                  {
                    body: {
                      ...body(edit),
                      aliases: edit.aliases.filter((x) => x.trim()),
                    },
                    ...(edit.id
                      ? { record_id: edit.id, revision: edit.revision }
                      : {}),
                  },
                );
                setSelected(saved);
                setEdit(undefined);
              });
            }}
          >
            <Field label="Contact name">
              <input
                required
                aria-label="Contact name"
                value={edit.display_name}
                onChange={(e) =>
                  setEdit({ ...edit, display_name: e.target.value })
                }
              />
            </Field>
            <Field label="Organisation">
              <input
                aria-label="Organisation"
                value={edit.organization}
                onChange={(e) =>
                  setEdit({ ...edit, organization: e.target.value })
                }
              />
            </Field>
            <Identifiers
              title="Emails"
              values={edit.emails}
              onChange={(emails) => setEdit({ ...edit, emails })}
            />
            <Identifiers
              title="Phones"
              values={edit.phones}
              onChange={(phones) => setEdit({ ...edit, phones })}
            />
            <Field label="Aliases (comma separated)">
              <input
                aria-label="Aliases"
                value={edit.aliases.join(", ")}
                onChange={(e) =>
                  setEdit({
                    ...edit,
                    aliases: e.target.value.split(",").map((x) => x.trim()),
                  })
                }
              />
            </Field>
            <Field label="Notes">
              <textarea
                aria-label="Notes"
                rows={3}
                value={edit.notes}
                onChange={(e) => setEdit({ ...edit, notes: e.target.value })}
              />
            </Field>
            <ProjectLinks
              values={edit.project_ids}
              onChange={(project_ids) => setEdit({ ...edit, project_ids })}
            />
            <details>
              <summary>External identifiers</summary>
              <Identifiers
                title="External identifiers"
                values={edit.external_ids}
                onChange={(external_ids) => setEdit({ ...edit, external_ids })}
              />
            </details>
            <Feedback error={op.error} />
            <button className="primary" disabled={op.busy}>
              Save Contact
            </button>
          </form>
        )}
      </Sheet>
      <Sheet
        open={!!merge}
        onOpenChange={(open) => {
          if (!open) setMerge(undefined);
        }}
        title="Merge contacts"
        description={merge?.scope || "Review both records before merging."}
      >
        {merge && (
          <>
            <p>
              Keep {merge.proposed.display_name}. Combined identifiers and
              project links are retained.
            </p>
            {merge.conflicts.map((c) => (
              <Field label={c.field} key={c.field}>
                <select
                  aria-label={`Merge ${c.field}`}
                  value={String(
                    merge.proposed[c.field as keyof typeof merge.proposed],
                  )}
                  onChange={(e) =>
                    setMerge({
                      ...merge,
                      proposed: {
                        ...merge.proposed,
                        [c.field]: e.target.value,
                      },
                    })
                  }
                >
                  <option value={c.keep}>Keep: {c.keep}</option>
                  <option value={c.remove}>Use: {c.remove}</option>
                </select>
              </Field>
            ))}
            <p>
              {merge.proposed.emails.length} emails ·{" "}
              {merge.proposed.phones.length} phones ·{" "}
              {merge.proposed.project_ids.length} project links
            </p>
            <section aria-label="Merged contact preview">
              <h3>Result after merge</h3>
              <p>
                {merge.proposed.display_name} ·{" "}
                {merge.proposed.organization || "No organisation"}
              </p>
              {[
                ...merge.proposed.emails,
                ...merge.proposed.phones,
                ...merge.proposed.external_ids,
              ].map((entry, index) => (
                <p className="personal-note" key={index}>
                  {entry.label}: {entry.value}
                </p>
              ))}
              {!!merge.proposed.aliases.length && (
                <p>Aliases: {merge.proposed.aliases.join(", ")}</p>
              )}
              {merge.proposed.notes && (
                <p className="personal-note">Notes: {merge.proposed.notes}</p>
              )}
              <details>
                <summary>Records and project references</summary>
                <p className="personal-note">
                  Keep {merge.keep_id} (revision {merge.keep_revision}). Remove{" "}
                  {merge.remove_id} (revision {merge.remove_revision}).
                </p>
                {merge.proposed.project_ids.map((id) => (
                  <p className="personal-note" key={id}>
                    Project {id}
                  </p>
                ))}
              </details>
            </section>
            <label>
              <input
                type="checkbox"
                checked={reviewed}
                onChange={(e) => setReviewed(e.target.checked)}
              />
              I reviewed the affected fields and relationships
            </label>
            <Feedback error={op.error} />
            <button
              disabled={!reviewed || op.busy}
              onClick={() =>
                void op.run(async () => {
                  const saved = await call<Contact>("contacts.merge", {
                    preview: { ...merge, conflicts_reviewed: reviewed },
                  });
                  setSelected(saved);
                  setMerge(undefined);
                }, "Contacts merged locally.")
              }
            >
              Review and merge
            </button>
          </>
        )}
      </Sheet>
    </WorkspacePage>
  );
}
