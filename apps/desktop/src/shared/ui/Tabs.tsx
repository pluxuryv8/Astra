import { cn } from "../utils/cn";

export type TabItem = {
  value: string;
  label: string;
};

export type TabsProps = {
  items: TabItem[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
};

export default function Tabs({ items, value, onChange, className }: TabsProps) {
  return (
    <div className={cn("ui-tabs", className)}>
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          className={cn("ui-tab", { "is-active": value === item.value })}
          onClick={() => onChange(item.value)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
