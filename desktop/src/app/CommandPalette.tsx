import * as Dialog from "@radix-ui/react-dialog";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import {
  collectItems,
  highlightRange,
  onPaletteProvidersChanged,
  PALETTE_MODES,
  parseQuery,
  type PaletteItem,
} from "./commands";

// V2 command palette: a raised overlay under the title bar. Keyboard-first:
// ↑/↓ move, Enter runs, Esc closes; the input keeps focus throughout. Rows are
// buttons so every command has a stable accessible name ("Open Settings").
export function CommandPalette({
  open,
  onOpenChange,
  query,
  setQuery,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  query: string;
  setQuery: (value: string) => void;
}) {
  const [items, setItems] = useState<PaletteItem[]>([]);
  const [active, setActive] = useState(0);
  const [revision, setRevision] = useState(0);
  const list = useRef<HTMLDivElement>(null);
  const { mode, text } = parseQuery(query);
  useEffect(() => onPaletteProvidersChanged(() => setRevision((value) => value + 1)), []);
  useEffect(() => {
    if (!open) return;
    let live = true;
    void collectItems(query).then((result) => {
      if (!live) return;
      setItems(result.items);
      setActive(0);
    });
    return () => {
      live = false;
    };
  }, [open, query, revision]);
  useEffect(() => {
    list.current
      ?.querySelector<HTMLElement>(`[data-index="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active]);
  const run = (item: PaletteItem | undefined) => {
    if (!item || item.unavailable) return;
    onOpenChange(false);
    void Promise.resolve(item.run()).catch(() => undefined);
  };
  const modeLabel = useMemo(() => PALETTE_MODES.find((m) => m.prefix === mode)?.hint || "", [mode]);
  const activeId = items[active] ? `palette-item-${active}` : undefined;
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="palette-scrim" />
        <Dialog.Content className="palette" aria-describedby={undefined}>
          <Dialog.Title className="sr-only">Commands</Dialog.Title>
          <label className="palette-input">
            <Search size={15} aria-hidden="true" />
            <input
              aria-label="Search commands"
              aria-controls="palette-results"
              aria-activedescendant={activeId}
              value={query}
              placeholder="Search spaces and commands · > commands · : line · @ symbols"
              autoFocus
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setActive((value) => Math.min(items.length - 1, value + 1));
                } else if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setActive((value) => Math.max(0, value - 1));
                } else if (e.key === "Home" && e.ctrlKey) {
                  setActive(0);
                } else if (e.key === "End" && e.ctrlKey) {
                  setActive(items.length - 1);
                } else if (e.key === "Enter") {
                  e.preventDefault();
                  run(items[active]);
                }
              }}
            />
          </label>
          <div className="palette-results" id="palette-results" ref={list}>
            {items.map((item, index) => {
              return (
                <Fragment key={item.id}>
                  {(index === 0 || items[index - 1].group !== item.group) && (
                    <span className="palette-group" aria-hidden="true">
                      {item.group}
                    </span>
                  )}
                  <PaletteRow item={item} index={index} active={index === active} query={text} onHover={() => setActive(index)} onRun={() => run(item)} />
                </Fragment>
              );
            })}
            {items.length === 0 && (
              <p className="palette-empty" role="status">
                {mode === ""
                  ? "Nothing matches. The palette only lists what OLIVE can do today."
                  : `No ${modeLabel.toLowerCase()} match. The palette only lists what OLIVE can do today.`}
              </p>
            )}
          </div>
          <div className="palette-foot" aria-hidden="true">
            <span><kbd className="kbd">↑</kbd><kbd className="kbd">↓</kbd> move</span>
            <span><kbd className="kbd">Enter</kbd> run</span>
            <span><kbd className="kbd">&gt;</kbd> commands</span>
            <span><kbd className="kbd">:</kbd> line</span>
            <span><kbd className="kbd">@</kbd> symbols</span>
            <span><kbd className="kbd">#</kbd> workspace symbols</span>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** One palette row. Its accessible name is the command alone; the detail,
 *  keybinding and any unavailability reason are its description. */
export function PaletteRow({
  item,
  index,
  active,
  query,
  onHover,
  onRun,
}: {
  item: PaletteItem;
  index: number;
  active: boolean;
  query: string;
  onHover: () => void;
  onRun: () => void;
}) {
  const range = highlightRange(item.title, query);
  return (
    <button
      id={`palette-item-${index}`}
      data-index={index}
      className="palette-row"
      data-active={active || undefined}
      aria-current={active ? "true" : undefined}
      aria-label={item.title}
      aria-description={[item.unavailable, item.detail, item.keys].filter(Boolean).join(" · ") || undefined}
      aria-disabled={item.unavailable ? "true" : undefined}
      title={item.unavailable || item.detail || undefined}
      tabIndex={-1}
      onMouseMove={onHover}
      onClick={onRun}
    >
      <span className="palette-title">
        {range ? (
          <>
            {item.title.slice(0, range[0])}
            <mark>{item.title.slice(range[0], range[1])}</mark>
            {item.title.slice(range[1])}
          </>
        ) : (
          item.title
        )}
      </span>
      {item.unavailable ? (
        <span className="palette-detail">{item.unavailable}</span>
      ) : (
        item.detail && <span className="palette-detail">{item.detail}</span>
      )}
      {item.keys && <kbd className="kbd">{item.keys}</kbd>}
    </button>
  );
}
