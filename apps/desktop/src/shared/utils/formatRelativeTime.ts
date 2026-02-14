export function formatRelativeTime(value?: number | string | Date) {
  if (!value) return "";
  const date = value instanceof Date ? value : new Date(value);
  const ts = date.getTime();
  if (Number.isNaN(ts)) return "";
  const diffMs = ts - Date.now();
  const abs = Math.abs(diffMs);
  const minutes = Math.floor(abs / 60000);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  const formatUnit = (amount: number, unit: "minute" | "hour" | "day") => {
    const forms =
      unit === "day"
        ? ["день", "дня", "дней"]
        : unit === "hour"
          ? ["час", "часа", "часов"]
          : ["минута", "минуты", "минут"];
    const mod10 = amount % 10;
    const mod100 = amount % 100;
    if (mod100 >= 11 && mod100 <= 14) return `${amount} ${forms[2]}`;
    if (mod10 === 1) return `${amount} ${forms[0]}`;
    if (mod10 >= 2 && mod10 <= 4) return `${amount} ${forms[1]}`;
    return `${amount} ${forms[2]}`;
  };

  let phrase = "";
  if (days > 0) {
    phrase = formatUnit(days, "day");
  } else if (hours > 0) {
    phrase = formatUnit(hours, "hour");
  } else {
    phrase = formatUnit(Math.max(minutes, 1), "minute");
  }

  if (diffMs >= 0) {
    return `через ${phrase}`;
  }
  return `${phrase} назад`;
}
