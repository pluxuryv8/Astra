import type { ButtonHTMLAttributes } from "react";
import { cn } from "../utils/cn";

export type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "ghost" | "outline" | "subtle";
  size?: "sm" | "md" | "lg";
  active?: boolean;
};

export default function IconButton({
  variant = "ghost",
  size = "md",
  active,
  className,
  ...props
}: IconButtonProps) {
  return (
    <button
      className={cn("ui-icon-button", `ui-icon-button--${variant}`, `ui-icon-button--${size}`, {
        "is-active": active
      }, className)}
      {...props}
    />
  );
}
