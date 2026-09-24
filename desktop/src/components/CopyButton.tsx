import { useEffect, useRef, useState } from "react";
import { Check, Copy } from "lucide-react";

/** Copies one captured visible/source payload. Success follows native completion. */
export function CopyButton({ text, label, iconOnly = false }: {
  text: string; label: string; iconOnly?: boolean;
}) {
  const [result, setResult] = useState<{text: string; status: "copied" | "error"} | null>(null);
  const epoch = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => { epoch.current++; clearTimeout(timer.current); }, []);
  const current = result?.text === text ? result.status : undefined;
  async function copy() {
    const attempt = ++epoch.current;
    clearTimeout(timer.current);
    setResult(null);
    try {
      await window.olive.copyText(text);
      if (attempt !== epoch.current) return;
      setResult({text, status: "copied"});
      timer.current = setTimeout(() => setResult(null), 1600);
    } catch {
      if (attempt === epoch.current) setResult({text, status: "error"});
    }
  }
  return <>
    <button type="button" className={iconOnly ? "icon-button" : "quiet compact"}
      aria-label={current === "copied" ? `${label} — copied` : label}
      onClick={() => void copy()}>
      {current === "copied" ? <Check size={iconOnly ? 14 : 13} aria-hidden="true" /> : <Copy size={iconOnly ? 14 : 13} aria-hidden="true" />}
      {!iconOnly && (current === "copied" ? "Copied" : "Copy")}
    </button>
    {current === "error" && <span role="alert" className="small">Could not copy to the system clipboard. Try again; very large text may exceed the copy limit.</span>}
  </>;
}
