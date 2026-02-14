import type { ReactNode } from "react";

export type TooltipProps = {
  label: string;
  children: ReactNode;
};

export default function Tooltip({ label, children }: TooltipProps) {
  return (
    <span className="ui-tooltip" data-tooltip={label}>
      {children}
    </span>
  );
}
