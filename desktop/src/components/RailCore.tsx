import { useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { motion } from "motion/react";
import { Core } from "./Core";

// The shared-layout projection is decorative. Keep its travelling geometry out
// of the navigation pane instead of suppressing the pane's overflow; the Core is
// drawn at exactly the anchor's size so it never spills out of its row.
export function RailCore({ state }: { state: string }) {
  const anchor = useRef<HTMLSpanElement>(null);
  const [position, setPosition] = useState<{
    left: number;
    top: number;
    size: number;
  }>();
  useLayoutEffect(() => {
    const node = anchor.current;
    if (!node) return;
    const measure = () => {
      const rect = node.getBoundingClientRect();
      setPosition({ left: rect.left, top: rect.top, size: rect.width });
    };
    measure();
    const observer = new ResizeObserver(measure);
    // The anchor lives in the navigation pane or the narrow bar; observe
    // whichever container it actually has rather than assuming a <nav>.
    const container = node.closest("nav, header") || node.parentElement;
    if (container) observer.observe(container);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, []);
  return (
    <>
      <span ref={anchor} className="core-anchor" aria-hidden="true" />
      {position &&
        createPortal(
          <div className="core-transit-stage" aria-hidden="true">
            <motion.div
              layoutId="core"
              layout="position"
              style={{
                position: "absolute",
                left: position.left,
                top: position.top,
                width: position.size,
                height: position.size,
              }}
            >
              <Core state={state} />
            </motion.div>
          </div>,
          document.body,
        )}
    </>
  );
}
