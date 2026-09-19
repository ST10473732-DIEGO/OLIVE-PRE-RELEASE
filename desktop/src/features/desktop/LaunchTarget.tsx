import { useState } from "react";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import type { DesktopState, Operation } from "./types";

type Launch = { launch_id: string; application: string; state: string };
export default function LaunchTarget({ state, operation, busy }: {
  state?: DesktopState; operation: Operation; busy: boolean;
}) {
  const resource = useResource(() => call<Launch[]>("desktop.launches", {}), ["desktop"]);
  const [kind, setKind] = useState<"executable" | "python">("executable");
  const [selected, setSelected] = useState("");
  return <section aria-label="Target-only launch">
    <h2>Launch and attach one target</h2>
    <p>Choose local code you trust. Launch approval covers this file and process tree; inspection and input require their own permissions. No other window titles are read.</p>
    <p className="muted">Selected code runs with your account permissions, not in an execution sandbox. Use Studio isolation for untrusted generated code.</p>
    {!state?.settings.enabled && <p role="status">Desktop Control is disabled. Enable it explicitly in Control permissions before launching.</p>}
    <div className="row">
      <select aria-label="Local launch type" value={kind} onChange={e => setKind(e.target.value as typeof kind)}>
        <option value="executable">Executable</option><option value="python">Python script</option>
      </select>
      <button disabled={busy || !state?.settings.enabled} onClick={() => void operation(async () => {
        const result = await window.olive.fileAction({ action: "desktop-launch", kind }) as Launch | null;
        if(result) setSelected(result.launch_id);
        await resource.refresh();
      }, "Launch request returned. Review the target before inspection.")}>Choose and review launch</button>
    </div>
    {resource.error && <p role="alert">{resource.error}</p>}
    <div className="row">
      <select aria-label="Owned launch" value={selected} onChange={e => setSelected(e.target.value)}>
        <option value="">Select this session's launch</option>
        {(resource.data || []).map(r => <option key={r.launch_id} value={r.launch_id}>{r.application} · {r.state.replaceAll("_", " ")}</option>)}
      </select>
      <button disabled={busy || !selected || !state?.settings.enabled} onClick={() => void operation(
        () => call("desktop.attach_launch", { launch_id: selected }),
        "Owned target inspected. Select an actually observed control below.",
      )}>Attach launched target</button>
    </div>
    <p>Keyboard policy: {state?.settings.keyboard_policy || "unknown"}. Mouse policy: {state?.settings.mouse_policy || "unknown"}. Deny blocks the corresponding operation, including semantic text entry. Ask requires an action approval; this panel does not grant permission.</p>
  </section>;
}
