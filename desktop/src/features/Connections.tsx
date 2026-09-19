import { useEffect, useRef, useState } from "react";
import { Sheet } from "../components/Sheet";
import { call } from "../services/api";
interface Status {
  enabled: boolean | null;
  server: string | null;
  channel: string | null;
  bot_name: string | null;
  guild_id: string | null;
  channel_id: string | null;
}
export function Connections({
  open,
  close,
  report,
}: {
  open: boolean;
  close: (value: boolean) => void;
  report: (e: unknown) => void;
}) {
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);
  const [guilds,setGuilds]=useState<{id:string;name:string}[]>([]);
  const [channels,setChannels]=useState<{id:string;name:string;can_send:boolean}[]>([]);
  const [selectedGuild,setSelectedGuild]=useState('');
  const discover=async(guild_id?:string)=>{
    setBusy(true);
    try {const result=await call<{guilds:{id:string;name:string}[];channels:{id:string;name:string;can_send:boolean}[]}>('connections.discord_destinations',guild_id?{guild_id}:{});if(!guild_id)setGuilds(result.guilds);setChannels(result.channels);}
    catch(e){report(e);}finally{setBusy(false);}
  };
  const secret = useRef<HTMLInputElement>(null);
  const guild = useRef<HTMLInputElement>(null);
  const channel = useRef<HTMLInputElement>(null);
  const inFlight = useRef(false);
  useEffect(() => {
    if (open)
      void call<Status>("connections.discord_status", {})
        .then(setStatus)
        .catch(report);
  }, [open]);
  return (
    <Sheet
      open={open}
      onOpenChange={close}
      title="Connections"
      description="Optional services. Your local OLIVE features do not require an account."
    >
      <h3>Discord application bot</h3>
      <p>
        {status?.enabled
          ? `Configured as ${status.bot_name} for #${status.channel} on ${status.server}.`
          : "Discord delivery is not configured."}
      </p>
      <p className="muted">
        Messages are sent as your bot, not as your personal Discord account.
        Each send requires review of the exact destination and text. Personal
        Discord accounts require manual sending; OLIVE can retain your draft but
        cannot automate a normal account. Only the configured bot channel is used.
      </p>
      <form
        className="project-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (inFlight.current) return;
          inFlight.current = true;
          setBusy(true);
          const request = call<Status>("connections.discord_configure", {
            token: secret.current!.value,
            guild_id: guild.current!.value,
            channel_id: channel.current!.value,
          });
          secret.current!.value = "";
          void request
            .then(setStatus)
            .catch(report)
            .finally(() => {
              inFlight.current = false;
              setBusy(false);
            });
        }}
      >
        <label>
          Bot token
          <input
            ref={secret}
            type="password"
            autoComplete="off"
            spellCheck={false}
            required
            disabled={busy}
          />
        </label>
        <label>
          Server ID
          <input
            ref={guild}
            inputMode="numeric"
            pattern="[0-9]{1,22}"
            required
            disabled={busy}
          />
        </label>
        <label>
          Text channel ID
          <input
            ref={channel}
            inputMode="numeric"
            pattern="[0-9]{1,22}"
            required
            disabled={busy}
          />
        </label>
        <button className="primary" disabled={busy}>
          {busy ? "Checking connection…" : "Connect this channel"}
        </button>
        <p className="small muted">
          Connection checks do not send messages. Credentials are kept in
          Windows Credential Manager, outside portable backups. This does not
          protect against every process running as your Windows user.
        </p>
      </form>
      {status?.enabled&&<div className="project-form">
        <button disabled={busy} onClick={()=>void discover()}>List accessible bot destinations</button>
        {!!guilds.length&&<label>Server<select value={selectedGuild} onChange={e=>{setSelectedGuild(e.target.value);void discover(e.target.value);}}><option value="">Select an accessible server</option>{guilds.map(g=><option key={g.id} value={g.id}>{g.name}</option>)}</select></label>}
        {channels.map(c=><button key={c.id} disabled={busy||!c.can_send} onClick={()=>{setBusy(true);void call<Status>('connections.discord_select',{guild_id:selectedGuild,channel_id:c.id}).then(setStatus).catch(report).finally(()=>setBusy(false));}}>Use #{c.name}{!c.can_send?' · read only':''}</button>)}
      </div>}
      {status?.enabled && (
        <button
          disabled={busy}
          onClick={() =>
            void call<Status>("connections.discord_disconnect", {
              remove_credentials: false,
            })
              .then(setStatus)
              .catch(report)
          }
        >
          Disconnect
        </button>
      )}
      <button
        disabled={busy}
        onClick={() =>
          void call<Status>("connections.discord_disconnect", {
            remove_credentials: true,
          })
            .then(setStatus)
            .catch(report)
        }
      >
        Disconnect and remove credential
      </button>
    </Sheet>
  );
}
