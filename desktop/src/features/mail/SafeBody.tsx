import DOMPurify from "dompurify";
import { useMemo, useState } from "react";
import { useResource } from "../../services/useResource";
import { call } from "../../services/api";
import type { MailRecord } from "./types";

export function sanitiseMail(
  html: string,
  images: Record<string, string> = {},
) {
  const fragment = DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      "p",
      "br",
      "div",
      "span",
      "strong",
      "b",
      "em",
      "i",
      "u",
      "s",
      "ul",
      "ol",
      "li",
      "blockquote",
      "pre",
      "code",
      "h1",
      "h2",
      "h3",
      "h4",
      "table",
      "tbody",
      "thead",
      "tr",
      "td",
      "th",
      "hr",
      "img",
    ],
    ALLOWED_ATTR: ["src", "alt"],
    ALLOWED_URI_REGEXP: /^cid:/i,
    ALLOW_DATA_ATTR: false,
    ALLOW_ARIA_ATTR: false,
    RETURN_DOM_FRAGMENT: true,
  });
  for (const image of fragment.querySelectorAll("img")) {
    const src = image.getAttribute("src") || "";
    const value = src.startsWith("cid:") ? images[src.slice(4)] : "";
    if (value?.startsWith("data:image/png;base64,"))
      image.setAttribute("src", value);
    else image.remove();
  }
  const container = document.createElement("div");
  container.append(fragment);
  return (
    "<!doctype html><html><head><meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'\"><style>body{font:16px/1.6 system-ui,sans-serif;color:#142638;background:#fff;padding:12px;overflow-wrap:anywhere}pre{white-space:pre-wrap}img{max-width:100%;height:auto}table{max-width:100%;border-collapse:collapse}td,th{padding:8px;border:1px solid #ccd4df}</style></head><body>" +
    container.innerHTML +
    "</body></html>"
  );
}
export default function SafeBody({
  record,
  onLoaded,
}: {
  record: MailRecord;
  onLoaded: (record: MailRecord) => void;
}) {
  const [rich, setRich] = useState(false),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  const images = useResource(
    () =>
      call<{ images: Record<string, string> }>("mail.inline_images", {
        record_id: record.id,
      }),
    [],
    record.id + ":" + record.revision,
  );
  const markup = useMemo(
    () => sanitiseMail(record.html || "", images.data?.images),
    [record.html, images.data],
  );
  const links = useMemo(() => {
    const fragment = DOMPurify.sanitize(record.html || "", {
      ALLOWED_TAGS: ["a"],
      ALLOWED_ATTR: ["href"],
      RETURN_DOM_FRAGMENT: true,
    });
    return [
      ...new Set(
        [...fragment.querySelectorAll("a")]
          .map((a) => a.getAttribute("href") || "")
          .filter((url) => /^https?:\/\//i.test(url)),
      ),
    ].slice(0, 30);
  }, [record.html]);
  return (
    <section className="mail-message-body">
      {record.body_cached === false ? (
        <>
          <p>
            The body is not cached. Connect to fetch this message; reading does
            not mark it read.
          </p>
          <button
            disabled={loading}
            onClick={() => {
              setLoading(true);
              void call<MailRecord>("mail.fetch_body", { record_id: record.id })
                .then(onLoaded)
                .catch((e) => setError(String(e)))
                .finally(() => setLoading(false));
            }}
          >
            {loading ? "Fetching…" : "Fetch body"}
          </button>
        </>
      ) : (
        <>
          {record.html && (
            <div className="row">
              <button aria-pressed={!rich} onClick={() => setRich(false)}>
                Plain text
              </button>
              <button aria-pressed={rich} onClick={() => setRich(true)}>
                Safe formatted view
              </button>
            </div>
          )}
          {rich ? (
            // Wait for the inline attachments before drawing the message:
            // rendering first and swapping images in afterwards shows the
            // message once without its pictures and then reflows it.
            images.data || images.error ? (
              <iframe
                title="Untrusted email body"
                sandbox=""
                referrerPolicy="no-referrer"
                srcDoc={markup}
              />
            ) : (
              <p className="muted" role="status">
                Preparing the safe view…
              </p>
            )
          ) : (
            <pre className="mail-plain">
              {record.text || "No plain-text body supplied."}
            </pre>
          )}
          {record.html && (
            <p className="muted">
              Scripts, forms and remote resources are blocked.
            </p>
          )}
        </>
      )}
      {error && <p role="alert">{error}</p>}
      {!!links.length && (
        <details>
          <summary>External link destinations</summary>
          {links.map((url) => (
            <p key={url}>
              <button
                className="mail-external"
                onClick={() =>
                  void window.olive
                    .openExternal(url)
                    .catch((e) => setError(String(e)))
                }
              >
                {url}
              </button>
            </p>
          ))}
        </details>
      )}
    </section>
  );
}
