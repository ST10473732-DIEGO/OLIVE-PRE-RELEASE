import { createContext, useLayoutEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { featureById, type Space } from "../navigation/features";

/** A view rendered inside a multi-view space hands its header actions to the
 *  space header. `active` is true only for the visible view, so hidden
 *  (still mounted) views never portal their controls. */
export const SpaceSlot = createContext<{ target: HTMLElement | null; active: boolean } | null>(null);

export function SpacePortal({ target, active, children }: { target: HTMLElement | null; active: boolean; children: ReactNode }) {
  return active && target ? createPortal(children, target) : null;
}

const DESCRIPTIONS: Record<string, string> = {
  plan: "Your calendar, tasks and reminders, on this device.",
  library: "What OLIVE knows: your documents, remembered facts and projects.",
  build: "Give OLIVE an objective, or write and run code yourself.",
  drawnote: "Your notes and drawings, stored on this device.",
};

// The Grove space header: the space's title and one line of context, the
// current view's actions on the right, and the views as tabs underneath with
// one underline that slides between them.
export function SpaceHeader({
  space,
  route,
  navigate,
  setActions,
}: {
  space: Space;
  route: string;
  navigate: (id: string) => void;
  setActions: (element: HTMLElement | null) => void;
}) {
  const tabs = useRef<HTMLDivElement>(null);
  const line = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const place = () => {
      const selected = tabs.current?.querySelector<HTMLElement>('[aria-selected="true"]');
      if (!selected || !line.current) return;
      line.current.style.transform = `translateX(${selected.offsetLeft + 10}px)`;
      line.current.style.width = `${Math.max(0, selected.offsetWidth - 20)}px`;
    };
    place();
    const ready = requestAnimationFrame(() => line.current?.setAttribute("data-ready", "true"));
    window.addEventListener("resize", place);
    return () => {
      cancelAnimationFrame(ready);
      window.removeEventListener("resize", place);
    };
  }, [route, space.id]);
  return (
    <div className="space-header">
      <div className="ph">
        <div className="ph-text">
          <p className="ph-title" aria-hidden="true">{space.label}</p>
          <p className="ph-sub">{DESCRIPTIONS[space.id]}</p>
        </div>
        <div className="ph-actions" ref={setActions} />
      </div>
      <div className="space-tabs" role="tablist" aria-label={`${space.label} views`} ref={tabs}>
        {space.routes.map((id) => (
          <button
            key={id}
            role="tab"
            aria-selected={route === id}
            tabIndex={route === id ? 0 : -1}
            onClick={() => navigate(id)}
            onKeyDown={(event) => {
              if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
              event.preventDefault();
              const index = space.routes.indexOf(route);
              const next = space.routes[(index + (event.key === "ArrowRight" ? 1 : -1) + space.routes.length) % space.routes.length];
              navigate(next);
              requestAnimationFrame(() => tabs.current?.querySelector<HTMLElement>('[aria-selected="true"]')?.focus());
            }}
          >
            {featureById(id)?.view ?? featureById(id)?.label}
          </button>
        ))}
        <span className="space-tab-line" ref={line} aria-hidden="true" />
      </div>
    </div>
  );
}
