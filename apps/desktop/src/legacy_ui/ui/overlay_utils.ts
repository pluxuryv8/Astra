export type OverlayStatus = {
  label: string;
  tone: "ok" | "warn" | "error" | "muted";
};

export function deriveOverlayStatus(
  runStatus: string | null | undefined,
  hasApproval: boolean,
  hasError: boolean
): OverlayStatus {
  if (hasApproval) {
    return { label: "Нужно подтверждение", tone: "warn" };
  }
  if (hasError) {
    return { label: "Ошибка", tone: "error" };
  }
  if (runStatus === "running") {
    return { label: "Выполняет", tone: "ok" };
  }
  if (runStatus === "paused" || (runStatus || "").includes("waiting")) {
    return { label: "Пауза", tone: "warn" };
  }
  if (runStatus === "done") {
    return { label: "Готово", tone: "ok" };
  }
  if (runStatus === "failed") {
    return { label: "Ошибка", tone: "error" };
  }
  return { label: "Ожидание", tone: "muted" };
}
