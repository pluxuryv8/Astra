import { Search } from "lucide-react";
import type { InputHTMLAttributes } from "react";
import { cn } from "../utils/cn";

export type SearchInputProps = InputHTMLAttributes<HTMLInputElement> & {
  iconPosition?: "left" | "right";
};

export default function SearchInput({ className, iconPosition = "left", ...props }: SearchInputProps) {
  return (
    <div className={cn("ui-search", { "is-icon-right": iconPosition === "right" }, className)}>
      <Search size={16} aria-hidden="true" />
      <input className="ui-search-input" {...props} />
    </div>
  );
}
