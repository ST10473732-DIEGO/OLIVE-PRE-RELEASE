import type { Message } from "../../services/api";
type Source = Message["sources"][number];

export function sourceGroup(source: Source): string {
  return source.kind === "document_excerpt" ? "Document evidence" : source.url ? "Public web evidence" : "Sources";
}

export function SourceChips({sources, inspect}: {sources: Source[]; inspect: (source: Source) => void}) {
  return <>{[...new Set(sources.map(sourceGroup))].map(group => <div key={group} aria-label={group}>
    <span className="small">{group}</span>
    <div className="chips">{sources.filter(s => sourceGroup(s) === group).map((source, index) => <button
      className="chip" key={index} onClick={() => inspect(source)}
      title={[source.title, source.kind === "current_snapshot" && "Current page snapshot", source.published_at ? `Published ${source.published_at}` : source.kind === "current_snapshot" && "Publication date unavailable", source.retrieved_at && `Retrieved ${source.retrieved_at}`].filter(Boolean).join(" · ")}>
      {source.label || source.name || `Source ${index + 1}`}
    </button>)}</div>
  </div>)}</>;
}

export function SourceEvidence({source}: {source: unknown}) {
  if (!source || typeof source !== "object") return null;
  const value = source as Source;
  return <>
    {value.title && <p><strong>{value.title}</strong></p>}
    {value.source && <p>{value.source}</p>}
    {value.kind === "current_snapshot" && <p className="small">Current page snapshot — what this page showed when retrieved.</p>}
    {value.kind === "current_snapshot" && !value.published_at && <p className="small">Publication date unavailable</p>}
    {value.published_at && <p className="small">Published {value.published_at}</p>}
    {value.retrieved_at && <p className="small">Retrieved {value.retrieved_at}</p>}
    {value.url && /^https?:\/\//i.test(value.url) && <button className="inline-link" onClick={() => void window.olive.openExternal(value.url!)}>Open original source</button>}
    {value.kind === "search_snippet" && <p className="small">Search snippet only; the page excerpt was not read.</p>}
    {value.evidence && <blockquote style={{whiteSpace: "pre-wrap"}}>{value.evidence}</blockquote>}
  </>;
}
