export type SafeCapability =
  | "connect.ping"
  | "device.status"
  | "chat.metadata.read"
  | "files.receive"
  | "models.remote"
  | "files.send"
  | "sync.notes"
  | "sync.draw";
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
export interface Transfer {
  transfer_id: string;
  direction: "incoming" | "outgoing";
  metadata: { name: string; size: number; sha256: string; mime: string };
  state: string;
  received_size: number;
  error: string | null;
}
export interface Device {
  studio_shares?: import("./StudioShares").StudioShare[];
  studio_jobs?: {job_id: string; workspace_id: string; operation: string; state: string}[];
  remote_ai?: { presets: Record<string, boolean>; jobs: { job_id: string; preset: string; state: string }[] };
  transfers?: Transfer[];
  sync?: DevicesState["sync"];
  /** OLIVE Notes live sync with this device (null when Notes is unavailable). */
  notes_sync?: { state: string; pending: number | null; last_sync?: string | null; refused?: number; error?: string } | null;
  /** OLIVE Draw live sync with this device: completed edits and images (null when Draw is unavailable). */
  draw_sync?: { state: string; pending: number | null; pending_assets?: number; last_sync?: string | null; refused?: number; error?: string } | null;
  device_id: string;
  display_name: string;
  platform: string;
  device_class: string;
  trust_state?: string;
  paired_at?: number;
  revoked_at?: number | null;
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
    /** "local" = Direct (LAN); "world" = OLIVE Connect World relay. */
    connection: string | null;
    latency_ms: number | null;
  };
  /** OLIVE Connect World for this pair: states and counters only, never route secrets. */
  world?: WorldPeer | null;
}
export interface WorldPeer {
  provisioned: boolean;
  confirmed: boolean;
  revoked: boolean;
  route: string;
  error: string | null;
  connected: boolean;
  last_connected_at: number | null;
  reconnects: number;
  bytes_in: number;
  bytes_out: number;
}
export interface WorldStatus {
  name: string;
  protocol: string;
  enabled: boolean;
  /** off | not_configured | connect_off | idle | connecting | connected | unavailable | conflict */
  relay: string;
  relay_host: string | null;
  relay_custom: boolean;
  managed: boolean;
  error: string | null;
  dev: boolean;
}
/** This computer's olive-chat/1 matrix, exactly what a paired phone is offered. */
export interface RemoteChatSummary {
  protocol: string;
  groups: { id: string; modes: { id: string; available: boolean; reason: string; limitations: string[] }[] }[];
  attachments: string[];
  video: { image_to_video: boolean; maximum_seconds: number | null; long_form: boolean } | null;
}
export interface DevicesState {
  /** Remote AI capabilities (null when Remote Chat is not attached in this build). */
  remote_chat?: RemoteChatSummary | null;
  /** Authoritative remote-control availability from the backend. */
  mobile_controls?: { unavailable: string[]; provided_by: Record<string, string> };
  sync?: {
    state: string;
    peer: string | null;
    sent: number;
    received: number;
    conflicts: number;
    last_sync: number | null;
    error?: string;
  };
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
    persistent?: boolean;
    pairing_port?: number | null;
  };
  nearby: { instance: string; address: string; port: number; state: string }[];
  /** Absent from an older backend: the World card is then not shown. */
  world?: WorldStatus;
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
/** The path an authenticated peer uses. Computation always stays on this computer. */
export function connectionPath(device: Device): "Direct" | "World" | null {
  const live = device.live;
  if (live?.state !== "online" || !live.encrypted) return null;
  return live.connection === "world" ? "World" : live.connection === "local" ? "Direct" : null;
}
export function deviceStatus(device: Device): string {
  if (device.trust_state === "revoked") return "Revoked";
  const path = connectionPath(device);
  if (path) return `Connected · ${path}`;
  const live = device.live;
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
      ["sync.notes", "Notes sync"],
      ["sync.draw", "Draw sync"],
    ],
  ],
  [
    "Files",
    [
      ["files.receive", "Receive files"],
      ["files.send", "Send selected files"],
      ["files.shared", "Shared folders"],
      ["filesystem.full", "Full filesystem"],
    ],
  ],
  [
    "Development",
    [
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

/** Future remote controls this computer cannot offer, labelled. The backend's
 * list is authoritative; Chat is served by Remote AI and is never listed. */
export function unavailableControls(data: Pick<DevicesState, "mobile_controls" | "capabilities">): string[] {
  const labels = new Map<string, string>(permissionGroups.flatMap(([, items]) => [...items] as [string, string][]));
  const provided = data.mobile_controls?.provided_by || { chat: "models.remote" };
  const names = data.mobile_controls?.unavailable ?? [...labels.keys()].filter((cap) => {
    const metadata = data.capabilities.find((c) => c.capability === cap);
    return metadata && !(metadata.supported && !metadata.policy_disabled && OFFERED.includes(cap));
  });
  return names.filter((cap) => !(cap in provided) && labels.has(cap)).map((cap) => labels.get(cap) as string);
}

/** Capabilities this version offers as controls; everything else is listed as unavailable. */
export const OFFERED = ["files.send", "models.remote", "files.receive", "connect.ping", "device.status", "chat.metadata.read", "sync.notes", "sync.draw"];

/** OLIVE Connect World, in plain words. Relay presence is never phone presence. */
export function worldSummary(world: WorldStatus): { label: string; detail: string; tone?: "online" | "warning" | "error" } {
  switch (world.relay) {
    case "off":
      return { label: "Off", detail: "Paired devices connect on your local network only." };
    case "not_configured":
      return { label: "Relay not configured", detail: "Add a relay in Advanced to use World.", tone: "warning" };
    case "connect_off":
      return { label: "Waiting for Connect", detail: "Turn on OLIVE Connect to use World.", tone: "warning" };
    case "idle":
      return { label: "Ready", detail: "A phone sets itself up the next time it connects on your local network.", tone: "online" };
    case "connected":
      return { label: "Ready", detail: "World relay connected.", tone: "online" };
    case "connecting":
      return { label: "Connecting…", detail: "Reaching the World relay." };
    case "conflict":
      return { label: "In use elsewhere", detail: "Another copy of this OLIVE profile is using Connect World.", tone: "error" };
    default:
      return { label: "Relay unavailable", detail: "World relay is unreachable. Local connections still work.", tone: "error" };
  }
}
/** This device's World state; "Connected · World" only after OLIVE authenticated it. */
export function worldDeviceLabel(world: WorldPeer | null | undefined, status?: WorldStatus): string {
  if (!world) return status && status.relay !== "off" && status.relay !== "not_configured" ? "Not set up yet" : "Not set up";
  if (world.revoked) return "Revoked";
  if (world.connected) return "Connected · World";
  if (!world.provisioned) return "Not set up yet";
  if (!world.confirmed) return "Setting up this device…";
  return status?.relay === "connected" ? "Ready" : status ? worldSummary(status).label : "Ready";
}
export function byteLabel(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  return `${(value / 1024 ** 3).toFixed(2)} GB`;
}
