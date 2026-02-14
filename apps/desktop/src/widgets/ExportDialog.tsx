import { useMemo, useState } from "react";
import { Download, FolderOpen } from "lucide-react";
import Modal from "../shared/ui/Modal";
import Button from "../shared/ui/Button";
import { cn } from "../shared/utils/cn";
import { exportDiagnosticsPack, exportJson } from "../shared/utils/exportService";

type ExportDialogProps = {
  open: boolean;
  onClose: () => void;
};

type ExportStatus = {
  phase: "idle" | "working" | "done" | "error";
  message?: string;
  path?: string;
  logsIncluded?: boolean;
  kind?: "json" | "pack";
};

function isTauriEnv() {
  return typeof window !== "undefined" && "__TAURI__" in window;
}

export default function ExportDialog({ open, onClose }: ExportDialogProps) {
  const [status, setStatus] = useState<ExportStatus>({ phase: "idle" });

  const canClose = status.phase !== "working";
  const inProgress = status.phase === "working";

  const helperText = useMemo(() => {
    if (status.phase === "working") return status.message || "Собираю данные…";
    if (status.phase === "error") return status.message || "Не удалось выполнить экспорт.";
    if (status.phase === "done") return status.message || "Готово.";
    return "Экспорт собирает историю диалога, запусков, диагностику и настройки UI.";
  }, [status]);

  const runExport = async (kind: "json" | "pack") => {
    if (inProgress) return;
    setStatus({ phase: "working", message: "Собираю данные…", kind });
    const onProgress = (message: string) => {
      setStatus((prev) => ({ ...prev, phase: "working", message }));
    };
    const result = kind === "json" ? await exportJson(onProgress) : await exportDiagnosticsPack(onProgress);
    if (result.ok) {
      const logsIncluded = "logsIncluded" in result ? result.logsIncluded : undefined;
      const extra =
        kind === "pack" && logsIncluded === false
          ? " Логи не найдены — запустите astra dev, чтобы они появились."
          : "";
      setStatus({
        phase: "done",
        message: `Готово: ${result.path}.${extra}`,
        path: result.path,
        logsIncluded,
        kind
      });
    } else {
      setStatus({ phase: "error", message: result.error, kind });
    }
  };

  const handleOpenFolder = async () => {
    if (!status.path) return;
    if (!isTauriEnv()) return;
    try {
      const pathApi = await import("@tauri-apps/api/path");
      const shell = await import("@tauri-apps/api/shell");
      const target =
        status.kind === "pack"
          ? status.path
          : await pathApi.dirname(status.path);
      await shell.open(target);
    } catch {
      // ignore
    }
  };

  return (
    <Modal
      open={open}
      title="Экспорт и диагностика"
      onClose={canClose ? onClose : undefined}
      className="export-dialog"
    >
      <div className="export-body">
        <div className={cn("export-helper", status.phase === "error" && "is-error")}>
          {helperText}
        </div>

        <div className="export-actions">
          <Button
            type="button"
            variant="primary"
            onClick={() => void runExport("json")}
            disabled={inProgress}
          >
            Экспорт JSON
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => void runExport("pack")}
            disabled={inProgress}
          >
            Пакет диагностики
          </Button>
        </div>

        {status.phase === "done" && status.path ? (
          <div className="export-result">
            <div className="export-path">{status.path}</div>
            <div className="export-result-actions">
              <Button type="button" variant="ghost" onClick={handleOpenFolder}>
                <FolderOpen size={16} />
                Открыть папку
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => void navigator.clipboard?.writeText(status.path || "")}
              >
                <Download size={16} />
                Скопировать путь
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
