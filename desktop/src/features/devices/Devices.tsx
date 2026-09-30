import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import {
  ArrowLeft,
  Info,
  KeyRound,
  Lock,
  Plus,
  Radio,
  ShieldOff,
  Trash2,
  Wifi,
} from "lucide-react";
import { call } from "../../services/api";
import { FilesPanel } from "./FilesPanel";
import { StudioShares } from "./StudioShares";
import { RemoteAI } from "./RemoteAI";
import { SyncPanel } from "./SyncPanel";
import { Pairing } from "./Pairing";
import {
  deviceStatus,
  permissionGroups,
  OFFERED,
  unavailableControls,
  type Device,
  type DevicesState,
  type PairingState,
  type SafeCapability,
} from "./types";
import { Confirm, DeviceIcon, Segmented, ago, dateLabel, deviceKind, fullTime, sentence } from "./ui";
import "./devices.css";

const DRAW_STATE: Record<string, string> = {
  synced: "Synced", syncing: "Syncing", offline: "Offline · edits wait on this computer", off: "Off", error: "Sync issue",
  idle: "Waiting to connect", unsupported: "Not supported by this device’s OLIVE version",
};
/** Only Off and Allow: live sync never stops to ask per note or per stroke. */
const LIVE_SYNC = new Set(["sync.notes", "sync.draw"]);
const NOTES_STATE: Record<string, string> = {
  synced: "Synced", syncing: "Syncing", offline: "Offline · changes wait on this computer", off: "Off", error: "Sync issue", idle: "Waiting to connect",
};
const TABS = ["status", "permissions", "activity"] as const;
type Tab = (typeof TABS)[number];

const CAPABILITY_LABELS: Record<string, string> = {
  ...Object.fromEntries(permissionGroups.flatMap(([, items]) => items.map(([cap, label]) => [cap, label]))),
  "sync.tasks": "Tasks sync",
  "sync.calendar": "Calendar sync",
  "sync.reminders": "Reminders sync",
  "sync.chat": "Chat sync",
};
const capabilityLabel = (cap: string) =>
  CAPABILITY_LABELS[cap] || (cap.startsWith("studio.") ? `Studio ${cap.slice(7)}` : sentence(cap));

const EVENT_LABELS: Record<string, string> = {
  device_revoked: "Device revoked",
  revoked_connection_closed: "Connection closed after revoke",
  pairing_completed: "Paired",
  connection_authenticated: "Connected securely",
  connection_started: "Connecting",
  connection_closed: "Disconnected",
  connection_failed: "Connection failed",
  permission_changed: "Permission changed",
  permission_off: "Blocked · permission is Off",
  confirmation_required: "Waiting for your approval",
  file_offer: "File offered",
  file_accepted: "File accepted",
  file_declined: "File declined",
  transfer_started: "Transfer started",
  transfer_completed: "Transfer completed",
  transfer_cancelled: "Transfer cancelled",
  transfer_failed: "Transfer failed",
};
const eventLabel = (state: string) => EVENT_LABELS[state] || sentence(state);
const eventTone = (state: string) =>
  /revoked|failed|denied|declined|rejected|mismatch|invalid|error/.test(state) ? "error"
  : /off|required|cancel|closed|expired/.test(state) ? "warning"
  : /approved|completed|paired|authenticated|accepted|allowed/.test(state) ? "success"
  : "neutral";

