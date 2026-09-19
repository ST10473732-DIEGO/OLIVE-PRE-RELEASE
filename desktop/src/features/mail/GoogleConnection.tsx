import { useEffect } from "react";
import { call } from "../../services/api";
import { useResource } from "../../services/useResource";
import { Feedback, useOperation } from "../personal/shared";

export default function GoogleConnection({onAuthorized}: {onAuthorized: () => Promise<void>}) {
  const status = useResource(() => call<{configured: boolean; state: string; connection_id: string}>("mail.google_status", {}), ["mail.changed"]);
  const op = useOperation(status.refresh);
  useEffect(() => {
    if (status.data?.state !== "awaiting_browser") return;
    const timer = setInterval(() => status.refresh(), 1500);
    return () => clearInterval(timer);
  }, [status.data?.state, status.refresh]);
  useEffect(() => {
    if (status.data?.state === "authorized_needs_enable") void onAuthorized();
  }, [status.data?.state, status.data?.connection_id, onAuthorized]);
  return <section aria-label="Google Mail setup">
    <h3>Gmail accounts</h3>
    <p>{status.data?.configured ? `Desktop client configured · ${status.data.state.replaceAll("_", " ")}` : "Needs setup: registered Google Desktop app client"}</p>
    <details><summary>Google setup checklist</summary>
      <ol>
        <li>In Google Cloud Console, create/select your project and enable the Gmail API.</li>
        <li>Configure Google Auth Platform branding, audience and data access for https://mail.google.com/. Add your own accounts as test users while testing. Public use of this restricted scope requires Google's applicable verification.</li>
        <li>Create an OAuth client with application type Desktop app, download its JSON, and import it here. OLIVE stores the client credential in the OS vault.</li>
        <li>Choose Authorize Gmail account and finish consent in your system browser. Repeat for each account. Then enable the account and run its connection test. Tests do not send mail.</li>
      </ol>
      <p>Testing-mode authorizations may expire. Reauthorize when Google revokes or expires access. Remove OLIVE's grant from your Google Account security settings to revoke it at the provider.</p>
    </details>
    <div className="row wrap">
      <button disabled={op.busy || status.data?.state === "awaiting_browser"} onClick={() => void op.run(() => window.olive.fileAction({action: "mail-google-client"}), "Client setup checked.")}>Import Google desktop client</button>
      <button disabled={!status.data?.configured || op.busy || status.data.state === "awaiting_browser"} onClick={() => void op.run(() => call("mail.google_begin", {}), "Finish authorization in the system browser.")}>Authorize Gmail account</button>
      {status.data?.state === "awaiting_browser" && <button onClick={() => void op.run(() => call("mail.google_cancel", {}), "Authorization cancelled.")}>Cancel Google authorization</button>}
    </div>
    <Feedback error={op.error || status.error} notice={op.notice} />
  </section>;
}
