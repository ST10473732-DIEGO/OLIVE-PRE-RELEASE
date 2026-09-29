import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Sheet } from "../../components/Sheet";

/**
 * Isolated preview of an OLIVE-owned loopback run (Electron WebContentsView,
 * no bridge, origin-locked). Opened from its button, or programmatically via
 * openRequest (Chat's "Open preview"). While open it reloads when an OLIVE
 * task edits the project or restarts its server.
 */
export function LocalPreview({
  sessionId,
  report,
  openRequest,
  workspaceId,
  trigger = true,
}: {
  sessionId?: string;
  report: (e: unknown) => void;
  openRequest?: { session: string; revision: number };
  workspaceId?: string;
  trigger?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [session, setSession] = useState(sessionId);
  const [revision, setRevision] = useState(0);
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => window.olive.onPreviewClosed(() => setOpen(false)), []);
  useEffect(() => {
    if (!open) setSession(sessionId);
  }, [sessionId, open]);
  useEffect(() => {
    if (!openRequest?.session) return;
    setSession(openRequest.session);
    setOpen(true);
  }, [openRequest?.revision]);
  useEffect(() => {
    if (!open || !workspaceId) return;
    return window.olive.subscribe((event) => {
      const data = event.data as { workspace_id?: string; session_id?: string };
      if (data.workspace_id !== workspaceId) return;
      if (event.topic === "studio.preview_ready" && data.session_id) {
        setSession(data.session_id);
        setRevision((n) => n + 1);
      }
      if (event.topic === "studio.preview_refresh" || event.topic === "studio.files_changed") setRevision((n) => n + 1);
    });
  }, [open, workspaceId]);
  useEffect(() => {
    if (!open || !session) return;
    let stale = false;
    const frame = requestAnimationFrame(() => {
      if (!host.current) return;
      const rect = host.current.getBoundingClientRect();
      const bounds = {
        x: Math.ceil(rect.x),
        y: Math.ceil(rect.y),
        width: Math.floor(rect.width) - 1,
        height: Math.floor(rect.height) - 1,
      };
      void window.olive
        .preview({ action: "open", session_id: session, bounds })
        .catch((error) => {
          if (!stale) {
            setOpen(false);
            report(error);
          }
        });
    });
    return () => {
      stale = true;
      cancelAnimationFrame(frame);
      void window.olive.preview({ action: "close" }).catch(report);
    };
  }, [open, session, revision]);
  return (
    <>
      {trigger && (
        <button
          disabled={!sessionId}
          title={
            sessionId
              ? "Verify and preview this run’s local web origin"
              : "Start a local web application first"
          }
          onClick={() => setOpen(true)}
        >
          Local app preview
        </button>
      )}
      <Sheet
        open={open}
        onOpenChange={setOpen}
        title="Local application preview"
        description="An isolated view of this active RunSession. It has no OLIVE bridge; unrelated network requests, new windows and downloads are blocked. Resizing closes the preview."
      >
        <div className="local-preview-bar">
          <button className="quiet compact" onClick={() => setRevision((n) => n + 1)} title="Reload the preview">
            <RefreshCw size={13} aria-hidden="true" /> Refresh
          </button>
        </div>
        <div className="local-preview-host" ref={host} />
      </Sheet>
    </>
  );
}
