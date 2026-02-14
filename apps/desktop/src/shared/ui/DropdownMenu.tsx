import { useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "../utils/cn";

export type DropdownItem = {
  id: string;
  label: string;
  onSelect?: () => void;
  tone?: "default" | "danger";
  disabled?: boolean;
  icon?: ReactNode;
};

export type DropdownMenuProps = {
  items: DropdownItem[];
  align?: "left" | "right";
  width?: number;
  trigger: (props: { open: boolean; toggle: () => void }) => ReactNode;
  className?: string;
};

export default function DropdownMenu({
  items,
  align = "right",
  width = 200,
  trigger,
  className
}: DropdownMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const handleClick = (event: MouseEvent) => {
      if (!ref.current || !(event.target instanceof Node)) return;
      if (!ref.current.contains(event.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const toggle = () => setOpen((prev) => !prev);

  return (
    <div className={cn("ui-dropdown", className)} ref={ref}>
      {trigger({ open, toggle })}
      {open ? (
        <div className="ui-dropdown-panel" data-align={align} style={{ minWidth: width }}>
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              className={cn("ui-dropdown-item", {
                "is-danger": item.tone === "danger",
                "is-disabled": item.disabled
              })}
              onClick={() => {
                if (item.disabled) return;
                item.onSelect?.();
                setOpen(false);
              }}
            >
              {item.icon ? <span className="ui-dropdown-icon">{item.icon}</span> : null}
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
