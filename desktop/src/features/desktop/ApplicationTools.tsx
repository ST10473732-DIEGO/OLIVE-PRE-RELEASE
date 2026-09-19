import { useState } from "react";
import { call } from "../../services/api";
import { Details } from "../../components/WorkspacePage";
import type { Operation } from "./types";
export default function ApplicationTools({
  operation,
  busy,
}: {
  operation: Operation;
  busy: boolean;
}) {
  const [apps, setApps] = useState<
    { id: string; display_name: string; launch_mechanism: string }[]
  >([]);
  const [selected, setSelected] = useState("");
  const [alias, setAlias] = useState("");
  const [query, setQuery] = useState("");
  const [media, setMedia] = useState<
    { application_id: string; state: string; title: string }[]
  >([]);
  const [clipboard, setClipboard] = useState("");
  const [result, setResult] = useState<unknown>();
  return (
    <section>
      <h2>Application discovery</h2>
      <button
        disabled={busy}
        onClick={() =>
          void operation(
            async () =>
              setApps(await call("desktop.discover_applications", {})),
            "Application discovery finished.",
          )
        }
      >
        Discover applications
      </button>
      <input
        aria-label="Search discovered applications"
        placeholder="Search discovered applications"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <label className="field">
        Application
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          <option value="">Select a discovered application</option>
          {apps
            .filter((a) =>
              a.display_name.toLowerCase().includes(query.toLowerCase()),
            )
            .map((a) => (
              <option key={a.id} value={a.id}>
                {a.display_name} · {a.launch_mechanism}
              </option>
            ))}
        </select>
      </label>
      <div className="row">
        <button
          disabled={busy || !selected}
          onClick={() =>
            void operation(
              async () =>
                setResult(
                  await call("desktop.open_application", {
                    application_id: selected,
                  }),
                ),
              "Application request returned; inspect the observed result.",
            )
          }
        >
          Review opening application
        </button>
        <input
          aria-label="Application alias"
          value={alias}
          onChange={(e) => setAlias(e.target.value)}
          placeholder="Optional application alias"
        />
        <button
          disabled={busy || !selected || !alias.trim()}
          onClick={() =>
            void operation(
              () =>
                call("desktop.application_alias", {
                  application_id: selected,
                  alias,
                }),
              "Application alias saved.",
            )
          }
        >
          Save alias
        </button>
      </div>
      <details>
        <summary>System media sessions</summary>
        <button
          disabled={busy}
          onClick={() =>
            void operation(
              async () => setMedia(await call("desktop.media_sessions", {})),
              "Media sessions inspected.",
            )
          }
        >
          Inspect media sessions
        </button>
        {media.map((m) => (
          <article className="record-card" key={m.application_id}>
            <h3>{m.title || m.application_id}</h3>
            <p>{m.state}</p>
            <div className="row">
              {(["play", "pause", "next", "previous"] as const).map(
                (action) => (
                  <button
                    disabled={busy}
                    key={action}
                    onClick={() =>
                      void operation(
                        async () =>
                          setResult(
                            await call("desktop.media_action", {
                              application_id: m.application_id,
                              action,
                            }),
                          ),
                        "Media operation returned; inspect verification.",
                      )
                    }
                  >
                    {action}
                  </button>
                ),
              )}
            </div>
          </article>
        ))}
      </details>
      <details>
        <summary>Explicit clipboard operations</summary>
        <p>
          Clipboard content is read or replaced only after the existing
          permission review. Clear the preview when finished.
        </p>
        <textarea
          aria-label="Clipboard text"
          value={clipboard}
          maxLength={8192}
          rows={3}
          onChange={(e) => setClipboard(e.target.value)}
        />
        <div className="row">
          <button
            disabled={busy}
            onClick={() =>
              void operation(async () => {
                const value = await call<{ text: string }>(
                  "desktop.clipboard_action",
                  { action: "read" },
                );
                setClipboard(value.text);
              }, "Clipboard text read.")
            }
          >
            Review reading clipboard
          </button>
          <button
            disabled={busy}
            onClick={() =>
              void operation(
                () =>
                  call("desktop.clipboard_action", {
                    action: "write",
                    text: clipboard,
                  }),
                "Clipboard text replaced.",
              )
            }
          >
            Review replacing clipboard
          </button>
          <button onClick={() => setClipboard("")}>Clear preview</button>
        </div>
      </details>
      {result !== undefined && (
        <Details value={result} title="Operation result" />
      )}
    </section>
  );
}
