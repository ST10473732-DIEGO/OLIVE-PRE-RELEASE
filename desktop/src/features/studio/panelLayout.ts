import { useEffect, useRef } from "react";

// "output" is the tool dock's height (Terminal, Problems, Tests, Output, Git,
// Debug); the key is kept so saved layouts keep working.
export const panelDefaults = { explorer: 230, assistant: 300, output: 240 };
export type PanelLayout = typeof panelDefaults;
export const panelBounds = {
  explorer: [150, 480],
  assistant: [220, 520],
  output: [110, 600],
} as const;
const storageKey = "studioPanelLayout";
export function readPanelLayout(): PanelLayout {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || "{}");
    return Object.fromEntries(
      Object.entries(panelDefaults).map(([key, fallback]) => {
        const [min, max] = panelBounds[key as keyof PanelLayout];
        return [
          key,
          typeof saved[key] === "number" &&
          saved[key] >= min &&
          saved[key] <= max
            ? saved[key]
            : fallback,
        ];
      }),
    ) as PanelLayout;
  } catch {
    return { ...panelDefaults };
  }
}
export function savePanelLayout(value: PanelLayout) {
  localStorage.setItem(storageKey, JSON.stringify(value));
}
export function usePanelLayout(open: boolean) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!root.current || !open) return;
    const saved = readPanelLayout();
    const panels = [
      ["explorer", ".explorer", "width"],
      ["assistant", ".studio-assistant", "width"],
      ["output", ".studio-dock", "height"],
    ] as const;
    const elements = panels.map(([key, selector, dimension]) => {
      const element = root.current!.querySelector<HTMLElement>(selector);
      if (element) element.style[dimension] = `${saved[key]}px`;
      return { key, dimension, element };
    });
    const observer = new ResizeObserver(() => {
      const next = readPanelLayout();
      for (const { key, dimension, element } of elements) {
        const value = Number.parseFloat(element?.style[dimension] || "");
        if (Number.isFinite(value))
          next[key] = Math.max(
            panelBounds[key][0],
            Math.min(panelBounds[key][1], value),
          );
      }
      savePanelLayout(next);
    });
    for (const { element } of elements) if (element) observer.observe(element);
    return () => observer.disconnect();
  }, [open]);
  return root;
}
