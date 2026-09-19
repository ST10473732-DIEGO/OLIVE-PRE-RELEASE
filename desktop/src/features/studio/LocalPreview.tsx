import { useEffect, useRef, useState } from "react";
import { Sheet } from "../../components/Sheet";
export function LocalPreview({
  sessionId,
  report,
}: {
  sessionId?: string;
  report: (e: unknown) => void;
}) {
  const [open, setOpen] = useState(false);
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => window.olive.onPreviewClosed(() => setOpen(false)), []);
  useEffect(() => {
    if (!open || !sessionId) return;
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
        .preview({ action: "open", session_id: sessionId, bounds })
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
  }, [open, sessionId]);
  return (
    <>
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
      <Sheet
        open={open}
        onOpenChange={setOpen}
        title="Local application preview"
        description="An isolated view of this active RunSession. It has no OLIVE bridge; unrelated network requests, new windows and downloads are blocked. Resizing closes the preview."
      >
        <div className="local-preview-host" ref={host} />
      </Sheet>
    </>
  );
}
