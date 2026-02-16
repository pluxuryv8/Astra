export const PHRASES = {
  clarifyFallback: "Нужно уточнение.",
  chatFallback: "Готово.",
  actStart: "Понял, выполняю. Статус — справа.",
  confirmDanger: "Нужно подтверждение: действие может быть опасным.",
  done: "Готово.",
  error: "Ошибка."
};

export function withName(text: string, name?: string | null): string {
  if (!text) return text;
  if (!name) return text;
  const trimmed = text.trim();
  if (!trimmed) return text;
  if (trimmed.toLowerCase().startsWith(name.toLowerCase())) return text;
  const lowered = trimmed.length > 1 ? trimmed[0].toLowerCase() + trimmed.slice(1) : trimmed.toLowerCase();
  return `${name}, ${lowered}`;
}

export function nameFromMeta(meta?: Record<string, unknown> | null): string | null {
  if (!meta) return null;
  const raw = meta.user_name;
  if (typeof raw !== "string") return null;
  const value = raw.trim();
  return value ? value : null;
}
