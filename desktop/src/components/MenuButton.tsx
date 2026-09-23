import { useEffect, useId, useRef, useState, type ReactNode } from "react";

export interface MenuItem {
  id: string;
  label: string;
  icon?: ReactNode;
  detail?: string;
  current?: boolean;
  disabled?: boolean;
  onSelect: () => void;
}

// A small keyboard-accessible menu (V2 §11 menu: raised, r.lg, 26 px items).
// Arrow keys move, Enter/Space selects, Esc closes and returns focus.
export function MenuButton({
  label,
  children,
  items,
  className = "",
  title,
  align = "start",
}: {
  label: string;
  children: ReactNode;
  items: MenuItem[];
  className?: string;
  title?: string;
  align?: "start" | "end";
}) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const first = menu.current?.querySelector<HTMLElement>('[role="menuitem"]:not([aria-disabled="true"])');
    first?.focus();
    const close = (event: MouseEvent) => {
      if (!menu.current?.contains(event.target as Node) && !button.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  const move = (delta: number) => {
    const options = [...(menu.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([aria-disabled="true"])') || [])];
    const index = options.indexOf(document.activeElement as HTMLElement);
    options[(index + delta + options.length) % options.length]?.focus();
  };
  return (
    <span className="menu-anchor">
      <button
        ref={button}
        className={className}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        title={title}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        {children}
      </button>
      {open && (
        <div
          ref={menu}
          id={id}
          className="menu"
          data-align={align}
          role="menu"
          aria-label={label}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              event.stopPropagation();
              setOpen(false);
              button.current?.focus();
            } else if (event.key === "ArrowDown") {
              event.preventDefault();
              move(1);
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              move(-1);
            } else if (event.key === "Tab") {
              setOpen(false);
            }
          }}
        >
          {items.map((item) => (
            <button
              key={item.id}
              role="menuitem"
              className="menu-item"
              tabIndex={-1}
              aria-current={item.current ? "true" : undefined}
              aria-disabled={item.disabled ? "true" : undefined}
              onClick={() => {
                if (item.disabled) return;
                setOpen(false);
                item.onSelect();
              }}
            >
              {item.icon}
              <span className="menu-label">{item.label}</span>
              {item.detail && <span className="menu-detail">{item.detail}</span>}
            </button>
          ))}
        </div>
      )}
    </span>
  );
}
