import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
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
  side?: "top" | "bottom";
  width?: number;
  trigger: (props: { open: boolean; toggle: () => void }) => ReactNode;
  className?: string;
};

export default function DropdownMenu({
  items,
  align = "right",
  side = "bottom",
  width = 200,
  trigger,
  className
}: DropdownMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [resolvedAlign, setResolvedAlign] = useState<"left" | "right">(align);
  const [resolvedSide, setResolvedSide] = useState<"top" | "bottom">(side);

  useEffect(() => {
    if (!open) return;
    const handleClick = (event: MouseEvent) => {
      if (!ref.current || !(event.target instanceof Node)) return;
      if (!ref.current.contains(event.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    setResolvedAlign(align);
    setResolvedSide(side);
  }, [open, align, side]);

  useLayoutEffect(() => {
    if (!open || !panelRef.current) return;
    const rect = panelRef.current.getBoundingClientRect();
    let nextAlign = align;
    let nextSide = side;

    if (rect.left < 8) nextAlign = "left";
    if (rect.right > window.innerWidth - 8) nextAlign = "right";
    if (rect.top < 8) nextSide = "bottom";
    if (rect.bottom > window.innerHeight - 8) nextSide = "top";

    if (nextAlign !== resolvedAlign) setResolvedAlign(nextAlign);
    if (nextSide !== resolvedSide) setResolvedSide(nextSide);
  }, [open, align, side, resolvedAlign, resolvedSide]);

  const toggle = () => setOpen((prev) => !prev);

  return (
    <div className={cn("ui-dropdown", className)} ref={ref}>
      {trigger({ open, toggle })}
      {open ? (
        <div
          ref={panelRef}
          className="ui-dropdown-panel"
          data-align={resolvedAlign}
          data-side={resolvedSide}
          style={{ minWidth: width }}
        >
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
