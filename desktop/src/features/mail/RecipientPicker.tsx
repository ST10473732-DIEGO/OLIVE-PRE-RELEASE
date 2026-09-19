import { useState } from "react";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";

export default function RecipientPicker({select}: {select: (address: string) => void}) {
  const [query, setQuery] = useState("");
  const r = useResource(() => query.trim().length >= 2
    ? call<{items: {address: string; name: string}[]}>("mail.recipients", {query})
    : Promise.resolve({items: []}), [], query);
  return <details className="mail-recipient-picker">
    <summary>Recent recipients and participants</summary>
    <input aria-label="Find recent recipient" placeholder="Name or email address"
      value={query} onChange={e => setQuery(e.target.value)} />
    <p>Choose an exact address, or enter one in To. Message participants are not verified identities.</p>
    {r.data?.items.map(item => <button key={item.address} onClick={() => {select(item.address); setQuery("");}}>
      {item.name ? item.name + " - " : ""}{item.address}
    </button>)}
    {r.error && <p role="alert">{r.error}</p>}
  </details>;
}
