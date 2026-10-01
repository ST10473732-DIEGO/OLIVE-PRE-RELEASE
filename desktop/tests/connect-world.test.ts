import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { readFileSync } from "node:fs";

vi.mock("../src/services/api", () => ({ call: vi.fn(async () => ({})) }));

import { connectSchemas } from "../electron/connect-contracts";
import { WorldDeviceFacts, WorldPanel } from "../src/features/devices/WorldPanel";
import {
  byteLabel,
  connectionPath,
  deviceStatus,
  worldDeviceLabel,
  worldSummary,
  type Device,
  type DevicesState,
  type WorldPeer,
  type WorldStatus,
} from "../src/features/devices/types";

const ROUTE_SECRET = "769500f30dc44572ffe5d2de92dfcf5e90e4321a024988af7d8cd5f7545cd4b2";

function world(relay: string, extra: Partial<WorldStatus> = {}): WorldStatus {
  return { name: "OLIVE Connect World", protocol: "olive-world/1", enabled: relay !== "off", relay,
    relay_host: relay === "not_configured" ? null : "relay.example.com", relay_custom: true, managed: false,
    error: null, dev: false, ...extra };
}
function peer(extra: Partial<WorldPeer> = {}): WorldPeer {
  return { provisioned: true, confirmed: true, revoked: false, route: "registered", error: null, connected: false,
    last_connected_at: null, reconnects: 0, bytes_in: 0, bytes_out: 0, ...extra };
}
function device(connection: string | null, extra: Partial<Device> = {}): Device {
  return { device_id: crypto.randomUUID(), display_name: "iPhone", device_class: "phone", platform: "ios",
    trust_state: "paired", live: { state: connection ? "online" : "offline", error: null, encrypted: !!connection,
      connection, latency_ms: 1.5 }, ...extra };
}
function state(w: WorldStatus | undefined): DevicesState {
  return { local: device(null), devices: [], capabilities: [], interfaces: [], interface_error: null,
    protocol: "olive-connect/1", network: { state: "on", error: null, interface: null, port: 1, discovery: false },
    nearby: [], activity: [], world: w };
}
const render = (w: WorldStatus | undefined) =>
  renderToStaticMarkup(createElement(WorldPanel, { data: state(w), act: () => undefined }));

