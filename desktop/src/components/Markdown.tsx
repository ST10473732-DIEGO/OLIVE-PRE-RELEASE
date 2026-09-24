import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { isValidElement, type ReactNode } from "react";
import { CopyButton } from "./CopyButton";

function textOf(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement<{ children?: ReactNode }>(node)) return textOf(node.props.children);
  return "";
}

// V2 code block: a header with the language and Copy. Copy only reads the
// block's own text; nothing is executed or opened.
function CodeBlock({ children }: { children?: ReactNode }) {
  const code = Array.isArray(children) ? children[0] : children;
  const className = isValidElement<{ className?: string }>(code) ? code.props.className || "" : "";
  const language = /language-([\w+#.-]+)/.exec(className)?.[1] || "text";
  return (
    <div className="code-block">
      <div className="code-block-head">
        <span>{language}</span>
        <CopyButton text={textOf(children)} label={`Copy ${language} code`} />
      </div>
      <pre>{children}</pre>
    </div>
  );
}
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
        pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
        img: ({ alt }) => (
          <span className="muted">[Image blocked{alt ? `: ${alt}` : ""}]</span>
        ),
      }}
    >
      {text}
    </ReactMarkdown>
  );
}
