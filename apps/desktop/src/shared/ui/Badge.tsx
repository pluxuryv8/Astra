import type { HTMLAttributes } from "react";
import { cn } from "../utils/cn";

export type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  tone?: "neutral" | "muted" | "accent" | "success" | "warn" | "danger";
  size?: "sm" | "md";
};

export default function Badge({ tone = "neutral", size = "md", className, ...props }: BadgeProps) {
  return <span className={cn("ui-badge", `ui-badge--${tone}`, `ui-badge--${size}`, className)} {...props} />;
}
