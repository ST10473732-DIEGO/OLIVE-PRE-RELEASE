import { useCallback, useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import {
  ArrowLeft,
  Laptop,
  Monitor,
  Plus,
  Radio,
  ShieldCheck,
  Wifi,
} from "lucide-react";
import { call } from "../../services/api";
import { Pairing } from "./Pairing";
import {
  deviceStatus,
  permissionGroups,
  type Device,
  type DevicesState,
  type PairingState,
  type SafeCapability,
} from "./types";
import "./devices.css";
const time = (value?: number) =>
  value ? new Date(value * 1000).toLocaleString() : "Not recorded";
export function Devices() {
  const [data, setData] = useState<DevicesState | null>(null),
    [error, setError] = useState(""),
    [selected, setSelected] = useState("this"),
    [detail, setDetail] = useState(false),
    [tab, setTab] = useState("status"),
    [busy, setBusy] = useState(false),
    [address, setAddress] = useState(""),
    [discovery, setDiscovery] = useState(false),
    [editing, setEditing] = useState(false),
    [name, setName] = useState(""),
    [pairing, setPairing] = useState<PairingState | null>(null),
    [revoke, setRevoke] = useState(false),
    [endpoint, setEndpoint] = useState(""),
    [port, setPort] = useState("");
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
      setBusy(false);
    }
  };
  const select = (id: string) => {
    setSelected(id);
    setDetail(true);
    setTab("status");
    setEndpoint("");
    setPort("");
  };
  const startPairing = () =>
    void act(async () =>
      setPairing(await call<PairingState>("connect.pair_create", {})),
    );
  const device =
    selected === "this"
      ? data?.local
      : data?.devices.find((d) => d.device_id === selected);
  const row = (d: Device, local = false) => (
    <button
      key={d.device_id}
      className={`devices-row ${selected === (local ? "this" : d.device_id) ? "selected" : ""}`}
      onClick={() => select(local ? "this" : d.device_id)}
    >
      <span className="devices-icon">
        <Monitor size={18} />
      </span>
      <span>
        <strong>{d.display_name}</strong>
        <small>
          {local
            ? `${d.public_identity_metadata?.os || d.platform} · Connect ${data?.network.state}`
            : deviceStatus(d)}
        </small>
      </span>
    </button>
  );
  const on = data?.network.state === "on";
  return (
    <section className="devices-workspace" aria-label="Devices workspace">
      <header className="devices-head">
        <span className="devices-icon accent">
          <Radio size={20} />
        </span>
        <div>
          <h1>Devices</h1>
          <p>OLIVE Connect · local pairing and permissions</p>
        </div>
        <span className="devices-pill">
          Connect {data?.network.state || "unavailable"}
        </span>
      </header>
      {error && (
        <div className="devices-error" role="alert">
          {error}
          <button onClick={() => void act(refresh)}>Retry</button>
        </div>
      )}
      {!data ? (
        <div className="devices-empty">Loading local device state…</div>
      ) : (
        <div className="devices-body" data-detail={detail}>
          <aside className="devices-rail" aria-label="Device list">
            <div className="devices-rail-head">
              <strong>Devices</strong>
              <button
                className="icon-button"
                aria-label="Connect a device"
                disabled={busy}
                onClick={startPairing}
              >
                <Plus size={18} />
              </button>
            </div>
            <div className="devices-rail-scroll">
              <p className="devices-eyebrow">This device</p>
              {row(data.local, true)}
              <p className="devices-eyebrow">Paired</p>
              {data.devices.map((d) => row(d))}
              {!data.devices.length && (
                <div className="devices-rail-empty">
                  No paired devices yet.
                  <button onClick={startPairing} disabled={busy}>
                    Connect first device
                  </button>
                </div>
              )}
              <p className="devices-eyebrow">Nearby</p>
              {!data.nearby.length && (
                <p className="devices-rail-empty">
                  No nearby OLIVE devices found.
                  {!data.network.discovery && " Nearby discovery is off."}
                </p>
              )}
              {data.nearby.map((n) => (
                <button
                  className="devices-row unpaired"
                  key={n.instance}
                  onClick={() => {
                    select("nearby");
                    setEndpoint(n.address);
                    setPort(String(n.port));
                  }}
                >
                  <span className="devices-icon">
                    <Radio size={18} />
                  </span>
                  <span>
                    <strong>OLIVE device</strong>
                    <small>{n.address} · Discovered · Unpaired</small>
                  </span>
                </button>
              ))}
            </div>
            <footer className="devices-rail-foot">
              <Radio size={17} />
              <span>
                <strong>OLIVE Connect</strong>
                <small>
                  {on
                    ? `${data.network.interface?.name} · ${data.network.interface?.address}`
                    : "Off — not reachable"}
                </small>
              </span>
              <button
                aria-label={on ? "Turn Connect off" : "Set up Connect"}
                disabled={busy}
                onClick={() =>
                  on
                    ? void act(() => call("connect.disable", {}))
                    : select("this")
                }
              >
                {on ? "Off" : "Set up"}
              </button>
            </footer>
          </aside>
          <main className="devices-main">
            <div className="devices-main-inner">
              <button
                className="devices-back quiet"
                onClick={() => setDetail(false)}
              >
                <ArrowLeft size={16} />
                Back to devices
              </button>
              {selected === "nearby" ? (
                <>
                  <h2>Discovered OLIVE device</h2>
                  <span className="devices-pill">Unpaired · Untrusted</span>
                  <p>
                    Discovery does not verify identity. Pairing requires both
                    devices to compare and confirm the same value.
                  </p>
                  <p>
                    {endpoint}:{port}
                  </p>
                  <button onClick={startPairing} disabled={busy}>
                    Create pairing offer
                  </button>
                </>
              ) : (
                device && (
                  <>
                    <div className="devices-detail-head">
                      <span className="devices-icon large">
                        <Laptop size={26} />
                      </span>
                      <div>
                        <h2>{device.display_name}</h2>
                        <div className="devices-meta">
                          <span className="devices-pill">
                            {selected === "this"
                              ? "This device"
                              : deviceStatus(device)}
                          </span>
                          <span>
                            {device.device_class} ·{" "}
                            {device.public_identity_metadata?.os ||
                              device.platform}
                          </span>
                          {device.live?.encrypted &&
                            device.live.state === "online" &&
                            device.trust_state === "paired" && (
                              <span className="devices-tls">
                                <ShieldCheck size={14} />
                                Encrypted · TLS 1.3
                              </span>
                            )}
                        </div>
                      </div>
                    </div>
                    {selected === "this" ? (
                      <>
                        <div className="devices-panel">
                          <header>
                            <div>
                              <h3>OLIVE Connect</h3>
                              <p>
                                Lets paired devices reach this computer on your
                                local network.
                              </p>
                            </div>
                            <span className="devices-pill">
                              {busy ? "Working" : data.network.state}
                            </span>
                          </header>
                          <div className="devices-panel-body">
                            {!on && (
                              <p className="devices-notice">
                                Connect is off. Select a local interface
                                explicitly before turning it on. It stays off
                                after restarting OLIVE.
                              </p>
                            )}
                            {data.network.error && (
                              <p role="alert">
                                Could not start Connect:{" "}
                                {data.network.error.replaceAll("_", " ")}. Check
                                the selected interface, secure key store and
                                local firewall.
                              </p>
                            )}
                            <p className="devices-eyebrow">Local interface</p>
                            <div className="devices-interfaces">
                              {data.interfaces.map((i) => (
                                <button
                                  key={i.address}
                                  aria-pressed={
                                    address === i.address ||
                                    (on &&
                                      data.network.interface?.address ===
                                        i.address)
                                  }
                                  disabled={on || busy}
                                  className="devices-interface"
                                  onClick={() => setAddress(i.address)}
                                >
                                  <Wifi size={18} />
                                  <span>
                                    <strong>{i.name}</strong>
                                    <small>{i.address}</small>
                                  </span>
                                </button>
                              ))}
                            </div>
                            {!data.interfaces.length && (
                              <p>
                                No approved local interfaces available.{" "}
                                {data.interface_error?.replaceAll("_", " ")}
                              </p>
                            )}
                            <label className="devices-check">
                              <input
                                type="checkbox"
                                checked={
                                  on ? data.network.discovery : discovery
                                }
                                disabled={on || busy}
                                onChange={(e) => setDiscovery(e.target.checked)}
                              />
                              Nearby discovery
                              <small>
                                Advertise this device on the selected network.
                              </small>
                            </label>
                            <button
                              className="primary"
                              disabled={
                                busy ||
                                (!on &&
                                  !data.interfaces.some(
                                    (i) => i.address === address,
                                  ))
                              }
                              onClick={() =>
                                void act(() =>
                                  on
                                    ? call("connect.disable", {})
                                    : call("connect.enable", {
                                        address,
                                        discovery,
                                      }),
                                )
                              }
                            >
                              {on ? "Turn Connect off" : "Turn Connect on"}
                            </button>
                            <p className="muted">
                              To change interface or discovery, turn Connect off
                              first. OLIVE does not alter your firewall.
                            </p>
                          </div>
                        </div>
                        <div className="devices-panel">
                          <div className="devices-panel-body">
                            <h3>This Device</h3>
                            <p>
                              OLIVE Core{" "}
                              {device.core_available
                                ? "available"
                                : "unavailable"}
                            </p>
                            {editing ? (
                              <form
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
                                    value={name}
                                    maxLength={100}
                                    onChange={(e) => setName(e.target.value)}
                                  />
                                </label>
                                <button disabled={busy || !name.trim()}>
                                  Save name
                                </button>
                              </form>
                            ) : (
                              <button
                                onClick={() => {
                                  setName(device.display_name);
                                  setEditing(true);
                                }}
                              >
                                Edit display name
                              </button>
                            )}
                          </div>
                        </div>
                        <details className="devices-disclosure">
                          <summary>Advanced details</summary>
                          <dl>
                            <dt>Device ID</dt>
                            <dd>{device.device_id}</dd>
                            <dt>Fingerprint</dt>
                            <dd>
                              {device.fingerprint ||
                                "Not provisioned. Created through the secure vault when you enable Connect or create pairing."}
                            </dd>
                            <dt>Protocol</dt>
                            <dd>{data.protocol}</dd>
                            <dt>Selected interface</dt>
                            <dd>{data.network.interface?.address || "None"}</dd>
                            <dt>Connect port</dt>
                            <dd>{data.network.port || "Not listening"}</dd>
                          </dl>
                          <p>
                            Only the selected Connect TCP port and local mDNS
                            UDP 5353 are relevant to firewall configuration. Do
                            not open Ollama or Studio ports.
                          </p>
                        </details>
                      </>
                    ) : (
                      <>
                        <div
                          className="devices-tabs"
                          role="group"
                          aria-label="Device details"
                        >
                          {["status", "permissions", "activity"].map((t) => (
                            <button
                              key={t}
                              aria-pressed={tab === t}
                              onClick={() => setTab(t)}
                            >
                              {t[0].toUpperCase() + t.slice(1)}
                            </button>
                          ))}
                        </div>
                        {tab === "status" && (
                          <div className="devices-panel">
                            <div className="devices-panel-body">
                              {device.trust_state === "revoked" ? (
                                <p className="devices-notice">
                                  Revoked · disconnected. This identity cannot
                                  reconnect. Re-pairing this revoked identity is
                                  not supported; its security history is
                                  retained.
                                </p>
                              ) : (
                                <>
                                  <dl>
                                    <dt>Trust</dt>
                                    <dd>Paired</dd>
                                    <dt>Connection</dt>
                                    <dd>{deviceStatus(device)}</dd>
                                    <dt>Paired since</dt>
                                    <dd>{time(device.paired_at)}</dd>
                                    <dt>Last seen</dt>
                                    <dd>{time(device.last_seen)}</dd>
                                  </dl>
                                  {device.live?.error && (
                                    <p role="alert">
                                      {device.live.error.replaceAll("_", " ")}.
                                      Check Connect is enabled on both devices,
                                      the paired identity and selected
                                      interface/port firewall rules.
                                    </p>
                                  )}
                                  {device.live?.state === "online" ? (
                                    <div className="devices-actions">
                                      <button
                                        disabled={busy}
                                        onClick={() =>
                                          void act(async () => {
                                            const r = await call<{
                                              state: string;
                                              error?: string;
                                            }>("connect.ping", {
                                              device_id: device.device_id,
                                            });
                                            if (r.state !== "completed")
                                              throw new Error(
                                                (r.error ===
                                                "confirmation_required"
                                                  ? "Waiting for approval on the other device. After approval, select Measure latency again to retry this exact request."
                                                  : r.error?.replaceAll(
                                                      "_",
                                                      " ",
                                                    )) || "Ping not completed",
                                              );
                                          })
                                        }
                                      >
                                        Measure latency
                                      </button>
                                      <button
                                        disabled={busy}
                                        onClick={() =>
                                          void act(() =>
                                            call("connect.disconnect", {
                                              device_id: device.device_id,
                                            }),
                                          )
                                        }
                                      >
                                        Disconnect
                                      </button>
                                    </div>
                                  ) : (
                                    <form
                                      onSubmit={(e) => {
                                        e.preventDefault();
                                        void act(() =>
                                          call("connect.open", {
                                            device_id: device.device_id,
                                            address: endpoint,
                                            port: Number(port),
                                          }),
                                        );
                                      }}
                                    >
                                      <p>
                                        Choose the paired device’s local Connect
                                        endpoint. Its identity is verified again
                                        before connecting.
                                      </p>
                                      {data.nearby.length > 0 && (
                                        <label>
                                          Discovered endpoint (untrusted)
                                          <select
                                            value=""
                                            onChange={(e) => {
                                              const n = data.nearby.find(
                                                (n) =>
                                                  n.instance === e.target.value,
                                              );
                                              if (n) {
                                                setEndpoint(n.address);
                                                setPort(String(n.port));
                                              }
                                            }}
                                          >
                                            <option value="">
                                              Choose endpoint
                                            </option>
                                            {data.nearby.map((n) => (
                                              <option
                                                key={n.instance}
                                                value={n.instance}
                                              >
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
                                          onChange={(e) =>
                                            setEndpoint(e.target.value)
                                          }
                                        />
                                      </label>
                                      <label>
                                        Connect port
                                        <input
                                          type="number"
                                          min={1}
                                          max={65535}
                                          value={port}
                                          onChange={(e) =>
                                            setPort(e.target.value)
                                          }
                                        />
                                      </label>
                                      <button
                                        disabled={
                                          !on || busy || !endpoint || !port
                                        }
                                      >
                                        Connect
                                      </button>
                                    </form>
                                  )}
                                </>
                              )}
                            </div>
                            {device.trust_state !== "revoked" && (
                              <footer>
                                <span>
                                  Removing access takes effect immediately.
                                </span>
                                <button
                                  className="danger"
                                  onClick={() => setRevoke(true)}
                                >
                                  Revoke device
                                </button>
                              </footer>
                            )}
                          </div>
                        )}
                        {tab === "permissions" && (
                          <div className="devices-panel">
                            {device.trust_state === "revoked" && (
                              <p className="devices-notice">
                                Permissions are inactive for this revoked
                                device.
                              </p>
                            )}
                            {permissionGroups.map(([group, items]) => (
                              <section
                                className="devices-permission-group"
                                key={group}
                              >
                                <h3 className="devices-eyebrow">{group}</h3>
                                {items.map(([cap, label]) => {
                                  const metadata = data.capabilities.find(
                                    (c) => c.capability === cap,
                                  );
                                  if (!metadata) return null;
                                  const available =
                                    metadata.supported &&
                                    !metadata.policy_disabled &&
                                    [
                                      "connect.ping",
                                      "device.status",
                                      "chat.metadata.read",
                                    ].includes(cap);
                                  const decision =
                                    device.permissions?.find(
                                      (p) =>
                                        p.capability === cap &&
                                        p.scope === null,
                                    )?.decision || "deny";
                                  return (
                                    <div
                                      className="devices-permission"
                                      key={cap}
                                    >
                                      <span>
                                        <strong>{label}</strong>
                                        {!available && (
                                          <small>Not yet available</small>
                                        )}
                                      </span>
                                      {available ? (
                                        <div
                                          className="devices-permission-seg"
                                          role="group"
                                          aria-label={label}
                                        >
                                          {(
                                            ["allow", "ask", "deny"] as const
                                          ).map((v) => (
                                            <button
                                              data-value={v}
                                              aria-pressed={v === decision}
                                              disabled={
                                                busy ||
                                                device.trust_state === "revoked"
                                              }
                                              key={v}
                                              onClick={() =>
                                                void act(() =>
                                                  call("connect.permission", {
                                                    device_id: device.device_id,
                                                    capability:
                                                      cap as SafeCapability,
                                                    decision: v,
                                                  }),
                                                )
                                              }
                                            >
                                              {v === "deny"
                                                ? "Off"
                                                : v === "ask"
                                                  ? "Ask"
                                                  : "Allow"}
                                            </button>
                                          ))}
                                        </div>
                                      ) : (
                                        <span className="devices-unavailable">
                                          Unavailable
                                        </span>
                                      )}
                                    </div>
                                  );
                                })}
                              </section>
                            ))}
                          </div>
                        )}
                        {tab === "activity" && (
                          <div className="devices-panel">
                            <ol className="devices-timeline">
                              {data.activity
                                .filter(
                                  (a) =>
                                    a.source_device_id === device.device_id,
                                )
                                .reverse()
                                .map((a) => (
                                  <li key={a.id}>
                                    <span>
                                      {a.result_state.replaceAll("_", " ")}
                                      {a.capability ? ` · ${a.capability}` : ""}
                                    </span>
                                    <time
                                      dateTime={new Date(
                                        a.timestamp * 1000,
                                      ).toISOString()}
                                    >
                                      {time(a.timestamp)}
                                    </time>
                                  </li>
                                ))}
                            </ol>
                            {!data.activity.some(
                              (a) => a.source_device_id === device.device_id,
                            ) && (
                              <p className="devices-rail-empty">
                                No device activity yet.
                              </p>
                            )}
                            <footer>
                              Connection and permission events only. No message
                              or file content.
                            </footer>
                          </div>
                        )}
                      </>
                    )}
                  </>
                )
              )}
            </div>
          </main>
        </div>
      )}
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
            <Dialog.Title>Revoke device</Dialog.Title>
            <Dialog.Description>
              This device will lose OLIVE Connect access immediately. The
              revocation is permanent for this identity.
            </Dialog.Description>
            <p className="devices-notice">
              {device?.display_name} will be disconnected right away.
            </p>
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
    </section>
  );
}
