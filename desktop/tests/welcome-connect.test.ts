import { describe, expect, it } from "vitest";
import { welcomeDevices } from "../src/services/runtimeState";

const phone = { device_id: "phone", display_name: "iPhone", trust_state: "paired", live: { state: "offline" } };
describe("Welcome live Connect state", () => {
  it("follows startup Off to On and actual connection without confusing trust and availability", () => {
    expect(welcomeDevices({ network: { state: "off" }, devices: [phone] }).detail).toBe("iPhone paired · Connect is off");
    expect(welcomeDevices({ network: { state: "on" }, devices: [phone] })).toEqual({ detail: "iPhone paired · Connect is on", done: false, waiting: false });
    expect(welcomeDevices({ network: { state: "on" }, devices: [{ ...phone, live: { state: "online" } }] })).toEqual({ detail: "iPhone connected", done: true, waiting: false });
  });
  it("never treats unavailable or starting status as an explicit Off", () => {
    expect(welcomeDevices(null).detail).toBe("Checking OLIVE Connect…");
    expect(welcomeDevices({ network: { state: "starting" }, devices: [phone] }).waiting).toBe(true);
    expect(welcomeDevices({ network: { state: "failed" }, devices: [phone] }).detail).toContain("status unavailable");
  });
  it("does not advertise revoked peers or imply all paired devices are online", () => {
    const online = { ...phone, live: { state: "online" } };
    expect(welcomeDevices({ network: { state: "on" }, devices: [online, { ...phone, display_name: "Laptop" }] }).detail).toBe("iPhone, Laptop paired · 1 connected");
    expect(welcomeDevices({ network: { state: "on" }, devices: [{ ...online, trust_state: "revoked" }] }).detail).toBe("None paired yet · pair a phone from Devices");
  });
});
