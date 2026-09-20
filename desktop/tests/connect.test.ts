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
  it("accepts only bounded local desktop offer imports and explicit comparisons", () => {
    const imported = connectSchemas["connect.pair_accept"];
    expect(imported.safeParse({ offer: "public C2 payload" }).success).toBe(
      true,
    );
    for (const bad of [
      { offer: "" },
      { offer: "x".repeat(12289) },
      { offer: "public", confirmed: true },
      { offer: "public", permissions: [] },
    ])
      expect(imported.safeParse(bad).success).toBe(false);
    expect(
      connectSchemas["connect.pair_confirm"].safeParse({
        session_id: crypto.randomUUID(),
        compared_value: "observed value",
        auto_confirm: true,
      }).success,
    ).toBe(false);
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

describe("C5 local sync contracts", () => {
  it("separates per-domain sync from actions and rejects remote resolution authority", () => {
    for (const capability of [
      "sync.tasks",
      "sync.calendar",
      "sync.reminders",
      "sync.chat",
    ])
      for (const decision of ["deny", "ask", "allow"])
        expect(
          connectSchemas["connect.permission"].safeParse({
            device_id: crypto.randomUUID(),
            capability,
            decision,
          }).success,
        ).toBe(true);
    expect(
      connectSchemas["connect.sync_now"].safeParse({
        device_id: crypto.randomUUID(),
        approved: true,
      }).success,
    ).toBe(false);
    expect(
      connectSchemas["connect.sync_select"].safeParse({
        device_id: crypto.randomUUID(),
        conversation_id: crypto.randomUUID(),
        selected: true,
      }).success,
    ).toBe(true);
    expect(
      connectSchemas["connect.sync_resolve"].safeParse({
        conflict_id: crypto.randomUUID(),
        choice: "merge",
      }).success,
    ).toBe(false);
    expect(
      connectSchemas["connect.sync_resolve"].safeParse({
        conflict_id: crypto.randomUUID(),
        choice: "incoming",
        source_device_id: crypto.randomUUID(),
      }).success,
    ).toBe(false);
  });
});

describe("C6 file boundary", () => {
  it("permits scoped file settings without exposing paths or remote approvals", () => {
    for (const capability of ["files.receive", "files.send"])
      for (const decision of ["deny", "ask", "allow"])
        expect(
          connectSchemas["connect.permission"].safeParse({
            device_id: crypto.randomUUID(),
            capability,
            decision,
          }).success,
        ).toBe(true);
    expect(
      connectSchemas["connect.file_start"].safeParse({
        transfer_id: crypto.randomUUID(),
        path: "/invented",
      }).success,
    ).toBe(false);
    expect(
      connectSchemas["connect.file_start"].safeParse({
        transfer_id: crypto.randomUUID(),
        approved: true,
      }).success,
    ).toBe(false);
    expect("connect.file_prepare" in connectSchemas).toBe(false);
    expect("connect.file_export" in connectSchemas).toBe(false);
  });
  it("shows untrusted filename and type as inert text without a malware safety claim", () => {
    const html = renderToStaticMarkup(
      createElement(ApprovalSummary, {
        approval: {
          id: "a",
          fingerprint: "f",
          summary: "Receive an untrusted file into OLIVE Inbox",
          tool_name: "connect.request",
          risk_level: "medium",
          targets: [],
          arguments: {
            capability: "files.receive",
            file: {
              name: "<script>name</script>",
              size: 123,
              mime: "application/octet-stream",
            },
          },
        },
      }),
    );
    expect(html).not.toContain("<script>");
    expect(html).toContain("123");
    expect(html).toContain("does not open, execute or import");
    expect(html).not.toContain("read-only operation");
  });
});

describe("C8 Studio authority", () => {
  it("requires peer and opaque workspace scope and excludes executable operations", () => {
    const device_id = crypto.randomUUID(), workspace_id = crypto.randomUUID();
    expect(connectSchemas["connect.studio_permission"].safeParse({device_id, workspace_id, capability: "studio.edit", decision: "ask"}).success).toBe(true);
    expect(connectSchemas["connect.studio_permission"].safeParse({device_id, capability: "studio.edit", decision: "allow"}).success).toBe(false);
    for (const operation of ["terminal", "shell", "install", "debug", "git", "permission", "create_project"])
      expect(connectSchemas["connect.studio_request"].safeParse({device_id, workspace_id, share_revision: 1, operation, arguments: {}}).success).toBe(false);
    expect(connectSchemas["connect.studio_share"].safeParse({device_id, workspace_id: "/home/project"}).success).toBe(false);
  });
});
