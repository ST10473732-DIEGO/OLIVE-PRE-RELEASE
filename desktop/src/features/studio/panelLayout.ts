// Studio V2 sizes: "explorer" is the primary sidebar width, "assistant" the
// OLIVE sidebar width and "output" the bottom panel height. The key names are
// kept so layouts saved before V2 keep working.
export const panelDefaults = { explorer: 256, assistant: 340, output: 236 };
export type PanelLayout = typeof panelDefaults;
export const panelBounds = {
  // The sidebar keeps its pre-V2 150 px minimum (V2 suggests 200); saved
  // layouts and the keyboard slider in Settings keep their meaning.
  explorer: [150, 480],
  assistant: [300, 520],
  output: [100, 900],
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
