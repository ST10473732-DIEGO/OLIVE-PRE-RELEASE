// Plain <textarea> <-> Y.Text binding.
//
// * Local input becomes one minimal Yjs edit (origin LOCAL, so undo tracks it).
// * Remote edits are applied with setRangeText(..., "preserve"), op by op, so
//   the caret, selection and scroll position stay on the same text instead of
//   the whole value being replaced.
// * During IME composition nothing touches the textarea; remote edits wait
//   and are merged when the composition ends.
// * Ctrl/Cmd+Z and Ctrl/Cmd+Shift+Z / Ctrl+Y use the local-only UndoManager.
import * as Y from "yjs";
import type { NoteSession } from "./session";
import { LOCAL } from "./session";
import { normalize, textDiff, tooLarge, transformIndex, type Delta } from "./engine/text";

/** The part of HTMLTextAreaElement the binding uses (tests supply a fake). */
export interface TextArea {
  value: string;
  selectionStart: number;
  selectionEnd: number;
  scrollTop: number;
  setRangeText(replacement: string, start: number, end: number, mode: "preserve"): void;
  setSelectionRange(start: number, end: number): void;
  addEventListener(type: string, listener: EventListener): void;
  removeEventListener(type: string, listener: EventListener): void;
}

export class TextareaBinding {
  private shadow: string;
  private composing = false;
  private queued: Delta[] = [];
  /** Electron's Edit menu also turns Ctrl+Z into a historyUndo input event;
   *  one keypress must undo exactly once. */
  private lastKeyHistory = 0;
  private readonly observer: (event: Y.YTextEvent, transaction: Y.Transaction) => void;

  constructor(private area: TextArea, private session: NoteSession, private onLimit: () => void = () => undefined) {
    this.shadow = session.text.toString();
    area.value = this.shadow;
    area.setSelectionRange(0, 0);
    this.observer = (event, transaction) => {
      if (transaction.origin === LOCAL) return; // Already in the textarea.
      const delta = event.delta as Delta;
      if (this.composing) {
        this.queued.push(delta);
        return;
      }
      this.applyDelta(delta, transaction.origin instanceof Y.UndoManager);
    };
    session.text.observe(this.observer);
    area.addEventListener("input", this.onInput as EventListener);
    area.addEventListener("compositionstart", this.onCompositionStart as EventListener);
    area.addEventListener("compositionend", this.onCompositionEnd as EventListener);
    area.addEventListener("keydown", this.onKeyDown as EventListener);
    area.addEventListener("beforeinput", this.onBeforeInput as EventListener);
    area.addEventListener("paste", this.onPaste as EventListener);
  }

  destroy() {
    this.session.text.unobserve(this.observer);
    this.area.removeEventListener("input", this.onInput as EventListener);
    this.area.removeEventListener("compositionstart", this.onCompositionStart as EventListener);
    this.area.removeEventListener("compositionend", this.onCompositionEnd as EventListener);
    this.area.removeEventListener("keydown", this.onKeyDown as EventListener);
    this.area.removeEventListener("beforeinput", this.onBeforeInput as EventListener);
    this.area.removeEventListener("paste", this.onPaste as EventListener);
  }

  private applyDelta(delta: Delta, moveCaret: boolean) {
    const area = this.area;
    const top = area.scrollTop;
    let position = 0;
    let caret: number | null = null;
    for (const op of delta) {
      if (op.retain !== undefined) position += op.retain;
      else if (typeof op.insert === "string") {
        area.setRangeText(op.insert, position, position, "preserve");
        position += op.insert.length;
        caret = position;
      } else if (op.delete !== undefined) {
        area.setRangeText("", position, position + op.delete, "preserve");
        caret = position;
      }
    }
    const expected = this.session.text.toString();
    if (area.value !== expected) {
      // Defensive: never leave the view diverged from the document.
      const start = Math.min(area.selectionStart, expected.length);
      const end = Math.min(area.selectionEnd, expected.length);
      area.value = expected;
      area.setSelectionRange(start, end);
    }
    this.shadow = expected;
    if (moveCaret && caret !== null) area.setSelectionRange(caret, caret);
    else area.scrollTop = top;
  }

  /** Commit the textarea's current value as one local edit. */
  private commit() {
    const value = this.area.value;
    const change = textDiff(this.shadow, value);
    if (!change) return;
    if (tooLarge(value)) {
      const caret = Math.max(0, this.area.selectionStart - (value.length - this.shadow.length));
      this.area.value = this.shadow;
      this.area.setSelectionRange(caret, caret);
      this.onLimit();
      return;
    }
    const text = this.session.text;
    const insert = normalize(change.insert);
    this.session.doc.transact(() => {
      if (change.remove) text.delete(change.index, change.remove);
      if (insert) text.insert(change.index, insert);
    }, LOCAL);
    if (insert !== change.insert) {
      const caret = change.index + insert.length;
      this.area.value = text.toString();
      this.area.setSelectionRange(caret, caret);
    }
    this.shadow = text.toString();
  }

