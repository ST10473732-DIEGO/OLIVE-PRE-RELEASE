/* eslint-disable no-control-regex -- Deliberately removes OSC control sequences from untrusted output. */
import { useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
// The terminal follows the presentation tokens so light and dark stay coherent.
function terminalTheme() {
  const tokens = getComputedStyle(document.documentElement);
  const colour = (name: string) => tokens.getPropertyValue(name).trim();
  return {
    background: colour("--bg") || "#0c121c",
    foreground: colour("--text") || "#bdc9db",
    cursor: colour("--accent") || "#7cc4ff",
    selectionBackground: colour("--accent-glow") || "#7cc4ff44",
  };
}
export default function Output({ text }: { text: string }) {
  const target = useRef<HTMLDivElement>(null);
  const terminal = useRef<Terminal | null>(null);
  useEffect(() => {
    const term = new Terminal({
      disableStdin: true,
      convertEol: true,
      scrollback: 2000,
      fontSize: 13,
      fontFamily: '"Cascadia Mono", Consolas, monospace',
      theme: terminalTheme(),
      allowProposedApi: false,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(target.current!);
    fit.fit();
    terminal.current = term;
    const observer = new ResizeObserver(() => fit.fit());
    observer.observe(target.current!);
    // Re-read tokens when the theme attribute changes; no polling.
    const themes = new MutationObserver(() => {
      term.options.theme = terminalTheme();
    });
    themes.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => {
      observer.disconnect();
      themes.disconnect();
      terminal.current = null;
      term.dispose();
    };
  }, []);
  useEffect(() => {
    // Strip OSC sequences (clipboard/title/link commands) from untrusted output.
    const safe = text
      .slice(-150000)
      .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "");
    terminal.current?.reset();
    terminal.current?.write(safe);
  }, [text]);
  return (
    <div
      className="output-terminal"
      aria-label="Read-only program and test output"
      ref={target}
    />
  );
}
