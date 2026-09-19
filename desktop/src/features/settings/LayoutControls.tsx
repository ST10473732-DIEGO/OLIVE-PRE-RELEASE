import { useState } from "react";
import {
  panelBounds,
  panelDefaults,
  readPanelLayout,
  savePanelLayout,
  type PanelLayout,
} from "../studio/panelLayout";

export function LayoutControls({
  resetNavigation,
}: {
  resetNavigation: () => void;
}) {
  const [value, setValue] = useState(readPanelLayout);
  const update = (next: PanelLayout) => {
    setValue(next);
    savePanelLayout(next);
  };
  return (
    <details>
      <summary>Workspace layout</summary>
      <p>
        Keyboard-accessible panel sizing. Studio applies these sizes when
        opened; smaller windows still reflow.
      </p>
      {(Object.keys(value) as (keyof PanelLayout)[]).map((key) => (
        <label className="field" key={key}>
          Studio {key} size
          <input
            aria-label={`Studio ${key} size`}
            type="range"
            step={10}
            min={panelBounds[key][0]}
            max={panelBounds[key][1]}
            value={value[key]}
            onChange={(event) => {
              const number = Number(event.target.value);
              if (
                number >= panelBounds[key][0] &&
                number <= panelBounds[key][1]
              )
                update({ ...value, [key]: number });
            }}
          />
          <output>{value[key]} px</output>
        </label>
      ))}
      <button
        onClick={() => {
          update({ ...panelDefaults });
          resetNavigation();
        }}
      >
        Reset navigation layout and size
      </button>
    </details>
  );
}
