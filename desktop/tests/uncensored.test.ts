import { describe, expect, it } from "vitest";
import { schemas } from "../electron/contracts";
import { messageAttribution, targetState, type ModelTarget } from "../src/features/chat/RemoteTarget";

describe("UNCENSORED attribution", () => {
  for (const tier of ["FAST", "BALANCED", "DEEP", "CREATIVE", "MAX"]) {
    it(`shows ${tier} without requiring or exposing a raw model`, () => {
      const provider = { runtime: "Ollama", preset: "uncensored", tier };
      expect(messageAttribution(provider)).toBe(`UNCENSORED · ${tier} · This device`);
      expect(messageAttribution({ ...provider, model: "private-checkpoint:latest" })).toBe(messageAttribution(provider));
      expect(messageAttribution(JSON.parse(JSON.stringify(provider)))).toBe(messageAttribution(provider));
    });
  }
  it("does not invent a tier for older or invalid metadata", () => {
    expect(messageAttribution({ runtime: "Ollama", preset: "uncensored", model: "raw:latest" })).toBe("UNCENSORED · This device");
    expect(messageAttribution({ runtime: "Ollama", preset: "uncensored", tier: "raw:latest" })).toBe("UNCENSORED · This device");
  });
  it("accepts the preset but rejects routing overrides from the renderer", () => {
    const args = { chat_id: crypto.randomUUID(), preset: "uncensored" };
    expect(schemas["chat.preset"].safeParse(args).success).toBe(true);
    expect(schemas["chat.preset"].safeParse({ ...args, tier: "MAX", model: "raw" }).success).toBe(false);
  });
  it("is unavailable remotely and preserves other attribution", () => {
    const target: ModelTarget = { device_id: crypto.randomUUID(), display_name: "Peer", busy: false,
      state: "online", permission: "allow", presets: { fast: true, normal: true, max: true } };
    expect(targetState(target, "uncensored")).toBe("Model unavailable");
    expect(messageAttribution({ runtime: "Ollama", preset: "fast" })).toBe("OLIVE FAST · This device");
    expect(messageAttribution({ runtime: "OLIVE Connect", preset: "max", device_name: "Peer" })).toBe("Answered by Peer · OLIVE MAX");
  });
});
