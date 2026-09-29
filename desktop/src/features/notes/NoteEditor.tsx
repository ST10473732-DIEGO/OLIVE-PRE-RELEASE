import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, X } from "lucide-react";
import { TextareaBinding, findAll } from "./binding";
import type { NoteSession, NoteSummary } from "./session";
import { countLabel } from "./notesModel";
import { displayTitle } from "./engine/text";

export function NoteEditor({
  session,
  note,
  onRename,
  onLimit,
  onTyping,
  findRequest,
  readOnly,
  autoFocus = false,
  onFocused = () => undefined,
}: {
  /** A note just created with New note: put the caret in its text. */
  autoFocus?: boolean;
  onFocused?: () => void;
  session: NoteSession;
  note: NoteSummary;
  onRename: (title: string) => void;
  onLimit: () => void;
  /** Typing keeps the note's place in the list until a pause. */
  onTyping: () => void;
  findRequest: number;
  readOnly: boolean;
}) {
  const area = useRef<HTMLTextAreaElement>(null);
  const binding = useRef<TextareaBinding | null>(null);
  const [title, setTitle] = useState(note.title);
  const [length, setLength] = useState(0);
  const [finding, setFinding] = useState(false);
  const [query, setQuery] = useState("");
  const [replacement, setReplacement] = useState("");
  const [current, setCurrent] = useState(-1);
  const [matches, setMatches] = useState(0);
  const titleTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const titleField = useRef<HTMLInputElement>(null);
  const findField = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const element = area.current;
    if (!element) return;
    const bound = new TextareaBinding(element, session, onLimit);
    binding.current = bound;
    setLength(session.text.length);
    const observe = () => setLength(session.text.length);
    session.text.observe(observe);
    return () => {
      session.text.unobserve(observe);
      bound.destroy();
      binding.current = null;
    };
    // The binding lives exactly as long as this session (onLimit is stable enough).
  }, [session]);

  useEffect(() => {
    if (document.activeElement !== titleField.current) setTitle(note.title);
  }, [note.title]);

  useEffect(() => {
    if (!autoFocus) return;
    area.current?.focus();
    onFocused();
  }, [autoFocus, onFocused]);

  useEffect(() => {
    if (!findRequest) return;
    setFinding(true);
    const selected = area.current ? area.current.value.slice(area.current.selectionStart, area.current.selectionEnd) : "";
    if (selected && !selected.includes("\n") && selected.length < 200) setQuery(selected);
    requestAnimationFrame(() => findField.current?.select());
  }, [findRequest]);

  useEffect(() => () => clearTimeout(titleTimer.current), []);

  const commitTitle = (value: string) => {
    clearTimeout(titleTimer.current);
    if (value.trim() !== note.title) onRename(value);
  };

  const reveal = (start: number, end: number) => {
    const element = area.current;
    if (!element) return;
    element.setSelectionRange(start, end);
    const lineHeight = parseFloat(getComputedStyle(element).lineHeight) || 22;
    const line = element.value.slice(0, start).split("\n").length - 1;
    element.scrollTop = Math.max(0, line * lineHeight - element.clientHeight / 3);
  };

  const step = (direction: 1 | -1) => {
    const element = area.current;
    if (!element || !query) return;
    const found = findAll(element.value, query);
    setMatches(found.length);
    if (!found.length) { setCurrent(-1); return; }
    const from = direction === 1 ? element.selectionEnd : element.selectionStart;
    let index = direction === 1 ? found.findIndex((m) => m.index >= from) : [...found].reverse().findIndex((m) => m.index + m.length <= from);
    if (direction === -1 && index >= 0) index = found.length - 1 - index;
    if (index < 0) index = direction === 1 ? 0 : found.length - 1;
    setCurrent(index);
    reveal(found[index].index, found[index].index + found[index].length);
  };

  useEffect(() => {
    if (!finding || !area.current) return;
    setMatches(query ? findAll(area.current.value, query).length : 0);
    setCurrent(-1);
  }, [query, finding, length]);

  const replaceOne = () => {
    const element = area.current;
    if (!element || !binding.current || readOnly) return;
    const selected = element.value.slice(element.selectionStart, element.selectionEnd);
    if (selected && selected.toLowerCase() === query.toLowerCase()) binding.current.replaceSelection(replacement);
    step(1);
  };

  const closeFind = () => {
    setFinding(false);
    area.current?.focus();
  };

  return (
    <div className="notes-editor">
      <div className="notes-editor-head">
        <input
          ref={titleField}
          className="notes-title-input"
          aria-label="Note title"
          placeholder={displayTitle("", session.text.toString())}
          value={title}
          maxLength={200}
          disabled={readOnly}
          onChange={(event) => {
            const value = event.target.value;
            setTitle(value);
            clearTimeout(titleTimer.current);
            titleTimer.current = setTimeout(() => commitTitle(value), 700);
          }}
          onBlur={(event) => commitTitle(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              commitTitle(title);
              area.current?.focus();
            }
          }}
        />
      </div>
      {finding && (
        <div className="notes-find" role="search" aria-label="Find in note">
          <input
            ref={findField}
            aria-label="Find"
            placeholder="Find"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") { event.preventDefault(); step(event.shiftKey ? -1 : 1); }
              if (event.key === "Escape") { event.preventDefault(); closeFind(); }
            }}
          />
          <span className="notes-find-count" aria-live="polite">
            {query ? (matches ? `${current >= 0 ? current + 1 : "–"} of ${matches}` : "No matches") : ""}
          </span>
          <button className="icon-button quiet" aria-label="Previous match" onClick={() => step(-1)} disabled={!matches}>
            <ChevronUp size={15} aria-hidden="true" />
          </button>
          <button className="icon-button quiet" aria-label="Next match" onClick={() => step(1)} disabled={!matches}>
            <ChevronDown size={15} aria-hidden="true" />
          </button>
          {!readOnly && (
            <>
              <input
                aria-label="Replace with"
                placeholder="Replace"
                value={replacement}
                onChange={(event) => setReplacement(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") { event.preventDefault(); replaceOne(); }
                  if (event.key === "Escape") { event.preventDefault(); closeFind(); }
                }}
              />
              <button className="quiet" onClick={replaceOne} disabled={!matches}>Replace</button>
              <button className="quiet" disabled={!matches}
                onClick={() => binding.current?.replaceAll(query, replacement)}>
                Replace all
              </button>
            </>
          )}
          <button className="icon-button quiet" aria-label="Close find" onClick={closeFind}>
            <X size={15} aria-hidden="true" />
          </button>
        </div>
      )}
      <textarea
        ref={area}
        className="notes-textarea"
        aria-label={`Note text: ${note.display_title}`}
        spellCheck
        readOnly={readOnly}
        onInput={onTyping}
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === "f") {
            event.preventDefault();
            event.stopPropagation();
            setFinding(true);
            requestAnimationFrame(() => findField.current?.select());
          }
        }}
      />
      <div className="notes-editor-foot" aria-live="off">
        <span>{countLabel(length)}</span>
      </div>
    </div>
  );
}
