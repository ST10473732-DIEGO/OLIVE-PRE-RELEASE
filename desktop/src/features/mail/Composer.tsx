import { useEffect, useRef, useState } from "react";
import { Paperclip, Send, Save, X } from "lucide-react";
import { call } from "../../services/api";
import { Field, Feedback, ProjectSelect } from "../personal/shared";
import { draftBody, outcomeLabel } from "./types";
import type { MailRecord, Connection, Submission } from "./types";
import RecipientPicker from "./RecipientPicker";

export default function Composer({
  initial,
  connections,
  onSaved,
  onClose,
  registerFlush,
}: {
  initial: MailRecord;
  connections: Connection[];
  onSaved: (r: MailRecord) => void;
  onClose: () => void;
  registerFlush: (fn: (() => Promise<MailRecord>) | null) => void;
}) {
  const [draft, setDraft] = useState(initial),
    [to, setTo] = useState(initial.to.join(", ")),
    [cc, setCc] = useState(initial.cc.join(", ")),
    [bcc, setBcc] = useState(initial.bcc.join(", "));
  const [status, setStatus] = useState("Saved locally"),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [submission, setSubmission] = useState<Submission>();
  const [comparison, setComparison] = useState<MailRecord>();
  const base = useRef(initial),
    generation = useRef(0),
    savedGeneration = useRef(0),
    saving = useRef<Promise<MailRecord> | null>(null),
    latest = useRef({ draft, to, cc, bcc });
  latest.current = { draft, to, cc, bcc };
  const locked = [
    "submitting",
    "accepted",
    "partially_accepted",
    "outcome_uncertain",
  ].includes(base.current.submission_state || "");
  const changed = () => {
    generation.current++;
    setStatus("Unsaved changes");
    setError("");
  };
  const save = async (): Promise<MailRecord> => {
    if (saving.current) {
      await saving.current;
      return save();
    }
    if (generation.current === savedGeneration.current) return base.current;
    const version = generation.current,
      v = latest.current;
    const split = (value: string) =>
      value
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    const body = draftBody({
      ...v.draft,
      to: split(v.to),
      cc: split(v.cc),
      bcc: split(v.bcc),
    });
    setStatus("Saving locally…");
    const promise = call<MailRecord>("mail.save_draft", {
      record_id: base.current.id,
      revision: base.current.revision,
      body,
    });
    saving.current = promise;
    try {
      const result = await promise;
      base.current = result;
      savedGeneration.current = version;
      onSaved(result);
      setStatus(
        generation.current === version ? "Saved locally" : "Unsaved changes",
      );
      return result;
    } catch (e) {
      setStatus("Not saved");
      setError(
        e instanceof Error
          ? e.message
          : "Could not save this draft. Your editor text is retained.",
      );
      throw e;
    } finally {
      saving.current = null;
    }
  };
  const saveRef = useRef(save);
  saveRef.current = save;
  const registerRef = useRef(registerFlush);
  registerRef.current = registerFlush;
  useEffect(() => {
    registerRef.current(() => saveRef.current());
    return () => registerRef.current(null);
  }, []);
  useEffect(() => {
    if (locked || generation.current === savedGeneration.current) return;
    const timer = setTimeout(() => {
      void saveRef.current().catch(() => {});
    }, 900);
    return () => clearTimeout(timer);
  }, [draft, to, cc, bcc, locked]);
  const perform = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Operation not completed");
    } finally {
      setBusy(false);
    }
  };
  const edit = (key: keyof MailRecord, value: unknown) => {
    changed();
    setDraft({ ...draft, [key]: value });
  };
  return (
    <section className="mail-composer" aria-label="Mail composer">
      <header className="row spread">
        <h2>{locked ? "Submission record" : "Compose"}</h2>
        <button
          className="icon-button"
          aria-label="Close composer"
          onClick={() =>
            void perform(async () => {
              await save();
              onClose();
            })
          }
        >
          <X size={18} />
        </button>
      </header>
      <p role="status" className="muted">
        {status}. Drafts remain on this device.
      </p>
      <fieldset disabled={locked} className="mail-compose-fields">
        <RecipientPicker
          select={(address) => {
            changed();
            setTo((current) => (current ? current + ", " + address : address));
          }}
        />
        <Field label="From / sending identity">
          <select
            aria-label="From / sending identity"
            value={draft.connection_id}
            onChange={(e) => {
              const selected = connections.find((c) => c.id === e.target.value);
              changed();
              setDraft({
                ...draft,
                connection_id: e.target.value,
                from: selected?.sender || "",
              });
            }}
          >
            <option value="">Draft without a configured sender</option>
            {connections
              .filter((c) => c.smtp || c.id === draft.connection_id)
              .map((c) => (
                <option key={c.id} value={c.id} disabled={!c.smtp}>
                  {c.name} · {c.sender || "No sender"}
                  {!c.smtp ? " (incoming only; sending needs setup)" : ""}
                  {!c.enabled ? " (disconnected)" : ""}
                </option>
              ))}
          </select>
        </Field>
        <Field label="To">
          <input
            value={to}
            onChange={(e) => {
              changed();
              setTo(e.target.value);
            }}
            placeholder="Exact email addresses, separated by commas"
          />
        </Field>
        <div className="mail-field-pair">
          <Field label="CC">
            <input
              value={cc}
              onChange={(e) => {
                changed();
                setCc(e.target.value);
              }}
            />
          </Field>
          <Field label="BCC">
            <input
              value={bcc}
              onChange={(e) => {
                changed();
                setBcc(e.target.value);
              }}
            />
          </Field>
        </div>
        <Field label="Subject">
          <input
            value={draft.subject}
            onChange={(e) => edit("subject", e.target.value)}
            maxLength={1000}
          />
        </Field>
        <Field label="Message">
          <textarea
            aria-label="Message"
            className="mail-body-input"
            value={draft.text}
            onChange={(e) => edit("text", e.target.value)}
            maxLength={160000}
          />
        </Field>
        <ProjectSelect
          value={draft.project_id}
          onChange={(id) => edit("project_id", id)}
        />
        <div className="mail-attachments">
          {draft.attachments.map((a) => (
            <div className="row spread" key={a.id}>
              <span>
                {a.name} · {a.size.toLocaleString()} bytes · snapshot
              </span>
              <button
                aria-label={`Remove ${a.name}`}
                onClick={() =>
                  edit(
                    "attachments",
                    draft.attachments.filter((item) => item.id !== a.id),
                  )
                }
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      </fieldset>
      <Feedback error={error} />
      {!draft.subject && <p className="muted">This draft has no subject.</p>}
      {error && (
        <button
          onClick={() =>
            void perform(async () =>
              setComparison(
                await call<MailRecord>("mail.get", {
                  record_id: base.current.id,
                }),
              ),
            )
          }
        >
          Compare saved draft
        </button>
      )}
      {comparison && (
        <section className="mail-conflict">
          <h3>Current saved version · revision {comparison.revision}</h3>
          <p>
            To: {comparison.to.join(", ")} · Subject: {comparison.subject}
          </p>
          <pre className="mail-plain">{comparison.text}</pre>
          <div className="row wrap">
            <button
              onClick={() => {
                base.current = comparison;
                setDraft(comparison);
                setTo(comparison.to.join(", "));
                setCc(comparison.cc.join(", "));
                setBcc(comparison.bcc.join(", "));
                generation.current = 0;
                savedGeneration.current = 0;
                setComparison(undefined);
                setError("");
                setStatus("Saved locally");
                onSaved(comparison);
              }}
            >
              Use saved version
            </button>
            <button
              onClick={() =>
                void perform(async () => {
                  base.current = comparison;
                  generation.current++;
                  await save();
                  setComparison(undefined);
                })
              }
            >
              Save my editor version against this revision
            </button>
          </div>
        </section>
      )}
      {!draft.connection_id && (
        <p>
          Mail delivery is not configured. You can save and reopen this draft.
        </p>
      )}
      <footer className="row wrap">
        <button
          disabled={busy || locked}
          onClick={() =>
            void perform(async () => {
              await save();
            })
          }
        >
          <Save size={16} />
          Save draft
        </button>
        <button
          disabled={busy || locked}
          onClick={() =>
            void perform(async () => {
              const record = await save();
              const result = (await window.olive.fileAction({
                action: "mail-attach",
                record_id: record.id,
                revision: record.revision,
              })) as MailRecord | null;
              if (result) {
                base.current = result;
                setDraft({
                  ...latest.current.draft,
                  attachments: result.attachments,
                });
                onSaved(result);
              }
            })
          }
        >
          <Paperclip size={16} />
          Attach file
        </button>
        <button
          className="primary"
          disabled={busy || locked || !draft.connection_id}
          onClick={() =>
            void perform(async () => {
              const record = await save();
              const prepared = await call<Submission>("mail.prepare", {
                record_id: record.id,
                revision: record.revision,
              });
              setSubmission(prepared);
              const result = await call<Submission>("mail.send", {
                submission_id: prepared.id,
                expected_fingerprint: prepared.fingerprint,
                preview: prepared.preview,
              }).catch(async (error) => {
                const outcomes = await call<{ items: Submission[] }>(
                  "mail.outbox",
                  {},
                );
                const current = outcomes.items.find(
                  (r) => r.id === prepared.id,
                );
                if (current) setSubmission(current);
                throw error;
              });
              setSubmission(result);
              const current = await call<MailRecord>("mail.get", {
                record_id: record.id,
              });
              base.current = current;
              onSaved(current);
              setStatus(outcomeLabel[result.state] || result.state);
            })
          }
        >
          <Send size={16} />
          Review submission
        </button>
        {busy && submission && (
          <button
            onClick={() =>
              void call<Submission>("mail.cancel", {
                submission_id: submission.id,
              })
                .then((result) => {
                  if (result.state === "cancelled") setSubmission(result);
                  else
                    setStatus(
                      "Cancellation requested; any possible submission must still be checked.",
                    );
                })
                .catch((e) => setError(String(e)))
            }
          >
            Cancel submission
          </button>
        )}
      </footer>
      <details className="mail-actions">
        <summary>Draft actions</summary>
        <div className="row wrap">
          <button
            disabled={busy}
            onClick={() =>
              void perform(async () => {
                const record = await save();
                const copy = await call<MailRecord>("mail.reply", {
                  record_id: record.id,
                  mode: "duplicate",
                });
                onSaved(copy);
              })
            }
          >
            Duplicate as new draft
          </button>
          <button
            disabled={busy}
            onClick={() =>
              void perform(async () => {
                const record = await save();
                await window.olive.fileAction({
                  action: "mail-export",
                  record_id: record.id,
                });
              })
            }
          >
            Export draft EML
          </button>
          <button
            disabled={busy || locked}
            onClick={() =>
              void perform(async () => {
                const record = await save();
                await call("mail.discard", {
                  record_id: record.id,
                  revision: record.revision,
                });
                onClose();
              })
            }
          >
            Discard to Trash
          </button>
        </div>
        {locked && (
          <p className="muted">
            A copy is a new message. The original may already have been
            accepted; inspect recipients before requesting another submission.
          </p>
        )}
      </details>
      {submission && (
        <section role="status">
          <h3>{outcomeLabel[submission.state] || submission.state}</h3>
          {submission.accepted?.length > 0 && (
            <p>Accepted recipients: {submission.accepted.join(", ")}</p>
          )}
          {Object.keys(submission.rejected || {}).length > 0 && (
            <p>
              Rejected recipients: {Object.keys(submission.rejected).join(", ")}
            </p>
          )}
          <p className="muted">
            Server acceptance is not proof of delivery or reading.
          </p>
        </section>
      )}
    </section>
  );
}
