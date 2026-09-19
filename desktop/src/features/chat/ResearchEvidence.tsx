import { lazy, Suspense, useState } from "react";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import { Sheet } from "../../components/Sheet";
import type { ResearchSession } from "../research/types";
const Research = lazy(() => import("../research/Research"));

export function ResearchEvidence({ chatId, sessionIds, report }: {chatId: string; sessionIds: string[]; report: (error: unknown) => void}) {
  const [history, setHistory] = useState(false);
  const id = sessionIds.at(-1);
  const detail = useResource(() => id ? call<ResearchSession>("research.get", {session_id: id}) : Promise.resolve(undefined), ["research"], id || "");
  const session = detail.data;
  return <div className="research-evidence">
    <button className="quiet" onClick={() => setHistory(true)}>Saved research & evidence</button>
    {session && <details open={session.status === "running"}>
      <summary>{session.question} · {session.status} · {session.sources.length} {session.sources.length === 1 ? "source" : "sources"}</summary>
      <p role="status">{session.activity || session.error}</p>
      {session.findings.slice(-6).map((finding, index) => <p key={index}>{finding.text}</p>)}
      <ul>{session.sources.map(source => <li key={source.id}>
        <details><summary>{source.title || source.domain} · {source.status}</summary>
          <p>{source.url}</p>
          {session.evidence.filter(e => e.source_id === source.id).slice(0, 8).map(e => <blockquote key={e.id}>{e.quote || e.claim}</blockquote>)}
        </details>
      </li>)}</ul>
    </details>}
    {detail.error && <p role="status">{detail.error}</p>}
    <Sheet open={history} onOpenChange={setHistory} title="Research history" description="Saved sessions, original sources, evidence and project links.">
      <Suspense fallback={<p>Opening research evidence…</p>}><Research key={chatId} chatId={chatId} report={report} target={id ? {id, revision: 1} : undefined}/></Suspense>
    </Sheet>
  </div>;
}
