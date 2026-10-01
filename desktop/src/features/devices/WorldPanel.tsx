import { useState } from "react";
import { Globe2 } from "lucide-react";
import { call } from "../../services/api";
import type { Device, DevicesState } from "./types";
import { byteLabel, worldDeviceLabel, worldSummary } from "./types";
import { ago, fullTime, sentence } from "./ui";

/** OLIVE Connect World: reach this computer from anywhere through an outbound relay.
 * Ordinary copy stays plain; relay details live under Advanced. Never shows secrets. */
export function WorldPanel({ data, act }: { data: DevicesState; act: (work: () => Promise<unknown>) => void }) {
  const world = data.world;
  const [url, setUrl] = useState("");
  if (!world) return null; // An older backend has no World.
  const summary = worldSummary(world);
  return (
    <section className="devices-card" aria-label="OLIVE Connect World">
      <header className="devices-card-head">
        <div>
          <h3>
            <Globe2 size={15} aria-hidden="true" /> OLIVE Connect World
          </h3>
          <p>Reach this computer securely when you’re away from your local network.</p>
        </div>
        <span className="devices-pill" data-tone={world.enabled ? summary.tone : undefined} role="status">
          {world.enabled ? summary.label : "Off"}
        </span>
      </header>
      <label className="devices-toggle">
        <input
          type="checkbox"
          className="switch"
          checked={world.enabled}
          aria-label="OLIVE Connect World"
          onChange={(e) => act(() => call("connect.world_set", { enabled: e.target.checked }))}
        />
        <span>
          {world.enabled ? "On" : "Off"}
          <small>{world.enabled ? summary.detail : "Paired devices connect on your local network only."}</small>
        </span>
      </label>
      <details className="devices-advanced">
        <summary>Advanced</summary>
        <dl className="devices-facts">
          <div>
            <dt>Relay</dt>
            <dd>{world.relay_host ?? "Not configured"}</dd>
          </div>
          <div>
            <dt>Relay status</dt>
            <dd>{sentence(world.relay)}</dd>
          </div>
          <div>
            <dt>Protocol</dt>
            <dd>{world.protocol}</dd>
          </div>
        </dl>
        {world.error && <p className="devices-hint">Last error: {sentence(world.error)}.</p>}
        <form
          className="devices-endpoint"
          onSubmit={(e) => {
            e.preventDefault();
            act(async () => {
              await call("connect.world_relay", { url: url.trim() });
              setUrl("");
            });
          }}
        >
          <label>
            Relay URL
            <input
              value={url}
              placeholder="wss://relay.example.com"
              maxLength={256}
              spellCheck={false}
              onChange={(e) => setUrl(e.target.value)}
            />
          </label>
          <button disabled={!/^wss?:\/\/\S+$/.test(url.trim())}>Use relay</button>
          {world.relay_custom && (
            <button type="button" className="quiet" onClick={() => act(() => call("connect.world_relay", {}))}>
              {world.managed ? "Use default" : "Remove"}
            </button>
          )}
        </form>
        <p className="devices-hint">
          The relay passes along encrypted traffic between your paired devices. It cannot read your chats, notes,
          drawings or files. It can see when devices connect and how much data moves. AI still runs on this computer.
        </p>
      </details>
    </section>
  );
}

/** One paired device's World row: plain state, then counters under Advanced. */
export function WorldDeviceFacts({ device, data, act }: {
  device: Device; data: DevicesState; act: (work: () => Promise<unknown>) => void;
}) {
  if (!data.world || device.trust_state === "revoked") return null;
  const world = device.world;
  return (
    <details className="devices-advanced" aria-label="OLIVE Connect World for this device">
      <summary>OLIVE Connect World · {worldDeviceLabel(world, data.world)}</summary>
      {world ? (
        <>
          <dl className="devices-facts">
            <div>
              <dt>Last World connection</dt>
              <dd>
                {world.last_connected_at ? (
                  <span title={fullTime(world.last_connected_at)}>{ago(world.last_connected_at)}</span>
                ) : (
                  "Never"
                )}
              </dd>
            </div>
            <div>
              <dt>Through relay</dt>
              <dd>
                {byteLabel(world.bytes_in)} in · {byteLabel(world.bytes_out)} out
              </dd>
            </div>
            <div>
              <dt>Reconnects</dt>
              <dd>{world.reconnects}</dd>
            </div>
          </dl>
          {world.error && <p className="devices-hint">Last error: {sentence(world.error)}.</p>}
          {world.provisioned && (
            <button
              className="quiet"
              onClick={() => act(() => call("connect.world_rotate", { device_id: device.device_id }))}
            >
              Rotate World route
            </button>
          )}
        </>
      ) : (
        <p className="devices-hint">This device sets itself up the next time it connects on your local network.</p>
      )}
    </details>
  );
}
