import type { ReactNode } from "react";
import { cn } from "../utils/cn";

export type SheetProps = {
  open: boolean;
  side?: "left" | "right" | "bottom";
  onClose?: () => void;
  children: ReactNode;
  className?: string;
};

export default function Sheet({ open, side = "right", onClose, children, className }: SheetProps) {
  if (!open) return null;

  return (
    <div className="ui-sheet-backdrop" onClick={onClose}>
      <div
        className={cn("ui-sheet", `ui-sheet--${side}`, className)}
        onClick={(event) => event.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
