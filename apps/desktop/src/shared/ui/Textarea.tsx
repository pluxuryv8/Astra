import type { TextareaHTMLAttributes } from "react";
import { cn } from "../utils/cn";

export type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement>;

export default function Textarea({ className, ...props }: TextareaProps) {
  return <textarea className={cn("ui-textarea", className)} {...props} />;
}
