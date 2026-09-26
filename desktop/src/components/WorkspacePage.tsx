import { useContext, type ReactNode } from "react";
import { SpacePortal, SpaceSlot } from "./SpaceHeader";
import "../design/workspace.css";
import "../design/pages.css";

/* Every feature page shares one frame: a header band (mark, title, one line
   of context, status pill, grouped actions) over a body. Two body layouts:
   - "flow": a centred scrolling column of panels (default; the older pages
     that have not been restructured keep their `.page-body` behaviour), and
   - "fill": a full-height row — optional rail on the left, main in the
     middle, optional side panel on the right — for list/detail workspaces.
   The OLIVE GO material (workspace.css) is what the classes resolve to. */
export function WorkspacePage({
  title,
  description,
  actions,
  children,
  className = "",
  layout = "legacy",
  icon,
  status,
  statusTone,
  rail,
  side,
  toolbar,
  bare = false,
}: {
  /** No header band: the page draws its own identity (Grove Mail, Chat). The
   *  title stays as an accessible heading. */
  bare?: boolean;
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  layout?: "legacy" | "flow" | "fill";
  icon?: ReactNode;
  status?: ReactNode;
  statusTone?: "live" | "warning" | "error" | "success" | "idle";
  rail?: ReactNode;
  side?: ReactNode;
  toolbar?: ReactNode;
}) {
  // Inside a multi-view space the space header shows the title and tabs; this
  // view keeps an accessible heading and hands its status and actions over.
  const space = useContext(SpaceSlot);
  const handed = space && (
    <SpacePortal target={space.target} active={space.active}>
      {status && (
        <span className="ws-head-status" data-tone={statusTone ?? "idle"} role="status">
          {status}
        </span>
      )}
      {actions}
    </SpacePortal>
  );
  if (layout === "legacy") {
    return (
      <main className={`feature-page ${space ? "in-space" : ""} ${className}`.trim()}>
        {space ? (
          <>
            <h1 className="sr-only">{title}</h1>
            {handed}
          </>
        ) : (
          <header className="page-header">
            <div>
              <h1>{title}</h1>
              {description && <p>{description}</p>}
            </div>
            {actions && <div className="row page-actions">{actions}</div>}
          </header>
        )}
        <div className="page-body">{children}</div>
      </main>
    );
  }
  return (
    <main className={`feature-page ws ${layout} ${space ? "in-space" : ""} ${className}`.trim()}>
      {space || bare ? (
        <>
          <h1 className="sr-only">{title}</h1>
          {handed}
        </>
      ) : (
        <header className="page-header ws-head">
          {icon && <span className="ws-head-mark" aria-hidden="true">{icon}</span>}
          <div className="ws-head-text">
            <h1>{title}</h1>
            {description && <p>{description}</p>}
          </div>
          {status && (
            <span className="ws-head-status" data-tone={statusTone ?? "idle"} role="status">
              {status}
            </span>
          )}
          {actions && <div className="row page-actions ws-actions">{actions}</div>}
        </header>
      )}
      {toolbar && <div className="ws-toolbar">{toolbar}</div>}
      {layout === "fill" ? (
        <div className="ws-body">
          {rail}
          {children}
          {side}
        </div>
      ) : (
        <div className="ws-body">{children}</div>
      )}
    </main>
  );
}

/* Left navigation column of a "fill" page. */
export function Rail({
  title,
  actions,
  children,
  foot,
  wide,
  className = "",
  label,
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  foot?: ReactNode;
  wide?: boolean;
  className?: string;
  label?: string;
}) {
  return (
    <aside className={`ws-rail ${wide ? "wide" : ""} ${className}`.trim()} aria-label={label ?? title}>
      {(title || actions) && (
        <div className="ws-rail-head">
          {title && <h2>{title}</h2>}
          {actions}
        </div>
      )}
      <div className="ws-rail-scroll">{children}</div>
      {foot && <div className="ws-rail-foot">{foot}</div>}
    </aside>
  );
}

/* Right detail column of a "fill" page. */
export function Side({
  title,
  actions,
  children,
  wide,
  always,
  className = "",
  label,
  as: Tag = "aside",
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  wide?: boolean;
  always?: boolean;
  className?: string;
  label?: string;
  as?: "aside" | "section";
}) {
  return (
    <Tag className={`ws-side ${wide ? "wide" : ""} ${always ? "always" : ""} ${className}`.trim()} aria-label={label}>
      {(title || actions) && (
        <div className="ws-side-head">
          {title && <h2>{title}</h2>}
          {actions}
        </div>
      )}
      <div className="ws-side-body">{children}</div>
    </Tag>
  );
}

/* Main column of a "fill" page. Scrolls itself; `pad` adds the page gutter. */
export function Main({
  children,
  pad = true,
  scroll = true,
  className = "",
  label,
  as: Tag = "section",
}: {
  children: ReactNode;
  pad?: boolean;
  scroll?: boolean;
  className?: string;
  label?: string;
  as?: "section" | "div";
}) {
  return (
    <Tag className={`ws-main ${pad ? "pad" : ""} ${scroll ? "scroll" : ""} ${className}`.trim()} aria-label={label}>
      {children}
    </Tag>
  );
}

