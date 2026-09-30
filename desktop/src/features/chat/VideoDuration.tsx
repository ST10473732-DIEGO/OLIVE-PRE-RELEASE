import { useEffect, useState } from "react";
import { Clapperboard, ImagePlay } from "lucide-react";
import { call } from "../../services/api";
import {
  DURATION_PRESETS, VIDEO_INPUT_NOTICE, durationLabel, parseCustomDuration, planLine, videoInput, type VideoPlan,
} from "./videoDuration";

/** Presentational VIDEO length control: Auto, presets or a custom length. */
export function VideoDurationView({ value, plan, images, busy, onChange }: {
  value: number | null; plan?: VideoPlan; images: number; busy: boolean; onChange: (seconds: number | null) => void;
}) {
  const custom = value !== null && !(DURATION_PRESETS as readonly number[]).includes(value);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(custom && value ? String(value) : "");
  const [unit, setUnit] = useState<"s" | "min">("s");
  const configurable = plan?.capability.duration.configurable !== false;
  const input = videoInput(images, Boolean(plan?.capability.supports_image_to_video));
  const typed = parseCustomDuration(text, unit);
  const selected = editing ? "custom" : value === null ? "auto" : custom ? "custom" : String(value);
  const auto = value === null && plan?.target_seconds !== undefined ? ` · ${durationLabel(plan.target_seconds)}` : "";
  return <div className="video-duration" role="group" aria-label="VIDEO length">
    <label className="video-duration-field">
      <Clapperboard size={13} aria-hidden="true" />
      <span>Duration</span>
      <select aria-label="Video duration" value={selected} disabled={busy || !configurable}
        onChange={(event) => {
          const next = event.target.value;
          if (next === "custom") { setEditing(true); return; }
          setEditing(false);
          onChange(next === "auto" ? null : Number(next));
        }}>
        <option value="auto">Auto{auto}</option>
        {DURATION_PRESETS.map((seconds) => <option key={seconds} value={String(seconds)}>{durationLabel(seconds)}</option>)}
        <option value="custom">{custom && value ? `Custom · ${durationLabel(value)}` : "Custom…"}</option>
      </select>
    </label>
    {editing && <form className="video-duration-custom" onSubmit={(event) => {
      event.preventDefault();
      if (typed === null) return;
      setEditing(false);
      onChange(typed);
    }}>
      <input aria-label="Custom video length" inputMode="decimal" autoFocus value={text} placeholder="e.g. 37"
        onChange={(event) => setText(event.target.value)} aria-invalid={text !== "" && typed === null} />
      <select aria-label="Custom length unit" value={unit} onChange={(event) => setUnit(event.target.value as "s" | "min")}>
        <option value="s">seconds</option>
        <option value="min">minutes</option>
      </select>
      <button type="submit" className="compact" disabled={typed === null}>Set</button>
      <button type="button" className="compact quiet" onClick={() => setEditing(false)}>Cancel</button>
    </form>}
    {input === "image" && <span className="video-input-chip"><ImagePlay size={13} aria-hidden="true" />{VIDEO_INPUT_NOTICE.image}</span>}
    <span className="video-duration-line" role="status" aria-live="polite" data-tone={plan?.error || input === "too_many" || input === "unsupported" ? "warning" : undefined}>
      {input === "too_many" || input === "unsupported" ? VIDEO_INPUT_NOTICE[input] : !configurable
        ? `This computer makes about ${durationLabel(plan?.capability.native_segment_seconds || 2)} clips; longer lengths need FFmpeg.`
        : planLine(plan)}
    </span>
  </div>;
}

/** The control with its live backend plan (debounced as the prompt changes). */
export function VideoDuration({ text, images, value, busy, onChange }: {
  text: string; images: number; value: number | null; busy: boolean; onChange: (seconds: number | null) => void;
}) {
  const [plan, setPlan] = useState<VideoPlan>();
  useEffect(() => {
    let live = true;
    const timer = setTimeout(() => {
      void call<VideoPlan>("media.video_plan", { text: text.slice(0, 4000), images, ...(value !== null ? { duration: value } : {}) })
        .then((result) => { if (live) setPlan(result); }).catch(() => undefined);
    }, 250);
    return () => { live = false; clearTimeout(timer); };
  }, [text, images, value]);
  return <VideoDurationView value={value} plan={plan} images={images} busy={busy} onChange={onChange} />;
}
