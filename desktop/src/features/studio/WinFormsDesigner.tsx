import {useEffect, useRef, useState, type PointerEvent as ReactPointerEvent} from "react";
import {Sheet} from "../../components/Sheet";
import {call} from "../../services/api";
import "./winforms-designer.css";

const TYPES = ["Button", "Label", "TextBox", "CheckBox", "ComboBox", "Panel", "FlowLayoutPanel", "TableLayoutPanel"] as const;
type ControlType = typeof TYPES[number];
type Control = {id: string; name: string; type: ControlType; parent: string; x: number; y: number; width: number; height: number; text: string; checked: boolean; items: string[]; dock: string; handler: string};
type Layout = {version: number; form: {text: string; width: number; height: number}; controls: Control[]};
type Design = {supported: boolean; reason?: string; layout?: Layout; revision?: string; diverged?: boolean; generated?: string; current_code?: string};
const containers = new Set(["Panel", "FlowLayoutPanel", "TableLayoutPanel"]);
const clone = <T,>(value: T): T => structuredClone(value);

export function WinFormsDesigner({workspaceId, open, onOpenChange, openCode, run}: {
  workspaceId: string; open: boolean; onOpenChange: (value: boolean) => void;
  openCode: (path: string) => Promise<void>; run: () => Promise<void>;
}) {
  const [design, setDesign] = useState<Design>();
  const [layout, setLayout] = useState<Layout>();
  const [saved, setSaved] = useState("");
  const [selection, setSelection] = useState<string[]>([]);
  const [undo, setUndo] = useState<Layout[]>([]), [redo, setRedo] = useState<Layout[]>([]);
  const [surface, setSurface] = useState("Design"), [snap, setSnap] = useState(true);
  const [error, setError] = useState(""), [busy, setBusy] = useState(false), [notice, setNotice] = useState("");
  const canvas = useRef<HTMLDivElement>(null);
  const drag = useRef<{x: number; y: number; layout: Layout; ids: string[]; resize: boolean} | null>(null);
  const dirty = !!layout && JSON.stringify(layout) !== saved;
  const selected = layout?.controls.find(c => c.id === selection[0]);
  const locked = busy || !design?.supported || design.diverged;
  const load = async () => {
    setBusy(true); setError("");
    try {
      const result = await call<Design>("designer.load", {workspace_id: workspaceId});
      setNotice("");
      setDesign(result); setLayout(result.layout); setSaved(JSON.stringify(result.layout)); setUndo([]); setRedo([]); setSelection([]);
      const raw = localStorage.getItem(`studioDesignDraft:${workspaceId}`);
      if (raw && result.supported) {
        const draft = JSON.parse(raw) as {layout: Layout; revision: string};
        setLayout(draft.layout);
        if (draft.revision !== result.revision) {
          setDesign({...result, revision: draft.revision, diverged: true, reason: "Disk layout changed while an unsaved design was retained. The draft remains visible; discard it to load disk content. Saving is blocked."});
        }
        setNotice("Restored unsaved design. Save or discard when ready.");
      }
    } catch (e) {setError(String(e));} finally {setBusy(false);}
  };
  useEffect(() => {if (open) void load();}, [open, workspaceId]);
  useEffect(() => {
    if (busy || !design?.revision || !layout) return;
    try {
      if (dirty) localStorage.setItem(`studioDesignDraft:${workspaceId}`, JSON.stringify({layout, revision: design.revision}));
      else localStorage.removeItem(`studioDesignDraft:${workspaceId}`);
    } catch {setError("Unsaved design could not be retained locally. Save before leaving Studio.");}
  }, [layout, dirty, busy, design?.revision, workspaceId]);
  const change = (next: Layout) => {
    if (!layout || locked) return;
    setUndo(u => [...u.slice(-99), clone(layout)]); setRedo([]); setLayout(next); setNotice("");
  };
  const property = (key: keyof Control, value: unknown) => {
    if (layout && selected) change({...layout, controls: layout.controls.map(c => c.id === selected.id ? {...c, [key]: value} : c)});
  };
  const quantize = (n: number) => Math.max(0, Math.round(n / (snap ? 8 : 1)) * (snap ? 8 : 1));
  const add = (type: ControlType, x = 24, y = 24, parent = "") => {
    if (!layout || locked) return;
    let index = 1; while (layout.controls.some(c => c.name === type.toLowerCase() + index)) index++;
    const id = "c" + crypto.randomUUID().replaceAll("-", "");
    const control: Control = {id, name: type.toLowerCase() + index, type, parent, x: quantize(x), y: quantize(y),
      width: containers.has(type) ? 240 : 120, height: containers.has(type) ? 160 : 32, text: type === "TextBox" ? "" : type,
      checked: false, items: [], dock: "None", handler: ""};
    change({...layout, controls: [...layout.controls, control]}); setSelection([id]);
  };
  const save = async (value = layout) => {
    if (!value || locked) throw new Error("Resolve the designer conflict before saving");
    setBusy(true); setError("");
    try {
      const result = await call<Design>("designer.save", {workspace_id: workspaceId, layout: value, revision: design?.revision});
      setDesign(result); setLayout(result.layout); setSaved(JSON.stringify(result.layout)); setNotice("Layout saved. User event code preserved.");
    } catch (e) {setError(String(e)); throw e;} finally {setBusy(false);}
  };
  const start = (e: ReactPointerEvent, c: Control, resize = false) => {
    if (locked || surface !== "Design" || !layout) return;
    e.stopPropagation(); e.preventDefault();
    const ids = e.shiftKey ? [...new Set([...selection, c.id])] : selection.includes(c.id) ? selection : [c.id];
    setSelection(ids); drag.current = {x: e.clientX, y: e.clientY, layout: clone(layout), ids, resize};
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const move = (e: ReactPointerEvent) => {
    const value = drag.current; if (!value) return;
    const dx = e.clientX - value.x, dy = e.clientY - value.y;
    setLayout({...value.layout, controls: value.layout.controls.map(c => !value.ids.includes(c.id) ? c : value.resize
      ? {...c, width: Math.min(4096, Math.max(12, quantize(c.width + dx))), height: Math.min(4096, Math.max(12, quantize(c.height + dy)))}
      : {...c, x: Math.min(4096, quantize(c.x + dx)), y: Math.min(4096, quantize(c.y + dy))})});
  };
  const finish = () => {
    if (!drag.current) return;
    const before = drag.current.layout; drag.current = null;
    setUndo(u => [...u.slice(-99), before]); setRedo([]);
  };
  const align = (key: "x" | "y") => {
    if (!layout || !selected) return;
    change({...layout, controls: layout.controls.map(c => selection.includes(c.id) && c.parent === selected.parent ? {...c, [key]: selected[key]} : c)});
  };
  const remove = () => {
    if (!layout) return;
    const removed = new Set(selection);
    for (let i = 0; i < layout.controls.length; i++) for (const c of layout.controls) if (removed.has(c.parent)) removed.add(c.id);
    change({...layout, controls: layout.controls.filter(c => !removed.has(c.id))}); setSelection([]);
  };
  const renderControls = (parent = ""): React.ReactNode => layout?.controls.filter(c => c.parent === parent).map(c =>
    <div key={c.id} className={`wf-control wf-${c.type} ${selection.includes(c.id) && surface === "Design" ? "selected" : ""}`}
      role="button" tabIndex={0} aria-label={`${c.type} ${c.name}`} data-control-id={c.id}
      style={{left: c.x, top: c.y, width: c.width, height: c.height}}
      onPointerDown={e => start(e, c)} onClick={e => e.stopPropagation()}
      onKeyDown={e => {if (e.key === "Enter") setSelection([c.id]);}}
      onDragOver={e => {if (containers.has(c.type)) e.preventDefault();}}
      onDrop={e => {
        if (!containers.has(c.type)) return;
        const type = e.dataTransfer.getData("olive-control") as ControlType;
        if (!TYPES.includes(type)) return;
        e.preventDefault(); e.stopPropagation(); const box = e.currentTarget.getBoundingClientRect(); add(type, e.clientX - box.left, e.clientY - box.top, c.id);
      }}>
      <span className="wf-caption">{c.type === "CheckBox" ? (c.checked ? "☑ " : "☐ ") : ""}{c.text}{c.type === "ComboBox" ? " ▾" : ""}</span>
      {containers.has(c.type) && renderControls(c.id)}
      {surface === "Design" && selection.includes(c.id) && <span className="wf-resize" aria-label={`Resize ${c.name}`} onPointerDown={e => start(e, c, true)} />}
    </div>);
  return <Sheet open={open} onOpenChange={value => {
    if (!value && dirty) {setNotice("Unsaved design: Save, Discard design changes, or keep editing."); return;}
    onOpenChange(value);
  }} title="Windows Forms designer" description="Native C# output. Design and Preview represent the form without executing project code.">
    <div className="winforms-designer">
      <div className="row wrap">
        {(["Design", "Code", "Preview"] as const).map(name => <button key={name} aria-pressed={surface === name} onClick={() => setSurface(name)}>{name}</button>)}
        <button disabled={locked || !dirty} onClick={() => void save().catch(() => {})}>Save design</button>
        <button disabled={!undo.length || locked} onClick={() => {if (!layout) return; setRedo(r => [...r, clone(layout)]); setLayout(undo[undo.length - 1]); setUndo(u => u.slice(0, -1));}}>Undo design</button>
        <button disabled={!redo.length || locked} onClick={() => {if (!layout) return; setUndo(u => [...u, clone(layout)]); setLayout(redo[redo.length - 1]); setRedo(r => r.slice(0, -1));}}>Redo design</button>
        <button disabled={busy} onClick={() => {localStorage.removeItem(`studioDesignDraft:${workspaceId}`); void load();}}>Discard design changes</button>
        <button disabled={locked || dirty} onClick={() => {onOpenChange(false); void run().catch(e => setError(String(e)));}}>Build and run native app</button>
      </div>
      {(error || design?.reason) && <p role="alert">{error || design?.reason}</p>}
      {notice && <p role="status">{notice}</p>}
      {design?.diverged && <div className="wf-code"><h3>Current external code (preserved)</h3><pre>{design.current_code}</pre><h3>Expected owned layout code</h3><pre>{design.generated}</pre></div>}
      {!design?.diverged && surface === "Code" && <div className="wf-code"><p>Generated layout code from the last saved design. Edit event code through the control's Properties.</p><pre>{design?.generated}</pre><button onClick={() => {if (dirty) {setNotice("Save or discard the design before opening Code."); return;} onOpenChange(false); void openCode("MainForm.cs");}}>Open form code in Monaco</button></div>}
      {layout && surface !== "Code" && <div className={`wf-layout ${surface === "Preview" ? "wf-preview" : ""}`}>
        {surface === "Design" && <aside aria-label="Control toolbox"><h3>Toolbox</h3>{TYPES.map(type => <button key={type} disabled={locked} draggable={!locked} onDragStart={e => e.dataTransfer.setData("olive-control", type)} onClick={() => add(type)}>{type}</button>)}
          <label><input type="checkbox" checked={snap} onChange={e => setSnap(e.target.checked)} />Snap to 8 px</label>
          <button disabled={selection.length < 2 || locked} onClick={() => align("x")}>Align left</button><button disabled={selection.length < 2 || locked} onClick={() => align("y")}>Align top</button>
          <button disabled={!selection.length || locked} onClick={remove}>Remove control</button>
          <h3>Hierarchy</h3><button onClick={() => setSelection([])}>Form</button>{layout.controls.map(c => <button key={c.id} aria-pressed={selection.includes(c.id)} onClick={() => setSelection([c.id])}>{c.parent ? "↳ " : ""}{c.name}</button>)}
        </aside>}
        <div className="wf-scroll"><p>{surface === "Preview" ? "Visual representation only. Use Build and run native app to execute C# events." : "Drag a toolbox control onto the form. Shift-select to align; drag a corner to resize."}</p>
          <div className="wf-title" style={{width: layout.form.width}}>{layout.form.text}</div>
          <div ref={canvas} className={`wf-canvas ${snap && surface === "Design" ? "grid" : ""}`} aria-label="Form canvas"
            style={{width: layout.form.width, height: layout.form.height}} onPointerMove={move} onPointerUp={finish} onPointerCancel={finish}
            onClick={() => setSelection([])} onDragOver={e => e.preventDefault()}
            onDrop={e => {e.preventDefault(); const type = e.dataTransfer.getData("olive-control") as ControlType; if (!TYPES.includes(type)) return; const box = e.currentTarget.getBoundingClientRect(); add(type, e.clientX - box.left, e.clientY - box.top);}}>{renderControls()}</div>
        </div>
        {surface === "Design" && <aside aria-label="Designer properties"><h3>{selected ? selected.name : "Form properties"}</h3>
          {selected ? <>
            <label>Name<input aria-label="Control name" value={selected.name} disabled={locked} onChange={e => property("name", e.target.value)} /></label>
            <label>Text<input aria-label="Control text" value={selected.text} disabled={locked} onChange={e => property("text", e.target.value)} /></label>
            {(["x", "y", "width", "height"] as const).map(key => <label key={key}>{key}<input aria-label={`Control ${key}`} type="number" value={selected[key]} disabled={locked} onChange={e => property(key, Number(e.target.value))} /></label>)}
            <label>Parent<select aria-label="Control parent" value={selected.parent} disabled={locked} onChange={e => property("parent", e.target.value)}><option value="">Form</option>{layout.controls.filter(c => c.id !== selected.id && containers.has(c.type)).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
            <label>Dock<select aria-label="Control dock" value={selected.dock} disabled={locked} onChange={e => property("dock", e.target.value)}>{["None", "Top", "Bottom", "Left", "Right", "Fill"].map(value => <option key={value}>{value}</option>)}</select></label>
            {(selected.dock !== "None" || containers.has(selected.type) || layout.controls.some(c => c.id === selected.parent && c.type !== "Panel")) && <p className="muted">The canvas shows design bounds. Native docking and flow/table arrangement are applied when the application runs.</p>}
            {selected.type === "CheckBox" && <label><input type="checkbox" checked={selected.checked} disabled={locked} onChange={e => property("checked", e.target.checked)} />Checked</label>}
            {selected.type === "ComboBox" && <label>Items, one per line<textarea aria-label="ComboBox items" value={selected.items.join("\n")} disabled={locked} onChange={e => property("items", e.target.value.split("\n"))} /></label>}
            <label>Event handler<input aria-label="Event handler" value={selected.handler} disabled={locked} onChange={e => property("handler", e.target.value)} /></label>
            <button disabled={locked || !selected.handler} onClick={() => void (async () => {try {await save(); onOpenChange(false); await openCode(`Events/${selected.handler}.cs`);} catch {/* The saved error remains visible. */}})()}>Edit event code</button>
          </> : <>
            <label>Title<input aria-label="Form title" value={layout.form.text} disabled={locked} onChange={e => change({...layout, form: {...layout.form, text: e.target.value}})} /></label>
            {(["width", "height"] as const).map(key => <label key={key}>{key}<input aria-label={`Form ${key}`} type="number" value={layout.form[key]} disabled={locked} onChange={e => change({...layout, form: {...layout.form, [key]: Number(e.target.value)}})} /></label>)}
          </>}
        </aside>}
      </div>}
    </div>
  </Sheet>;
}