/* A raised surface with an optional head (icon, title, sub-line, actions). */
export function Panel({
  title,
  sub,
  icon,
  actions,
  children,
  foot,
  tone,
  raised,
  tight,
  flush,
  className = "",
  as: Tag = "section",
  headingLevel = 2,
  label,
}: {
  title?: ReactNode;
  sub?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  foot?: ReactNode;
  tone?: "warning" | "error" | "accent";
  raised?: boolean;
  tight?: boolean;
  flush?: boolean;
  className?: string;
  as?: "section" | "article" | "div" | "aside";
  headingLevel?: 2 | 3;
  label?: string;
}) {
  const H = headingLevel === 3 ? "h3" : "h2";
  return (
    <Tag
      className={`ws-panel ${tone ? `tone-${tone}` : ""} ${raised ? "raised" : ""} ${className}`.trim()}
      aria-label={label}
    >
      {(title || actions) && (
        <div className="ws-panel-head">
          {icon && <span className="ws-panel-icon" aria-hidden="true">{icon}</span>}
          <div className="ws-title">
            {title && <H>{title}</H>}
            {sub && <p>{sub}</p>}
          </div>
          {actions && <div className="ws-panel-actions">{actions}</div>}
        </div>
      )}
      {children !== undefined && (
        <div className={`ws-panel-body ${tight ? "tight" : ""} ${flush ? "flush" : ""}`.trim()}>{children}</div>
      )}
      {foot && <div className="ws-panel-foot">{foot}</div>}
    </Tag>
  );
}

/* Eyebrow + optional trailing control above a group of things. */
export function SectionHead({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="ws-section-head">
      <p className="ws-eyebrow">{children}</p>
      {action}
    </div>
  );
}

/* A designed empty state: icon tile, one heading, one sentence, actions. */
export function EmptyState({
  icon,
  title,
  children,
  actions,
  compact,
  className = "",
  headingLevel = 2,
}: {
  icon?: ReactNode;
  title: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  compact?: boolean;
  className?: string;
  headingLevel?: 2 | 3;
}) {
  const H = headingLevel === 3 ? "h3" : "h2";
  return (
    <div className={`ws-empty ${compact ? "compact" : ""} ${className}`.trim()}>
      {icon && <span className="ws-empty-icon" aria-hidden="true">{icon}</span>}
      <H>{title}</H>
      {children && <p>{children}</p>}
      {actions && <div className="ws-empty-actions">{actions}</div>}
    </div>
  );
}

/* Segmented control. Buttons carry aria-pressed so tests keep their handle. */
export function Seg<T extends string>({
  value,
  options,
  onChange,
  vertical,
  label,
  className = "",
}: {
  value: T;
  options: { value: T; label: ReactNode; count?: number | string; icon?: ReactNode; title?: string }[];
  onChange: (value: T) => void;
  vertical?: boolean;
  label?: string;
  className?: string;
}) {
  return (
    <div className={`ws-seg ${vertical ? "vertical" : ""} ${className}`.trim()} role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          title={option.title}
        >
          {option.icon}
          {option.label}
          {option.count !== undefined && <span className="count" aria-hidden="true">{option.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Pill({
  tone,
  children,
  className = "",
}: {
  tone?: "success" | "warning" | "error" | "accent" | "olive";
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={`ws-pill badge ${className}`.trim()} data-tone={tone}>
      {children}
    </span>
  );
}

/* Inline notice with a tone; renders nothing without a message. */
export function Notice({
  tone,
  icon,
  children,
  actions,
  role = "status",
  className = "",
}: {
  tone?: "warning" | "error" | "accent";
  icon?: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  role?: "status" | "alert" | "note";
  className?: string;
}) {
  if (!children) return null;
  return (
    <div className={`ws-notice ${className}`.trim()} data-tone={tone} role={role === "note" ? undefined : role}>
      {icon}
      <div className="grow">{typeof children === "string" ? <p>{children}</p> : children}</div>
      {actions}
    </div>
  );
}

export function Facts({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="ws-facts">
      {items.map(([term, value], index) => (
        <div key={index} style={{ display: "contents" }}>
          <dt>{term}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/* Collapsed group of secondary material (developer details, maintenance). */
export function Disclosure({
  summary,
  badge,
  children,
  open,
  className = "",
  onToggle,
}: {
  summary: ReactNode;
  badge?: ReactNode;
  children: ReactNode;
  open?: boolean;
  className?: string;
  onToggle?: (open: boolean) => void;
}) {
  return (
    <details
      className={`ws-disclosure ${className}`.trim()}
      open={open}
      onToggle={onToggle ? (event) => onToggle((event.currentTarget as HTMLDetailsElement).open) : undefined}
    >
      <summary>
        {summary}
        {badge}
      </summary>
      <div className="ws-disclosure-body">{children}</div>
    </details>
  );
}

/* Pagination foot shared by every list. */
export function Pager({
  page,
  pages,
  onPrevious,
  onNext,
  total,
  noun,
}: {
  page: number;
  pages: number;
  onPrevious: () => void;
  onNext: () => void;
  total?: number;
  noun?: string;
}) {
  if (pages <= 1 && !total) return null;
  return (
    <div className="ws-pager">
      <span>
        {total !== undefined && noun ? `${total} ${noun}${total === 1 ? "" : "s"}` : ""}
        {pages > 1 ? `${total !== undefined ? " · " : ""}Page ${page} of ${pages}` : ""}
      </span>
      {pages > 1 && (
        <span className="ws-pager-buttons">
          <button type="button" className="quiet" disabled={page <= 1} onClick={onPrevious}>
            Previous
          </button>
          <button type="button" className="quiet" disabled={page >= pages} onClick={onNext}>
            Next
          </button>
        </span>
      )}
    </div>
  );
}

export function Details({
  value,
  title = "Technical details",
}: {
  value: unknown;
  title?: string;
}) {
  return (
    <details className="technical-details">
      <summary>{title}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
