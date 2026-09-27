import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Laptop, Monitor, Smartphone, Tablet } from "lucide-react";
import type { Device } from "./types";

export type Decision = "deny" | "ask" | "allow";
const DECISIONS: Decision[] = ["deny", "ask", "allow"];
const WORD: Record<Decision, string> = { deny: "Off", ask: "Ask", allow: "Allow" };

/** Off · Ask · Allow with a sliding indicator. The chosen value shows at once
 *  and settles to the saved value when the change returns. */
export function Segmented({
  label,
  value,
  disabled,
  onChange,
}: {
  label: string;
  value: Decision;
  disabled?: boolean;
  onChange: (value: Decision) => Promise<unknown>;
}) {
  const [pending, setPending] = useState<Decision | null>(null);
  const shown = pending ?? value;
  return (
    <div
      className="devices-seg"
      role="group"
      aria-label={label}
      data-value={shown}
      style={{ "--i": DECISIONS.indexOf(shown) } as CSSProperties}
    >
      <span className="devices-seg-thumb" aria-hidden="true" />
      {DECISIONS.map((v) => (
        <button
          key={v}
          type="button"
          data-value={v}
          aria-pressed={v === shown}
          disabled={disabled}
          onClick={() => {
            if (v === shown || pending) return;
            setPending(v);
            void onChange(v).finally(() => setPending(null));
          }}
        >
          {WORD[v]}
        </button>
      ))}
    </div>
  );
}

/** Confirmation for destructive actions. */
export function Confirm({
  open,
  title,
  children,
  action,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  action: string;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => Promise<unknown>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (open) setError("");
  }, [open]);
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="devices-overlay" />
        <Dialog.Content className="devices-modal">
          <Dialog.Title>{title}</Dialog.Title>
          <Dialog.Description asChild>
            <div className="devices-modal-text">{children}</div>
          </Dialog.Description>
          {error && <p role="alert">{error}</p>}
          <div className="devices-modal-actions">
            <Dialog.Close>Cancel</Dialog.Close>
            <button
              className="danger"
              disabled={busy}
              onClick={() => {
                setBusy(true);
                setError("");
                onConfirm()
                  .then(() => onOpenChange(false))
                  .catch((e) => setError(e instanceof Error ? e.message : "The action could not complete."))
                  .finally(() => setBusy(false));
              }}
            >
              {action}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function DeviceIcon({ device, size = 16 }: { device: Pick<Device, "device_class">; size?: number }) {
  const Icon =
    device.device_class === "phone" ? Smartphone
    : device.device_class === "tablet" ? Tablet
    : device.device_class === "laptop" ? Laptop
    : Monitor;
  return <Icon size={size} aria-hidden="true" />;
}

const PLATFORM: Record<string, string> = {
  ios: "iOS", android: "Android", macos: "macOS", windows: "Windows", linux: "Linux",
};
const CLASS: Record<string, string> = {
  phone: "Phone", tablet: "Tablet", laptop: "Laptop", desktop: "Desktop",
};
export function deviceKind(device: Device): string {
  const os = device.public_identity_metadata?.os || PLATFORM[device.platform] || "";
  return [CLASS[device.device_class], os].filter(Boolean).join(" · ");
}

export function dateLabel(value?: number | null): string {
  if (!value) return "Not recorded";
  return new Date(value * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function fullTime(value?: number | null): string {
  return value ? new Date(value * 1000).toLocaleString() : "Not recorded";
}

/** "just now", "5 min ago", "3 h ago", "yesterday 18:02", "24 Sep 2026". */
export function ago(value?: number | null, now = Date.now()): string {
  if (!value) return "Not recorded";
  const seconds = Math.max(0, Math.round(now / 1000 - value));
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))} min ago`;
  if (seconds < 6 * 3600) return `${Math.round(seconds / 3600)} h ago`;
  const date = new Date(value * 1000);
  const today = new Date(now);
  const time = date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  if (date.toDateString() === today.toDateString()) return `today ${time}`;
  const yesterday = new Date(now - 86400000);
  if (date.toDateString() === yesterday.toDateString()) return `yesterday ${time}`;
  return dateLabel(value);
}

/** Backend codes such as "request_denied" as a sentence. */
export function sentence(code: string): string {
  const text = code.replaceAll("_", " ").trim();
  return text ? text[0].toUpperCase() + text.slice(1) : text;
}