export function Devices() {
  const [data, setData] = useState<DevicesState | null>(null),
    [error, setError] = useState(""),
    [selected, setSelected] = useState("this"),
    [detail, setDetail] = useState(false),
    [tab, setTab] = useState<Tab>("status"),
    [busy, setBusy] = useState(false),
    [address, setAddress] = useState(""),
    [discovery, setDiscovery] = useState(false),
    [persistent, setPersistent] = useState(false),
    [editing, setEditing] = useState(false),
    [name, setName] = useState(""),
    [importing, setImporting] = useState(false),
    [pairingCode, setPairingCode] = useState(""),
    [pairing, setPairing] = useState<PairingState | null>(null),
    [revoke, setRevoke] = useState(false),
    [removing, setRemoving] = useState(false),
    [clearingActivity, setClearingActivity] = useState(false),
    [endpoint, setEndpoint] = useState(""),
    [port, setPort] = useState("");
  // Actions run one at a time. Controls stay enabled while one runs, so the
  // page does not flash every button to its disabled look on each click.
  const running = useRef(false);
  const refresh = useCallback(async () => {
    const value = await call<DevicesState>("connect.snapshot", {});
    setData(value);
  }, []);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const value = await call<DevicesState>("connect.snapshot", {});
        if (!stopped) setData(value);
      } catch {
        if (!stopped)
          setError(
            "Devices is unavailable. Check the local backend and retry.",
          );
      }
      if (!stopped) timer = setTimeout(() => void poll(), 1500);
    };
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, []);
  const act = async (action: () => Promise<unknown>) => {
    if (running.current) return;
    running.current = true;
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "The action could not complete.",
      );
    } finally {
      running.current = false;
      setBusy(false);
    }
  };
  const select = (id: string) => {
    setSelected(id);
    setDetail(true);
    setTab("status");
    setEditing(false);
    setEndpoint("");
    setPort("");
  };
  const startPairing = () => {
    if (data?.network.state !== "on") {
      setError(
        "Turn on OLIVE Connect for this computer before pairing.",
      );
      select("this");
      return;
    }
    void act(async () =>
      setPairing(await call<PairingState>("connect.pair_create", {})),
    );
  };
  const device =
    selected === "this"
      ? data?.local
      : data?.devices.find((d) => d.device_id === selected);
  // A removed device disappears from the snapshot; fall back to this computer.
  useEffect(() => {
    if (data && selected !== "this" && selected !== "nearby" && !device) setSelected("this");
  }, [data, selected, device]);
  const tone = (d: Device) =>
    d.trust_state === "revoked" ? "error" : d.live?.state === "online" ? "online" : "offline";
  const row = (d: Device, local = false) => (
    <button
      key={d.device_id}
      className={`devices-row ${selected === (local ? "this" : d.device_id) ? "selected" : ""}`}
      onClick={() => select(local ? "this" : d.device_id)}
    >
      <span className="devices-icon">
        <DeviceIcon device={d} />
      </span>
      <span>
        <strong>{d.display_name}</strong>
        <small>
          {local
            ? `${d.public_identity_metadata?.os || d.platform} · Connect ${data?.network.state === "on" ? "on" : "off"}`
            : deviceStatus(d)}
        </small>
      </span>
      {!local && <span className="status-dot" data-tone={tone(d)} aria-hidden="true" />}
    </button>
  );
  const on = data?.network.state === "on";
  const remote = device && selected !== "this" ? device : null;
  const revoked = remote?.trust_state === "revoked";
  const activity = remote && data ? data.activity.filter((a) => a.source_device_id === remote.device_id).reverse() : [];
  return (
    <section className="devices-workspace" aria-label="Devices workspace" aria-busy={busy}>
      <header className="devices-head">
        <div>
          <h1>Devices</h1>
          <p>Pair your phone and other computers over your own network.</p>
        </div>
        <button className="quiet devices-code" disabled={!data} onClick={() => setImporting(true)}>
          <KeyRound size={15} aria-hidden="true" />
          Enter pairing code
        </button>
        <button className="primary devices-pair-primary" disabled={!data} onClick={startPairing}>
          <Plus size={16} aria-hidden="true" />
          Pair a device
        </button>
      </header>
      {error && (
        <div className="devices-error" role="alert">
          <span>{error}</span>
          <button className="quiet" onClick={() => void act(refresh)}>Retry</button>
          <button className="quiet" aria-label="Dismiss" onClick={() => setError("")}>✕</button>
        </div>
      )}
      {!data ? (
        <div className="devices-empty">Loading devices…</div>
      ) : (
        <div className="devices-body" data-detail={detail}>
          <aside className="devices-rail" aria-label="Device list">
            <div className="devices-rail-scroll">
              <p className="devices-eyebrow">This computer</p>
              {row(data.local, true)}
              {data.pairing_recovery?.map((session) => (
                <button
                  className="devices-row devices-row-recovery"
                  key={session.session_id}
                  onClick={() =>
                    void act(async () =>
                      setPairing(
                        await call<PairingState>("connect.pair_status", {
                          session_id: session.session_id,
                        }),
                      ),
                    )
                  }
                >
                  <span className="devices-icon"><KeyRound size={15} aria-hidden="true" /></span>
                  <span>
                    <strong>Finish pairing</strong>
                    <small>{session.state === "completed" ? "Completed" : "Pending"}</small>
                  </span>
                </button>
              ))}
              <p className="devices-eyebrow">
                Paired
                {data.devices.length > 0 && <span className="devices-count">{data.devices.length}</span>}
              </p>
              {data.devices.map((d) => row(d))}
              {!data.devices.length && (
                <p className="devices-rail-empty">No paired devices yet.</p>
              )}
              <p className="devices-eyebrow">Nearby</p>
              {!data.nearby.length && (
                <p className="devices-rail-empty">
                  {!on
                    ? "Turn Connect on to find nearby devices."
                    : data.network.discovery
                      ? "No nearby OLIVE devices found."
                      : "Nearby discovery is off."}
                </p>
              )}
              {data.nearby.map((n) => (
                <button
                  className={`devices-row unpaired ${selected === "nearby" && endpoint === n.address ? "selected" : ""}`}
                  key={n.instance}
                  onClick={() => {
                    select("nearby");
                    setEndpoint(n.address);
                    setPort(String(n.port));
                  }}
                >
                  <span className="devices-icon">
                    <Radio size={15} aria-hidden="true" />
                  </span>
                  <span>
                    <strong>OLIVE device</strong>
                    <small>{n.address} · Discovered · Unpaired</small>
                  </span>
                </button>
              ))}
            </div>
            <footer className="devices-rail-foot">
              <span className="status-dot" data-tone={on ? "online" : "offline"} aria-hidden="true" />
              <span>
                <strong>OLIVE Connect {on ? "on" : "off"}</strong>
                <small>
                  {on
                    ? `${data.network.interface?.name} · ${data.network.interface?.address}`
                    : "Not reachable by other devices"}
                </small>
              </span>
              <button
                className="quiet"
                aria-label={on ? "Turn Connect off" : "Set up Connect"}
                onClick={() =>
                  on
                    ? void act(() => call("connect.disable", {}))
                    : select("this")
                }
              >
                {on ? "Turn off" : "Set up"}
              </button>
            </footer>
          </aside>
          <main className="devices-main">
            <div className="devices-main-inner" key={selected}>
              <button
                className="devices-back quiet"
                onClick={() => setDetail(false)}
              >
                <ArrowLeft size={16} aria-hidden="true" />
                Back to devices
              </button>
              {selected === "nearby" ? (
                <>
                  <div className="devices-detail-head">
                    <span className="devices-icon large"><Radio size={22} aria-hidden="true" /></span>
                    <div>
                      <h2>OLIVE device</h2>
                      <p className="devices-sub-line">
                        <span className="devices-pill">Unpaired · Untrusted</span>
                        <span className="mono">{endpoint}:{port}</span>
                      </p>
                    </div>
                  </div>
                  <section className="devices-card">
                    <header className="devices-card-head">
                      <div>
                        <h3>Pair with this device</h3>
                        <p>
                          Discovery doesn’t prove who this is. Pairing asks both
                          devices to compare and confirm the same code.
                        </p>
                      </div>
                      <div className="devices-card-actions">
                        <button className="primary" onClick={startPairing}>
                          Create pairing offer
                        </button>
                      </div>
                    </header>
                  </section>
                </>
              ) : (
                device && (
                  <>
                    <div className="devices-detail-head">
                      <span className="devices-icon large">
                        <DeviceIcon device={device} size={22} />
                      </span>
                      <div>
                        <h2>{device.display_name}</h2>
                        <p className="devices-sub-line">
                          {remote ? (
                            <span className="devices-pill" data-tone={tone(remote)}>
                              <span className="status-dot" data-tone={tone(remote)} aria-hidden="true" />
                              {deviceStatus(remote)}
                            </span>
                          ) : (
                            <span className="devices-pill">This computer</span>
                          )}
                          <span>{deviceKind(device)}</span>
                          {remote?.paired_at ? <span>Paired {dateLabel(remote.paired_at)}</span> : null}
                        </p>
                      </div>
                    </div>
                    {selected === "this" ? (
                      <>
                        <section className="devices-card" aria-label="OLIVE Connect">
                          <header className="devices-card-head">
                            <div>
                              <h3>OLIVE Connect</h3>
                              <p>
                                Lets paired devices reach this computer on your
                                local network.
                              </p>
                            </div>
                            <span className="devices-pill" data-tone={on ? "online" : undefined}>
                              {busy ? "Working…" : on ? "On" : data.network.state === "failed" ? "Failed" : "Off"}
                            </span>
                          </header>
                          {data.network.error && (
                            <p className="devices-inline-error" role="alert">
                              Could not start Connect:{" "}
                              {data.network.error.replaceAll("_", " ")}. Check
                              the selected network, secure key store and
                              firewall.
                            </p>
                          )}
                          <div className="devices-field">
                            <span className="devices-field-label">Network</span>
                            <div className="devices-interfaces">
                              {data.interfaces.map((i) => (
                                <button
                                  key={i.address}
                                  aria-pressed={
                                    on
                                      ? data.network.interface?.address === i.address
                                      : address === i.address
                                  }
                                  disabled={on}
                                  className="devices-interface"
                                  onClick={() => setAddress(i.address)}
                                >
                                  <Wifi size={16} aria-hidden="true" />
                                  <span>
                                    <strong>{i.name}</strong>
                                    <small>{i.address}</small>
                                  </span>
                                </button>
                              ))}
                            </div>
                            {!data.interfaces.length && (
                              <p className="devices-hint">
                                No approved local networks available.{" "}
                                {data.interface_error?.replaceAll("_", " ")}
                              </p>
                            )}
                          </div>
                          <label className="devices-toggle">
                            <input
                              type="checkbox"
                              className="switch"
                              checked={
                                on ? data.network.discovery : discovery
                              }
                              disabled={on}
                              onChange={(e) => setDiscovery(e.target.checked)}
                            />
                            <span>
                              Nearby discovery
                              <small>
                                Advertise this computer on the selected network.
                              </small>
                            </span>
                          </label>
                          <label className="devices-toggle">
                            <input type="checkbox" className="switch" checked={on ? !!data.network.persistent : persistent}
                              disabled={on} onChange={(e) => setPersistent(e.target.checked)} />
                            <span>
                              Keep Connect available after restart
                              <small>Remember this network and use stable ports.</small>
                            </span>
                          </label>
                          <div className="devices-card-foot">
                            <button
                              className={on ? "" : "primary"}
                              disabled={
                                !on &&
                                !data.interfaces.some(
                                  (i) => i.address === address,
                                )
                              }
                              onClick={() =>
                                void act(() =>
                                  on
                                    ? call("connect.disable", {})
                                    : call("connect.enable", {
                                        address,
                                        discovery,
                                        persistent,
                                      }),
                                )
                              }
                            >
                              {on ? "Turn Connect off" : "Turn Connect on"}
                            </button>
                            <span className="devices-hint">
                              {on
                                ? "Turn Connect off to change these settings."
                                : "Pick a network first. OLIVE never changes your firewall."}
                            </span>
                          </div>
                          {data.network.persistent && <p className="devices-hint devices-card-note">
                            Connect port {data.network.port}. Pairing port {data.network.pairing_port} opens only during pairing.
                          </p>}
                        </section>
                        <section className="devices-card" aria-label="Display name">
                          {editing ? (
                            <form
                              className="devices-rename"
                              onSubmit={(e) => {
                                e.preventDefault();
                                void act(async () => {
                                  await call("connect.rename", { name });
                                  setEditing(false);
                                });
                              }}
                            >
                              <label>
                                Display name
                                <input
                                  autoFocus
                                  value={name}
                                  maxLength={100}
                                  onChange={(e) => setName(e.target.value)}
                                />
                              </label>
                              <button type="button" className="quiet" onClick={() => setEditing(false)}>Cancel</button>
                              <button className="primary" disabled={!name.trim()}>
                                Save name
                              </button>
                            </form>
                          ) : (
                            <header className="devices-card-head">
                              <div>
                                <h3>Display name</h3>
                                <p>Other devices see this computer as <strong>{device.display_name}</strong>.</p>
                              </div>
                              <div className="devices-card-actions">
                                <button
                                  onClick={() => {
                                    setName(device.display_name);
                                    setEditing(true);
                                  }}
                                >
                                  Edit display name
                                </button>
                              </div>
                            </header>
                          )}
                        </section>
                        <details className="devices-disclosure">
                          <summary>Advanced details</summary>
                          <dl>
                            <dt>OLIVE Core</dt>
                            <dd>{device.core_available ? "Available" : "Unavailable"}</dd>
                            <dt>Device ID</dt>
                            <dd className="mono">{device.device_id}</dd>
                            <dt>Fingerprint</dt>
                            <dd className="mono">
                              {device.fingerprint ||
                                "Created in the secure vault when you turn on Connect or pair."}
                            </dd>
                            <dt>Protocol</dt>
                            <dd>{data.protocol}</dd>
                            <dt>Selected network</dt>
                            <dd>{data.network.interface?.address || "None"}</dd>
                            <dt>Connect port</dt>
                            <dd>{data.network.port || "Not listening"}</dd>
                          </dl>
                          <p>
                            Only the Connect TCP port and local mDNS (UDP 5353)
                            matter for your firewall. Don’t open Ollama or
                            Studio ports.
                          </p>
                        </details>
                      </>
                    ) : remote && (
                      <>
                        <div
                          className="devices-tabs"
                          role="group"
                          aria-label="Device details"
                          style={{ "--i": TABS.indexOf(tab) } as CSSProperties}
                        >
                          <span className="devices-seg-thumb" aria-hidden="true" />
                          {TABS.map((t) => (
                            <button
                              key={t}
                              aria-pressed={tab === t}
                              onClick={() => setTab(t)}
                            >
                              {t[0].toUpperCase() + t.slice(1)}
                              {t === "activity" && activity.length > 0 && <span className="devices-count" aria-hidden="true">{activity.length}</span>}
                            </button>
                          ))}
                        </div>
                        <div className="devices-view" key={tab}>
                          {tab === "status" && (
                            <>
                              {revoked ? (
                                <section className="devices-card devices-revoked" aria-label="Revoked">
                                  <header className="devices-card-head">
                                    <span className="devices-card-icon"><ShieldOff size={16} aria-hidden="true" /></span>
                                    <div>
                                      <h3>Revoked{remote.revoked_at ? ` ${dateLabel(remote.revoked_at)}` : ""}</h3>
                                      <p>
                                        {remote.display_name} is disconnected and
                                        can’t reconnect. This identity can’t be
                                        paired again.
                                      </p>
                                    </div>
                                  </header>
                                </section>
                              ) : (
                                <section className="devices-card" aria-label="Connection">
                                  <header className="devices-card-head">
                                    <div>
                                      <h3>Connection</h3>
                                      <p>
                                        {remote.last_seen
                                          ? <>Last seen <span title={fullTime(remote.last_seen)}>{ago(remote.last_seen)}</span></>
                                          : "Not connected yet."}
                                      </p>
                                    </div>
                                    {remote.live?.state === "online" && (
                                      <div className="devices-card-actions">
                                        <button
                                          onClick={() =>
                                            void act(async () => {
                                              const r = await call<{
                                                state: string;
                                                error?: string;
                                              }>("connect.ping", {
                                                device_id: remote.device_id,
                                              });
                                              if (r.state !== "completed")
                                                throw new Error(
                                                  (r.error === "confirmation_required"
                                                    ? "Waiting for approval on the other device. After approval, select Measure latency again."
                                                    : r.error?.replaceAll("_", " ")) || "Ping not completed",
                                                );
                                            })
                                          }
                                        >
                                          Measure latency
                                        </button>
                                        <button
                                          className="quiet"
                                          onClick={() =>
                                            void act(() =>
                                              call("connect.disconnect", {
                                                device_id: remote.device_id,
                                              }),
                                            )
                                          }
                                        >
                                          Disconnect
                                        </button>
                                      </div>
                                    )}
                                  </header>
                                  <dl className="devices-facts">
                                    <div>
                                      <dt>Status</dt>
                                      <dd>
                                        <span className="status-dot" data-tone={tone(remote)} aria-hidden="true" />
                                        {deviceStatus(remote)}
                                      </dd>
                                    </div>
                                    <div>
                                      <dt>Encryption</dt>
                                      <dd>
                                        {remote.live?.encrypted && remote.live.state === "online" ? (
                                          <span className="devices-tls">
                                            <Lock size={13} aria-hidden="true" />
                                            TLS 1.3
                                          </span>
                                        ) : (
                                          "Not connected"
                                        )}
                                      </dd>
                                    </div>
                                    <div>
                                      <dt>Identity</dt>
                                      <dd>Verified at pairing</dd>
                                    </div>
                                  </dl>
                                  {remote.live?.error && (
                                    <p className="devices-inline-error" role="alert">
                                      {sentence(remote.live.error)}. Check Connect
                                      is on for both devices and the port is
                                      allowed by the firewall.
                                    </p>
                                  )}
                                  {remote.live?.state !== "online" && (
                                    <form
                                      className="devices-endpoint"
                                      onSubmit={(e) => {
                                        e.preventDefault();
                                        void act(() =>
                                          call("connect.open", {
                                            device_id: remote.device_id,
                                            address: endpoint,
                                            port: Number(port),
                                          }),
                                        );
                                      }}
                                    >
                                      {data.nearby.length > 0 && (
                                        <label>
                                          Discovered endpoint
                                          <select
                                            value=""
                                            onChange={(e) => {
                                              const n = data.nearby.find(
                                                (n) => n.instance === e.target.value,
                                              );
                                              if (n) {
                                                setEndpoint(n.address);
                                                setPort(String(n.port));
                                              }
                                            }}
                                          >
                                            <option value="">Choose…</option>
                                            {data.nearby.map((n) => (
                                              <option key={n.instance} value={n.instance}>
                                                {n.address}:{n.port}
                                              </option>
                                            ))}
                                          </select>
                                        </label>
                                      )}
                                      <label>
                                        Local address
                                        <input
                                          value={endpoint}
                                          maxLength={64}
                                          placeholder="192.168.1.20"
                                          onChange={(e) => setEndpoint(e.target.value)}
                                        />
                                      </label>
                                      <label className="devices-endpoint-port">
                                        Connect port
                                        <input
                                          type="number"
                                          min={1}
                                          max={65535}
                                          value={port}
                                          onChange={(e) => setPort(e.target.value)}
                                        />
                                      </label>
                                      <button className="primary" disabled={!on || !endpoint || !port}>
                                        Connect
                                      </button>
                                      <p className="devices-hint">
                                        {on
                                          ? "The device’s identity is checked again before connecting."
                                          : "Turn on Connect for this computer first."}
                                      </p>
                                    </form>
                                  )}
                                </section>
                              )}
                              {(!revoked || remote.transfers?.some((t) => t.state !== "dismissed")) && <FilesPanel
                                key={`files-${remote.device_id}`}
                                device={remote}
                                refresh={refresh}
                              />}
                              {data.sync && !revoked && (
                                <SyncPanel
                                  key={remote.device_id}
                                  device={remote}
                                  data={data}
                                  refresh={refresh}
                                />
                              )}
                              {!revoked && <RemoteAI device={remote} summary={data.remote_chat} refresh={refresh} />}
                              {revoked ? (
                                <section className="devices-danger" aria-label="Remove device">
                                  <div>
                                    <strong>Remove from Devices</strong>
                                    <p>Removes {remote.display_name} and its activity from this list. OLIVE keeps it blocked.</p>
                                  </div>
                                  <button className="danger" onClick={() => setRemoving(true)}>
                                    <Trash2 size={14} aria-hidden="true" />
                                    Remove device
                                  </button>
                                </section>
                              ) : (
                                <section className="devices-danger" aria-label="Revoke pairing">
                                  <div>
                                    <strong>Revoke pairing</strong>
                                    <p>{remote.display_name} loses every permission at once and can’t reconnect.</p>
                                  </div>
                                  <button className="danger" onClick={() => setRevoke(true)}>
                                    Revoke device
                                  </button>
                                </section>
                              )}
                            </>
                          )}
                          {tab === "permissions" && (
                            revoked ? (
                              <p className="devices-note" role="note">
                                <ShieldOff size={14} aria-hidden="true" />
                                <span>Permissions are inactive for this revoked device.</span>
                              </p>
                            ) : (
                              <>
                                <p className="devices-note" role="note">
                                  <Info size={14} aria-hidden="true" />
                                  <span>
                                    Pairing proves this is {remote.display_name} but <strong>grants no access</strong>.
                                    These settings control what it can do on this computer.
                                  </span>
                                </p>
                                <section className="devices-card" aria-label="Permissions">
                                  {permissionGroups.map(([group, items]) => {
                                    const shown = items.filter(([cap]) => {
                                      const metadata = data.capabilities.find((c) => c.capability === cap);
                                      return metadata && metadata.supported && !metadata.policy_disabled && OFFERED.includes(cap);
                                    });
                                    if (!shown.length) return null;
                                    return (
                                      <div className="devices-group" key={group}>
                                        <h3 className="devices-eyebrow">{group}</h3>
                                        {shown.map(([cap, label]) => (
                                          <div className="devices-row-line devices-permission" key={cap}>
                                            <span className="devices-row-label">
                                              {label}
                                              {cap === "sync.draw" && remote.draw_sync && remote.draw_sync.state !== "off" && (
                                                <small className="devices-notes-sync">
                                                  {DRAW_STATE[remote.draw_sync.state] || sentence(remote.draw_sync.state)}
                                                  {remote.draw_sync.pending ? ` · ${remote.draw_sync.pending} edit${remote.draw_sync.pending === 1 ? "" : "s"} to send` : ""}
                                                  {remote.draw_sync.pending_assets ? ` · ${remote.draw_sync.pending_assets} image${remote.draw_sync.pending_assets === 1 ? "" : "s"} arriving` : ""}
                                                  {remote.draw_sync.last_sync ? ` · last ${remote.draw_sync.last_sync.slice(11, 16)} UTC` : ""}
                                                </small>
                                              )}
                                              {cap === "sync.notes" && remote.notes_sync && remote.notes_sync.state !== "off" && (
                                                <small className="devices-notes-sync">
                                                  {NOTES_STATE[remote.notes_sync.state] || sentence(remote.notes_sync.state)}
                                                  {remote.notes_sync.pending ? ` · ${remote.notes_sync.pending} to send` : ""}
                                                  {remote.notes_sync.last_sync ? ` · last ${remote.notes_sync.last_sync.slice(11, 16)} UTC` : ""}
                                                </small>
                                              )}
                                            </span>
                                            <Segmented
                                              options={LIVE_SYNC.has(cap) ? ["deny", "allow"] : undefined}
                                              label={label}
                                              value={
                                                remote.permissions?.find(
                                                  (p) => p.capability === cap && p.scope === null,
                                                )?.decision || "deny"
                                              }
                                              onChange={(decision) =>
                                                act(() =>
                                                  call("connect.permission", {
                                                    device_id: remote.device_id,
                                                    capability: cap as SafeCapability,
                                                    decision,
                                                  }),
                                                )
                                              }
                                            />
                                          </div>
                                        ))}
                                      </div>
                                    );
                                  })}
                                  {(() => {
                                    const labels = unavailableControls(data);
                                    return labels.length ? (
                                      <p className="devices-unavailable-line">
                                        <span className="devices-unavailable">Additional mobile controls</span>
                                        <span>Not available in this version: {labels.join(" · ")}.</span>
                                      </p>
                                    ) : null;
                                  })()}
                                </section>
                                <StudioShares key={`studio-${remote.device_id}`} device={remote} refresh={refresh} />
                              </>
                            )
                          )}
                          {tab === "activity" && (
                            <section className="devices-card" aria-label="Activity">
                              <header className="devices-card-head">
                                <div>
                                  <h3>Activity</h3>
                                  <p>Connection and permission events. Never message or file content.</p>
                                </div>
                                <div className="devices-card-actions">
                                  <button
                                    className="quiet"
                                    disabled={!activity.length}
                                    onClick={() => setClearingActivity(true)}
                                  >
                                    Clear activity
                                  </button>
                                </div>
                              </header>
                              {activity.length ? (
                                <ol className="devices-activity">
                                  {activity.map((a) => (
                                    <li key={a.id} data-tone={eventTone(a.result_state)}>
                                      <span className="devices-activity-dot" aria-hidden="true" />
                                      <span className="devices-activity-text">
                                        <strong>{eventLabel(a.result_state)}</strong>
                                        {a.capability && <span>{capabilityLabel(a.capability)}</span>}
                                      </span>
                                      <time
                                        dateTime={new Date(a.timestamp * 1000).toISOString()}
                                        title={fullTime(a.timestamp)}
                                      >
                                        {ago(a.timestamp)}
                                      </time>
                                    </li>
                                  ))}
                                </ol>
                              ) : (
                                <p className="devices-empty-line">No device activity yet.</p>
                              )}
                            </section>
                          )}
                        </div>
                      </>
                    )}
                  </>
                )
              )}
            </div>
          </main>
        </div>
      )}
      <Dialog.Root open={importing} onOpenChange={setImporting}>
        <Dialog.Portal>
          <Dialog.Overlay className="devices-overlay" />
          <Dialog.Content className="devices-modal">
            <Dialog.Title>Enter pairing code</Dialog.Title>
            <Dialog.Description>
              Paste the pairing code shown on the other OLIVE computer. Turn on
              Connect for this computer first. A completion code can also
              finish a pairing you already confirmed.
            </Dialog.Description>
            <label>
              Pairing code
              <textarea
                value={pairingCode}
                maxLength={12288}
                onChange={(event) => setPairingCode(event.target.value)}
              />
            </label>
            {error && (
              <p role="alert">
                Could not use this pairing code. Check the code, expiry and
                selected network.
              </p>
            )}
            <div className="devices-modal-actions">
              <Dialog.Close>Cancel</Dialog.Close>
              <button
                className="primary"
                disabled={busy || !pairingCode.trim()}
                onClick={() =>
                  void act(async () => {
                    const result = await call<PairingState>(
                      "connect.pair_accept",
                      { offer: pairingCode.trim() },
                    );
                    setPairing(result);
                    setImporting(false);
                    setPairingCode("");
                  })
                }
              >
                Use pairing code
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      {pairing && (
        <Pairing
          key={pairing.session_id}
          initial={pairing}
          close={() => setPairing(null)}
          refresh={() => void refresh()}
        />
      )}
      <Dialog.Root open={revoke} onOpenChange={setRevoke}>
        <Dialog.Portal>
          <Dialog.Overlay className="devices-overlay" />
          <Dialog.Content className="devices-modal">
            <Dialog.Title>Revoke {device?.display_name}?</Dialog.Title>
            <Dialog.Description>
              {device?.display_name} is disconnected right away and loses every
              permission. This can’t be undone; the same identity can’t pair
              again.
            </Dialog.Description>
            <div className="devices-modal-actions">
              <Dialog.Close>Cancel</Dialog.Close>
              <button
                className="danger"
                disabled={busy}
                onClick={() =>
                  void act(async () => {
                    await call("connect.revoke", { device_id: selected });
                    setRevoke(false);
                  })
                }
              >
                Revoke
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <Confirm
        open={removing}
        onOpenChange={setRemoving}
        title={`Remove ${remote?.display_name ?? "device"}?`}
        action="Remove device"
        onConfirm={async () => {
          if (!remote) return;
          await call("connect.remove", { device_id: remote.device_id });
          await refresh();
          setSelected("this");
          setDetail(false);
        }}
      >
        <p>
          It disappears from Devices along with its activity and finished file
          transfers. Unsaved received files are deleted.
        </p>
        <p>OLIVE still remembers the revoked identity, so it stays blocked.</p>
      </Confirm>
      <Confirm
        open={clearingActivity}
        onOpenChange={setClearingActivity}
        title="Clear activity"
        action="Clear activity"
        onConfirm={async () => {
          if (!remote) return;
          await call("connect.activity_clear", { device_id: remote.device_id });
          await refresh();
        }}
      >
        <p>
          Deletes {activity.length === 1 ? "1 event" : `${activity.length} events`} for{" "}
          {remote?.display_name}. Pairing and permissions don’t change.
        </p>
      </Confirm>
    </section>
  );
}