describe("OLIVE Connect World on the desktop", () => {
  it("names the feature OLIVE Connect World and never Cloud/Anywhere", () => {
    const html = render(world("connected"));
    expect(html).toContain("OLIVE Connect World");
    expect(html).toContain("Reach this computer securely when you’re away from your local network.");
    for (const banned of ["Connect Anywhere", "Remote Connect", "Cloud Connect", "Cloud"])
      expect(html).not.toContain(banned);
    const source = readFileSync("src/features/devices/WorldPanel.tsx", "utf8");
    expect(source).not.toMatch(/Connect Anywhere|Cloud Connect|Remote Connect/);
  });
  it("shows a truthful Direct / World badge only for authenticated channels", () => {
    expect(deviceStatus(device("local"))).toBe("Connected · Direct");
    expect(deviceStatus(device("world"))).toBe("Connected · World");
    expect(connectionPath(device("world"))).toBe("World");
    expect(deviceStatus(device(null))).toBe("Offline");
    const unauthenticated = device("world");
    unauthenticated.live!.encrypted = false;
    expect(deviceStatus(unauthenticated)).toBe("Offline");
    expect(deviceStatus(device("world", { trust_state: "revoked" }))).toBe("Revoked");
    expect(deviceStatus(device("world"))).not.toContain("Cloud");
  });
  it("describes the toggle and every relay state in plain words", () => {
    expect(render(world("off"))).toContain("Paired devices connect on your local network only.");
    expect(render(world("off"))).not.toContain("checked=\"\"");
    expect(render(world("connected"))).toContain("checked=\"\"");
    expect(worldSummary(world("connected")).label).toBe("Ready");
    expect(worldSummary(world("idle")).label).toBe("Ready");
    expect(worldSummary(world("not_configured")).label).toBe("Relay not configured");
    expect(render(world("not_configured"))).toContain("Relay not configured");
    expect(worldSummary(world("unavailable")).label).toBe("Relay unavailable");
    expect(worldSummary(world("unavailable")).detail).toContain("Local connections still work");
    expect(worldSummary(world("connecting")).label).toBe("Connecting…");
    expect(worldSummary(world("conflict")).tone).toBe("error");
    expect(worldSummary(world("connect_off")).detail).toContain("Turn on OLIVE Connect");
  });
  it("keeps relay presence separate from phone presence and shows provisioning", () => {
    const status = world("connected");
    expect(worldDeviceLabel(null, status)).toBe("Not set up yet");
    expect(worldDeviceLabel(peer({ provisioned: false, confirmed: false }), status)).toBe("Not set up yet");
    expect(worldDeviceLabel(peer({ confirmed: false }), status)).toBe("Setting up this device…");
    expect(worldDeviceLabel(peer(), status)).toBe("Ready");
    expect(worldDeviceLabel(peer({ connected: true }), status)).toBe("Connected · World");
    expect(worldDeviceLabel(peer({ revoked: true }), status)).toBe("Revoked");
    expect(worldDeviceLabel(peer(), world("unavailable"))).toBe("Relay unavailable");
  });
  it("never displays route secrets, tokens or raw keys", () => {
    const leaky = { ...peer(), route_secret: ROUTE_SECRET } as unknown as WorldPeer;
    const d = device("world", { world: leaky });
    const html = renderToStaticMarkup(createElement(WorldDeviceFacts, { device: d, data: state(world("connected")), act: () => undefined }))
      + render({ ...world("connected"), route_secret: ROUTE_SECRET } as unknown as WorldStatus);
    expect(html).not.toContain(ROUTE_SECRET);
    expect(html).not.toMatch(/token|secret|credential|private key/i);
    expect(html).toContain("relay.example.com");
  });
  it("hides itself for an older backend and for revoked devices", () => {
    expect(render(undefined)).toBe("");
    const revoked = device(null, { trust_state: "revoked", world: peer({ revoked: true }) });
    expect(renderToStaticMarkup(createElement(WorldDeviceFacts, { device: revoked, data: state(world("connected")), act: () => undefined }))).toBe("");
    expect(renderToStaticMarkup(createElement(WorldDeviceFacts, { device: device("local"), data: state(undefined), act: () => undefined }))).toBe("");
  });
  it("offers rotation only for a provisioned device and formats counters", () => {
    const html = renderToStaticMarkup(createElement(WorldDeviceFacts, {
      device: device("world", { world: peer({ connected: true, bytes_in: 1536, bytes_out: 3 * 1024 * 1024 }) }),
      data: state(world("connected")), act: () => undefined }));
    expect(html).toContain("Rotate World route");
    expect(html).toContain("1.5 KB in · 3.0 MB out");
    expect(byteLabel(5)).toBe("5 B");
  });
  it("validates World bridge arguments strictly", () => {
    expect(connectSchemas["connect.world_set"].safeParse({ enabled: true }).success).toBe(true);
    expect(connectSchemas["connect.world_set"].safeParse({ enabled: "yes" }).success).toBe(false);
    expect(connectSchemas["connect.world_relay"].safeParse({ url: "wss://relay.example.com" }).success).toBe(true);
    expect(connectSchemas["connect.world_relay"].safeParse({}).success).toBe(true);
    for (const url of ["https://x", "wss://a b", "", "wss://" + "a".repeat(300)])
      expect(connectSchemas["connect.world_relay"].safeParse({ url }).success).toBe(false);
    expect(connectSchemas["connect.world_relay"].safeParse({ url: "wss://x", token: "t" }).success).toBe(false);
    expect(connectSchemas["connect.world_rotate"].safeParse({ device_id: crypto.randomUUID() }).success).toBe(true);
    expect(connectSchemas["connect.world_rotate"].safeParse({ device_id: "x" }).success).toBe(false);
  });
});
