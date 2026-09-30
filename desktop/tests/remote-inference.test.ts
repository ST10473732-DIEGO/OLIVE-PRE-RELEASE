import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { connectSchemas } from "../electron/connect-contracts";
import { schemas } from "../electron/contracts";
import { RemoteAttribution, TargetOptions, targetState, type ModelTarget } from "../src/features/chat/RemoteTarget";
import { RemoteAI } from "../src/features/devices/RemoteAI";
import { ApprovalSummary } from "../src/components/ApprovalSummary";

const target: ModelTarget = { device_id: crypto.randomUUID(), display_name: "Gaming PC", state: "online", permission: "allow", busy: false,
  presets: { fast: true, normal: true, max: true } };

describe("Remote AI presentation and narrow bridge", () => {
  it("keeps target selection separate and explicit", () => {
    const html = renderToStaticMarkup(createElement(TargetOptions, { targets: [target], preset: "max" }));
    expect(html).toContain(target.device_id);
    expect(html).toContain("Gaming PC · Online");
    expect(html).not.toContain("qwen");
    expect(html).not.toContain("Auto");
    expect(schemas["chat.run_on"].safeParse({ chat_id: crypto.randomUUID(), device_id: target.device_id }).success).toBe(true);
    expect(schemas["chat.run_on"].safeParse({ chat_id: crypto.randomUUID(), device_id: "", fallback: true }).success).toBe(false);
  });
  it("labels every unavailable state truthfully without changing the target", () => {
    expect(targetState({ ...target, state: "offline" }, "fast")).toBe("Offline");
    expect(targetState({ ...target, state: "revoked" }, "fast")).toBe("Revoked");
    expect(targetState({ ...target, permission: "deny" }, "fast")).toBe("Remote AI Off");
    expect(targetState({ ...target, permission: "ask" }, "fast")).toBe("Online · Ask");
    expect(targetState({ ...target, busy: true }, "fast")).toBe("Busy");
    expect(targetState(target, "deep")).toBe("Model unavailable");
    // Media generation modes are This device only, never offered remotely.
    for (const media of ["reimagine", "audio", "video"]) expect(targetState(target, media)).toBe("This device only");
    expect(targetState({ ...target, presets: { ...target.presets, max: false } }, "max")).toBe("Model unavailable");
  });
  it("supports Off Ask Allow without tool or provider controls", () => {
    for (const decision of ["deny", "ask", "allow"])
      expect(connectSchemas["connect.permission"].safeParse({ device_id: target.device_id, capability: "models.remote", decision }).success).toBe(true);
    for (const field of ["model", "provider_url", "tools", "approved"])
      expect(connectSchemas["connect.model_targets"].safeParse({ [field]: "untrusted" }).success).toBe(false);
    expect(connectSchemas["connect.inference_stop"].safeParse({ device_id: target.device_id, job_id: crypto.randomUUID() }).success).toBe(true);
  });
  it("retains remote attribution for visible answers and running output", () => {
    const provider = { runtime: "OLIVE Connect", preset: "max", device_name: "<script>Gaming PC</script>" };
    const complete = renderToStaticMarkup(createElement(RemoteAttribution, { provider }));
    expect(complete).toContain("Answered by");
    expect(complete).toContain("OLIVE MAX");
    expect(complete).not.toContain("<script>");
    expect(renderToStaticMarkup(createElement(RemoteAttribution, { provider, complete: false }))).toContain("Thinking on");
    expect(renderToStaticMarkup(createElement(RemoteAttribution, {}))).toBe("");
  });
  it("shows active work and Stop without prompt or hardware details", () => {
    const html = renderToStaticMarkup(createElement(RemoteAI, {
      device: { device_id: target.device_id, display_name: target.display_name, platform: "linux", device_class: "desktop",
        remote_ai: { presets: target.presets, jobs: [{ job_id: crypto.randomUUID(), preset: "fast", state: "streaming" }] } },
      refresh: async () => {},
    }));
    expect(html).toContain("Stop remote inference");
    expect(html).toContain("OLIVE FAST");
    // The stale "text-only / unavailable remotely" wording is gone; capabilities come from the backend matrix.
    expect(html).not.toContain("unavailable remotely");
    expect(html).not.toMatch(/text-only/i);
    expect(html).toContain("capabilities are unavailable right now");
    expect(html).not.toContain("GPU");
  });
  it("reuses trusted Ask with a bounded metadata preview", () => {
    const html = renderToStaticMarkup(createElement(ApprovalSummary, { approval: {
      id: "a", fingerprint: "f", summary: "Remote AI", tool_name: "connect.request", risk_level: "low", targets: [],
      arguments: { source_name: "<script>Peer</script>", inference: { preset: "normal", message_count: 2, input_bytes: 512 } },
    } }));
    expect(html).toContain("OLIVE NORMAL");
    expect(html).toContain("512");
    expect(html).toContain("saved permission stays Ask");
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("No message content or inference access");
  });
});
