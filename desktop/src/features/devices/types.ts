export type SafeCapability =
  "connect.ping" | "device.status" | "chat.metadata.read";
export interface NetworkInterface {
  name: string;
  address: string;
  network: string;
}
export interface Capability {
  capability: string;
  supported: boolean;
  policy_disabled: boolean;
}
export interface Device {
  device_id: string;
  display_name: string;
  platform: string;
  device_class: string;
  trust_state?: string;
  paired_at?: number;
  last_seen?: number;
  fingerprint?: string;
  identity_fingerprint?: string;
  core_available?: boolean;
  public_identity_metadata?: { os: string };
  permissions?: {
    capability: string;
    decision: "allow" | "ask" | "deny";
    scope: string | null;
  }[];
  live?: {
    state: string;
    error: string | null;
    encrypted: boolean;
    connection: string | null;
    latency_ms: number | null;
  };
}
export interface DevicesState {
  local: Device;
  devices: Device[];
  capabilities: Capability[];
  interfaces: NetworkInterface[];
  interface_error: string | null;
  protocol: string;
  network: {
    state: string;
    error: string | null;
    interface: NetworkInterface | null;
    port: number | null;
    discovery: boolean;
  };
  nearby: { instance: string; address: string; port: number; state: string }[];
  pairing_recovery?: { session_id: string; state: string }[];
  activity: {
    id: number;
    source_device_id: string;
    timestamp: number;
    result_state: string;
    capability: string | null;
  }[];
}
export interface PairingState {
  session_id: string;
  state: string;
  expires_at: number;
  offer?: string;
  comparison?: string;
  fingerprint?: string;
  candidate_id?: string;
  candidate_name?: string;
  completion_code?: string;
  listener_active?: boolean;
  error?: string;
  device_id?: string;
}
export function deviceStatus(device: Device): string {
  if (device.trust_state === "revoked") return "Revoked";
  const live = device.live;
  if (live?.state === "online" && live.encrypted && live.connection === "local")
    return `Online · Local${live.latency_ms !== null ? ` · ${live.latency_ms.toFixed(1)} ms` : ""}`;
  return (
    (
      {
        connecting: "Connecting",
        authenticating: "Authenticating",
        failed: "Connection failed",
        discovering: "Discovered",
      } as Record<string, string>
    )[live?.state || ""] || "Offline"
  );
}
export const permissionGroups = [
  [
    "Connection",
    [
      ["connect.ping", "Connect ping"],
      ["device.status", "Device status"],
    ],
  ],
  [
    "Personal",
    [
      ["chat.metadata.read", "Chat availability metadata"],
      ["chat", "Chat"],
      ["tasks", "Tasks"],
      ["calendar", "Calendar"],
      ["reminders", "Reminders"],
      ["notifications", "Notifications"],
    ],
  ],
  [
    "Files",
    [
      ["files.receive", "Receive files"],
      ["files.shared", "Shared folders"],
      ["filesystem.full", "Full filesystem"],
    ],
  ],
  [
    "Development",
    [
      ["studio.view", "Studio"],
      ["studio.run", "Run project"],
      ["models.remote", "Remote AI"],
      ["terminal", "Terminal"],
    ],
  ],
  [
    "System",
    [
      ["apps.launch", "Launch apps"],
      ["desktop_control", "Desktop Control"],
      ["software.install", "Install software"],
    ],
  ],
] as const;
