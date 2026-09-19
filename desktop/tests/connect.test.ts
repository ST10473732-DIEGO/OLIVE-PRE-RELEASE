import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { QRCodeSVG } from "qrcode.react";
import { connectSchemas } from "../electron/connect-contracts";
import { features, searchFeatures } from "../src/navigation/features";
import {
  deviceStatus,
  permissionGroups,
  type Device,
} from "../src/features/devices/types";
import { ApprovalSummary } from "../src/components/ApprovalSummary";

describe("Devices contracts and truthful presentation", () => {
  it("has one primary route and discoverable aliases", () => {
    expect(features.filter((f) => f.id === "devices")).toHaveLength(1);
    expect(features.find((f) => f.id === "devices")?.primary).toBe(true);
    for (const alias of ["devices", "connect", "pair", "paired devices"])
      expect(searchFeatures(alias).some((f) => f.id === "devices")).toBe(true);
  });
  it("requires interface selection and rejects untrusted authority", () => {
    expect(
      connectSchemas["connect.enable"].safeParse({ discovery: false }).success,
    ).toBe(false);
    expect(
      connectSchemas["connect.enable"].safeParse({
        address: "127.0.0.1",
        discovery: false,
      }).success,
    ).toBe(true);
    expect(
      connectSchemas["connect.enable"].safeParse({
        address: "127.0.0.1",
        discovery: false,
        approved: true,
      }).success,
    ).toBe(false);
    expect(
      connectSchemas["connect.permission"].safeParse({
        device_id: crypto.randomUUID(),
        capability: "terminal",
        decision: "allow",
      }).success,
    ).toBe(false);
    for (const decision of ["allow", "ask", "deny"])
      expect(
        connectSchemas["connect.permission"].safeParse({
          device_id: crypto.randomUUID(),
          capability: "connect.ping",
          decision,
        }).success,
      ).toBe(true);
  });
  it("reports latency only for an authenticated online local channel", () => {
    const d: Device = {
      device_id: "test",
      display_name: "Peer",
      device_class: "desktop",
      platform: "linux",
      trust_state: "paired",
    };
    expect(deviceStatus(d)).toBe("Offline");
    d.live = {
      error: null,
      state: "online",
      encrypted: true,
      connection: "local",
      latency_ms: 0,
    };
    expect(deviceStatus(d)).toBe("Online · Local · 0.0 ms");
    d.live.state = "failed";
    expect(deviceStatus(d)).toBe("Connection failed");
    d.trust_state = "revoked";
    expect(deviceStatus(d)).toBe("Revoked");
  });
  it("retains artifact categories without implying availability", () => {
    expect(permissionGroups.map((g) => g[0])).toEqual([
      "Connection",
      "Personal",
      "Files",
      "Development",
      "System",
    ]);
  });
  it("renders a real QR from the supplied offer", () => {
    const one = renderToStaticMarkup(
      createElement(QRCodeSVG, { value: "public-offer-1" }),
    );
    const two = renderToStaticMarkup(
      createElement(QRCodeSVG, { value: "public-offer-2" }),
    );
    expect(one).toContain("<path");
    expect(one).not.toEqual(two);
  });
  it("renders bounded text as text in Connect approval without raw JSON", () => {
    const html = renderToStaticMarkup(
      createElement(ApprovalSummary, {
        approval: {
          id: "a",
          fingerprint: "f",
          summary: "Connect ping",
          tool_name: "connect.request",
          risk_level: "low",
          targets: [],
          arguments: {
            source_name: "<script>bad</script>",
            target_name: "This device",
            envelope_fingerprint: "hidden-digest",
          },
        },
      }),
    );
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("hidden-digest");
    expect(html).toContain("saved permission stays Ask");
  });
});