  private onInput = () => {
    if (!this.composing) this.commit();
  };

  private onCompositionStart = () => {
    this.composing = true;
  };

  private onCompositionEnd = () => {
    this.composing = false;
    const queued = this.queued;
    this.queued = [];
    if (!queued.length) {
      this.commit();
      return;
    }
    // Remote edits arrived while composing: place the composed change where its
    // text now is, then show the merged document.
    const value = this.area.value;
    const change = textDiff(this.shadow, value);
    let caret = this.area.selectionStart;
    if (change) {
      let start = change.index;
      let end = change.index + change.remove;
      for (const delta of queued) {
        start = transformIndex(start, delta);
        end = transformIndex(end, delta);
      }
      const insert = normalize(change.insert);
      const text = this.session.text;
      this.session.doc.transact(() => {
        if (end > start) text.delete(start, end - start);
        if (insert) text.insert(start, insert);
      }, LOCAL);
      caret = start + insert.length;
    } else {
      for (const delta of queued) caret = transformIndex(caret, delta);
    }
    const top = this.area.scrollTop;
    this.area.value = this.session.text.toString();
    this.area.setSelectionRange(caret, caret);
    this.area.scrollTop = top;
    this.shadow = this.area.value;
  };

  undo() {
    if (this.composing) return;
    this.commit();
    this.session.undo.undo();
  }

  redo() {
    if (this.composing) return;
    this.session.undo.redo();
  }

  private onKeyDown = (event: KeyboardEvent) => {
    const mod = event.ctrlKey || event.metaKey;
    if (!mod || event.altKey) return;
    const key = event.key.toLowerCase();
    if (key === "z") {
      event.preventDefault();
      this.lastKeyHistory = Date.now();
      if (event.shiftKey) this.redo();
      else this.undo();
    } else if (key === "y" && !event.shiftKey) {
      event.preventDefault();
      this.lastKeyHistory = Date.now();
      this.redo();
    }
  };

  private onBeforeInput = (event: InputEvent) => {
    if (event.inputType !== "historyUndo" && event.inputType !== "historyRedo") return;
    event.preventDefault();
    if (Date.now() - this.lastKeyHistory < 250) return; // Same keypress, already handled.
    if (event.inputType === "historyUndo") this.undo();
    else this.redo();
  };

  private onPaste = (event: ClipboardEvent) => {
    // The textarea only ever inserts plain text (rich clipboard HTML is ignored).
    const pasted = event.clipboardData?.getData("text/plain") ?? "";
    const area = this.area;
    const next = area.value.slice(0, area.selectionStart) + pasted + area.value.slice(area.selectionEnd);
    if (tooLarge(next)) {
      event.preventDefault();
      this.onLimit();
    }
  };

  /** Replace the current selection (find/replace, programmatic insert). */
  replaceSelection(replacement: string) {
    const area = this.area;
    const start = area.selectionStart;
    area.setRangeText(normalize(replacement), start, area.selectionEnd, "preserve");
    area.setSelectionRange(start, start + normalize(replacement).length);
    this.commit();
  }

  /** Replace every case-insensitive occurrence as one undoable edit. */
  replaceAll(find: string, replacement: string): number {
    if (!find || this.composing) return 0;
    this.commit();
    const text = this.session.text;
    const found = findAll(text.toString(), find);
    const matches = found.map((match) => match.index);
    const lengths = new Map(found.map((match) => [match.index, match.length]));
    if (!matches.length) return 0;
    const insert = normalize(replacement);
    // One small operation per match (last first), so concurrent remote edits
    // between matches are untouched; one transaction = one undo step.
    this.session.doc.transact(() => {
      for (const index of matches.reverse()) {
        text.delete(index, lengths.get(index) ?? find.length);
        if (insert) text.insert(index, insert);
      }
    }, LOCAL);
    const top = this.area.scrollTop;
    this.area.value = text.toString();
    this.area.scrollTop = top;
    this.shadow = this.area.value;
    return matches.length;
  }
}

/** Case-insensitive literal matches, indexed in the original string (UTF-16). */
export function findAll(source: string, find: string): { index: number; length: number }[] {
  if (!find) return [];
  const pattern = new RegExp(find.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "giu");
  const found: { index: number; length: number }[] = [];
  for (const match of source.matchAll(pattern)) {
    found.push({ index: match.index ?? 0, length: match[0].length });
    if (found.length >= 10_000) break;
  }
  return found;
}
