import type { InputHTMLAttributes } from "react";
import { cn } from "../utils/cn";

export type InputProps = InputHTMLAttributes<HTMLInputElement>;

export default function Input({ className, ...props }: InputProps) {
  return <input className={cn("ui-input", className)} {...props} />;
}
