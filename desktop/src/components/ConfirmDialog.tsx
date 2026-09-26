import * as Dialog from "@radix-ui/react-dialog";
import { useEffect, useRef, useState, type ReactNode } from "react";

/** A small centred question for destructive actions: a title, one line of
 *  consequence, Cancel and a confirm button. Cancel takes focus first, so
 *  Enter never destroys anything by accident. While the action runs both
 *  buttons wait; a failure stays in the dialog instead of closing it. */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  children,
  confirmLabel,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => Promise<unknown>;
}) {
  const cancel = useRef<HTMLButtonElement>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (open) setError("");
  }, [open]);
  const confirm = async () => {
    setWorking(true);
    setError("");
    try {
      await onConfirm();
      onOpenChange(false);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      setWorking(false);
    }
  };
  return (
    <Dialog.Root open={open} onOpenChange={(value) => !working && onOpenChange(value)}>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay confirm-overlay" />
        <Dialog.Content
          className="confirm-dialog"
          role="alertdialog"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            cancel.current?.focus();
          }}
        >
          <Dialog.Title className="confirm-title">{title}</Dialog.Title>
          <Dialog.Description className="confirm-body">{children}</Dialog.Description>
          {error && (
            <p className="confirm-error" role="alert">
              {error}
            </p>
          )}
          <div className="confirm-actions">
            <button ref={cancel} disabled={working} onClick={() => onOpenChange(false)}>
              Cancel
            </button>
            <button className="danger" disabled={working} onClick={() => void confirm()}>
              {working ? "Deleting…" : confirmLabel}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
