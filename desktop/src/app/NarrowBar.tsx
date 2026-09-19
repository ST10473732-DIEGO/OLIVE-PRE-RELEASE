import { Menu } from "lucide-react";
import { RailCore } from "../components/RailCore";
import { featureById } from "../navigation/features";

// Narrow windows hide the navigation pane, so this slim bar carries the two
// things that must never disappear: the Core (activity, and where the entrance
// hand-off lands) and a way back to navigation. It is the only header row.
export function NarrowBar({
  route,
  activity,
  state,
  detail,
  openNavigation,
  openActivity,
}: {
  route: string;
  activity: string;
  state: string;
  detail: string;
  openNavigation: () => void;
  openActivity: () => void;
}) {
  return (
    <header className="narrow-bar">
      <button
        className="icon-button"
        aria-label="Open navigation"
        title="Open navigation"
        onClick={openNavigation}
      >
        <Menu size={19} aria-hidden="true" />
      </button>
      <span className="narrow-route">{featureById(route)?.label || "OLIVE"}</span>
      <button
        className="narrow-identity activity-button"
        aria-label="OLIVE activity"
        title={`${state}${detail ? ` · ${detail}` : ""} — open activity`}
        onClick={openActivity}
      >
        <RailCore state={activity} />
      </button>
    </header>
  );
}
