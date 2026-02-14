import type { ReactNode } from "react";
import { cn } from "../utils/cn";

export type ModalProps = {
  open: boolean;
  title?: string;
  onClose?: () => void;
  children: ReactNode;
  className?: string;
};

export default function Modal({ open, title, onClose, children, className }: ModalProps) {
  if (!open) return null;

  return (
    <div className="ui-modal-backdrop" onClick={onClose}>
      <div
        className={cn("ui-modal", className)}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        {title ? <div className="ui-modal-title">{title}</div> : null}
        <div className="ui-modal-body">{children}</div>
      </div>
    </div>
  );
}
