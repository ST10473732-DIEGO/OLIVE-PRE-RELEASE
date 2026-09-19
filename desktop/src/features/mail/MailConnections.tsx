import { useRef, useState } from "react";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import { Sheet } from "../../components/Sheet";
import { Field, Feedback, useOperation } from "../personal/shared";
import type { Connection, Endpoint } from "./types";
import GoogleConnection from "./GoogleConnection";

const empty = {
  name: "",
  sender: "",
  username: "",
  smtp: { host: "", port: 465, tls: "tls" as const } as Endpoint | null,
  imap: null as Endpoint | null,
  sync_enabled: false,
  sent_folder: "",
  sent_copy: false,
  ca_pem: "",
};
export default function MailConnections() {
  const resource = useResource(
    () => call<{ items: Connection[] }>("mail.connections", {}),
    ["mail.changed"],
  );
  const op = useOperation(resource.refresh),
    [editing, setEditing] = useState(false),
    [selected, setSelected] = useState<Connection>(),
    [form, setForm] = useState({ ...empty }),
    [credential, setCredential] = useState<Connection>(),
    [test, setTest] =
      useState<
        Record<
          string,
          { status: string; category?: string; capabilities?: string[] }
        >
      >();
  const secret = useRef<HTMLInputElement>(null);
  const configure = (c?: Connection) => {
    setSelected(c);
    setForm(
      c
        ? {
            name: c.name,
            sender: c.sender,
            username: c.username,
            smtp: c.smtp,
            imap: c.imap,
            sync_enabled: c.sync_enabled,
            sent_folder: c.sent_folder,
            sent_copy: c.sent_copy,
            ca_pem: c.ca_pem,
          }
        : { ...empty },
    );
    setEditing(true);
  };
  return (
    <section className="mail-connections">
      <div className="row spread">
        <div>
          <h2>Mail connections</h2>
          <p className="muted">
            Optional, user-chosen servers. Local Mail works without a
            connection.
          </p>
        </div>
        <button onClick={() => configure()}>Add connection</button>
        <button onClick={() => {
          configure();
          setForm({...empty, name: "iCloud Mail", smtp: {host: "smtp.mail.me.com", port: 587, tls: "starttls"}, imap: {host: "imap.mail.me.com", port: 993, tls: "tls"}});
        }}>Add iCloud Mail</button>
      </div>
      <GoogleConnection onAuthorized={resource.refresh} />
      <details><summary>iCloud setup</summary><p>Enable two-factor authentication for your Apple Account and create an app-specific password at account.apple.com. Use your full iCloud email address as sender and username, then store the app-specific password here. Do not enter your main Apple Account password. Connection testing sends no mail.</p></details>
      <Feedback
        error={op.error || resource.error}
        notice={op.notice}
        loading={resource.loading}
      />
      {!resource.loading && !resource.data?.items.length && (
        <p>
          No mail server configured. Compose and import in Mail whenever you
          need.
        </p>
      )}
      {resource.data?.items.map((c) => (
        <article className="mail-connection" key={c.id}>
          <div className="row spread">
            <div>
              <h3>{c.name}</h3>
              <p>{c.sender || "No sending identity"}</p>
              <p className="muted">
                {c.state.replaceAll("_", " ")} · {c.smtp ? "SMTP" : ""}
                {c.smtp && c.imap ? " + " : ""}
                {c.imap ? "IMAP" : ""}
              </p>
            </div>
            <button onClick={() => configure(c)}>Edit</button>
          </div>
          <div className="row wrap">
            {c.sync_status && (
              <p>
                Last refresh: {c.sync_status.state} ·{" "}
                {c.sync_status.last_success || "No successful refresh"} ·{" "}
                {c.sync_status.mailbox}
              </p>
            )}
            {c.test_status && (
              <details>
                <summary>
                  Last connection test · configuration revision{" "}
                  {c.test_status.configuration_revision}
                </summary>
                {Object.entries(c.test_status.results).map(
                  ([protocol, result]) => (
                    <p key={protocol}>
                      {protocol.toUpperCase()}: {result.status}{" "}
                      {result.category || ""} ·{" "}
                      {result.capabilities?.join(", ")}
                    </p>
                  ),
                )}
              </details>
            )}
            {c.auth_type === "google_oauth" ? <button onClick={() => void op.run(() => call("mail.google_begin", {connection_id: c.id}), "Finish Google authorization in the system browser.")}>Reauthorize Google account</button> : <button onClick={() => setCredential(c)}>
              {c.credential_ref ? "Replace credentials" : "Store credentials"}
            </button>}
            <button
              disabled={op.busy}
              onClick={() =>
                void op.run(
                  async () =>
                    setTest(
                      await call("mail.connection_test", { record_id: c.id }),
                    ),
                  "Connection checks completed. No message was sent.",
                )
              }
            >
              Test connection
            </button>
            <button
              disabled={op.busy}
              onClick={() =>
                void op.run(
                  () =>
                    call("mail.connection_state", {
                      record_id: c.id,
                      revision: c.revision,
                      enabled: !c.enabled,
                    }),
                  c.enabled
                    ? "Disconnected. Local cache retained."
                    : "Connection enabled. No outbox content was sent.",
                )
              }
            >
              {c.enabled ? "Disconnect" : "Reconnect"}
            </button>
            <button
              disabled={!c.credential_ref || op.busy}
              onClick={() =>
                void op.run(
                  () =>
                    call("mail.connection_state", {
                      record_id: c.id,
                      revision: c.revision,
                      enabled: false,
                      remove_credentials: true,
                    }),
                  "Credentials removed; cache and native drafts retained.",
                )
              }
            >
              Remove credentials
            </button>
            <button
              disabled={c.enabled || op.busy}
              onClick={() =>
                void op.run(
                  () =>
                    call("mail.cache_remove", {
                      connection_id: c.id,
                      revision: c.revision,
                    }),
                  "Cached bodies removed; stable references and native drafts retained.",
                )
              }
            >
              Review removal of cached bodies
            </button>
          </div>
        </article>
      ))}
      {test && (
        <section aria-label="Connection test results">
          <h3>Connection test results</h3>
          {Object.entries(test).map(([name, r]) => (
            <p key={name}>
              {name.toUpperCase()}: {r.status}
              {r.category ? " · " + r.category : ""}
              {r.capabilities?.length ? " · " + r.capabilities.join(", ") : ""}
            </p>
          ))}
        </section>
      )}
      <Sheet
        open={editing}
        onOpenChange={setEditing}
        title={selected ? "Edit mail connection" : "Connect a mail server"}
        description="Only the server you configure is contacted. Certificate-validated TLS is required."
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void op.run(async () => {
              await call("mail.connection_save", {
                body: form,
                ...(selected
                  ? { record_id: selected.id, revision: selected.revision }
                  : {}),
              });
              setEditing(false);
            }, "Connection saved locally and disconnected. Store credentials if needed, then reconnect.");
          }}
        >
          {(
            [
              ["name", "Connection name"],
              ["sender", "Sending email address"],
              ["username", "Username"],
            ] as const
          ).map(([key, label]) => (
            <Field key={key} label={label}>
              <input
                value={form[key]}
                required={key === "name"}
                onChange={(e) => setForm({ ...form, [key]: e.target.value })}
              />
            </Field>
          ))}
          {(["smtp", "imap"] as const).map((protocol) => (
            <fieldset key={protocol}>
              <legend>{protocol.toUpperCase()}</legend>
              <label className="check-field">
                <input
                  type="checkbox"
                  checked={!!form[protocol]}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      [protocol]: e.target.checked
                        ? {
                            host: "",
                            port: protocol === "smtp" ? 465 : 993,
                            tls: "tls",
                          }
                        : null,
                    })
                  }
                />
                Use {protocol.toUpperCase()}
              </label>
              {form[protocol] && (
                <>
                  <Field label={`${protocol.toUpperCase()} server`}>
                    <input
                      required
                      value={form[protocol].host}
                      onChange={(e) =>
                        setForm({
                          ...form,
                          [protocol]: {
                            ...form[protocol]!,
                            host: e.target.value,
                          },
                        })
                      }
                    />
                  </Field>
                  <div className="mail-field-pair">
                    <Field label="Port">
                      <input
                        type="number"
                        min={1}
                        max={65535}
                        value={form[protocol].port}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            [protocol]: {
                              ...form[protocol]!,
                              port: Number(e.target.value),
                            },
                          })
                        }
                      />
                    </Field>
                    <Field label="Security">
                      <select
                        aria-label={`${protocol.toUpperCase()} security`}
                        value={form[protocol].tls}
                        onChange={(e) =>
                          setForm({
                            ...form,
                            [protocol]: {
                              ...form[protocol]!,
                              tls: e.target.value as Endpoint["tls"],
                            },
                          })
                        }
                      >
                        <option value="tls">TLS from connection</option>
                        <option value="starttls">Required STARTTLS</option>
                      </select>
                    </Field>
                  </div>
                </>
              )}
            </fieldset>
          ))}
          <details>
            <summary>Sync and Sent-copy preferences</summary>
            <label className="check-field">
              <input
                type="checkbox"
                checked={form.sync_enabled}
                disabled={!form.imap}
                onChange={(e) =>
                  setForm({ ...form, sync_enabled: e.target.checked })
                }
              />
              Refresh INBOX while OLIVE runs
            </label>
            <p className="muted">
              Checks at most every five minutes, in batches of 50. Existing Mail
              connect/read Allow is required for automatic refresh; Ask remains
              manual. No outbox content is sent.
            </p>
            <label className="check-field">
              <input
                type="checkbox"
                checked={form.sent_copy}
                disabled={!form.imap || !form.smtp}
                onChange={(e) =>
                  setForm({ ...form, sent_copy: e.target.checked })
                }
              />
              Use explicit client-managed Sent copies
            </label>
            <Field label="Sent mailbox">
              <input
                value={form.sent_folder}
                onChange={(e) =>
                  setForm({ ...form, sent_folder: e.target.value })
                }
              />
            </Field>
            <p className="muted">
              Leave off if your server saves its own copies. An explicit Outbox
              action can append a reviewed copy after server acceptance; a
              failed copy never resends the email.
            </p>
          </details>
          <details>
            <summary>Private server certificate authority</summary>
            <p className="muted">
              Optional PEM certificate for this connection only. Hostname and
              certificate verification remain required. No Windows trust-store
              changes.
            </p>
            <Field label="Connection-specific CA certificate (PEM)">
              <textarea
                aria-label="Connection-specific CA certificate (PEM)"
                value={form.ca_pem}
                onChange={(e) => setForm({ ...form, ca_pem: e.target.value })}
              />
            </Field>
          </details>
          <Feedback error={op.error} />
          <button className="primary" disabled={op.busy}>
            Save connection
          </button>
        </form>
      </Sheet>
      <Sheet
        open={!!credential}
        onOpenChange={(open) => {
          if (!open) {
            if (secret.current) secret.current.value = "";
            setCredential(undefined);
          }
        }}
        title="Store mail credentials"
        description="Stored in Windows Credential Manager for this profile. Ordinary mail data remains readable local data."
      >
        <form
          className="mail-credential-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!credential || !secret.current) return;
            const value = secret.current.value;
            secret.current.value = "";
            void op.run(async () => {
              await call("mail.credential_store", {
                record_id: credential.id,
                revision: credential.revision,
                secret: value,
              });
              setCredential(undefined);
            }, "Credentials stored in the Windows vault.");
          }}
        >
          <p>
            {credential?.name} · {credential?.username}
          </p>
          <Field label={credential?.imap?.host === "imap.mail.me.com" ? "Apple app-specific password" : "Password or app password"}>
            <input
              type="password"
              ref={secret}
              autoComplete="off"
              required
              maxLength={2500}
            />
          </Field>
          <Feedback error={op.error} />
          <button className="primary" disabled={op.busy}>
            Store credentials
          </button>
        </form>
      </Sheet>
    </section>
  );
}
