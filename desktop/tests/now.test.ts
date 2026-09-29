import { describe, expect, it } from "vitest";
import { schemas } from "../electron/contracts";
import { messageAttribution, targetState } from "../src/features/chat/RemoteTarget";

describe("OLIVE NOW", () => {
  it("accepts the preset without renderer model overrides", () => {
    const args = {chat_id: crypto.randomUUID(), preset: "now"};
    expect(schemas["chat.preset"].safeParse(args).success).toBe(true);
    expect(schemas["chat.preset"].safeParse({...args, model: "cloud"}).success).toBe(false);
  });
  it("keeps exact model tags out of public attribution", () => {
    for (const tier of ["LIVE", "DEEP LIVE"]) {
      expect(messageAttribution({runtime: "Ollama", preset: "now", model: "private:tag", tier})).toBe(`NOW · ${tier} · This device`);
    }
  });
  it("explains remote unavailability", () => {
    expect(targetState({device_id: "fixture", display_name: "Peer", state: "online", permission: "allow", busy: false, presets: {}}, "now")).toBe("NOW unavailable remotely");
  });
});
