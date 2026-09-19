import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
export function Markdown({
  text,
  onLink,
}: {
  text: string;
  onLink?: (url: string) => void;
}) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children }) => (
          <button
            className="inline-link"
            onClick={() => {
              if (href) {
                if (onLink) onLink(href);
                else void window.olive.openExternal(href);
              }
            }}
          >
            {children}
          </button>
        ),
        img: ({ alt }) => (
          <span className="muted">[Image blocked{alt ? `: ${alt}` : ""}]</span>
        ),
      }}
    >
      {text}
    </ReactMarkdown>
  );
}
