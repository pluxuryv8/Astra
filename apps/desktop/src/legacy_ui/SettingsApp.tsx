import { useEffect, useState } from "react";
import {
  checkApiStatus,
  checkPermissions,
  createProject,
  initAuth,
  listProjects,
  updateProject
} from "./api";
import SettingsPanel from "./ui/SettingsPanel";
import type { Project, ProjectSettings } from "./types";

const MODE_OPTIONS = [
  { value: "plan_only", label: "Только план" },
  { value: "research", label: "Исследование" },
  { value: "execute_confirm", label: "Выполнение с подтверждением" },
  { value: "autopilot_safe", label: "Автопилот (безопасный)" }
];

const RUN_MODE_KEY = "astra_run_mode";

export default function SettingsApp() {
  const [, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [modelName, setModelName] = useState("llama2-uncensored:7b");
  const [apiAvailable, setApiAvailable] = useState<boolean | null>(null);
  const [savingKey, setSavingKey] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState<{ text: string; tone: "success" | "error" | "info" } | null>(null);
  const [permissions, setPermissions] = useState<{
    screen_recording?: "granted" | "denied" | "unknown";
    accessibility?: "granted" | "denied" | "unknown";
  } | null>(null);
  const [mode, setMode] = useState<string>(() => localStorage.getItem(RUN_MODE_KEY) || "execute_confirm");

  useEffect(() => {
    const setup = async () => {
      await initAuth();
      const data = await listProjects();
      if (!data.length) {
        const created = await createProject({ name: "Основной", tags: ["default"], settings: {} });
        setProjects([created]);
        setSelectedProject(created);
        setModelName(created.settings?.llm?.model || "llama2-uncensored:7b");
        return;
      }
      setProjects(data);
      setSelectedProject(data[0]);
      setModelName(data[0].settings?.llm?.model || "llama2-uncensored:7b");
    };
    setup().catch(() => setSettingsMessage({ text: "Не удалось загрузить проект", tone: "error" }));
  }, []);

  useEffect(() => {
    localStorage.setItem(RUN_MODE_KEY, mode);
  }, [mode]);

  useEffect(() => {
    checkPermissions()
      .then(setPermissions)
      .catch(() => setPermissions(null));
  }, []);

  useEffect(() => {
    const check = async () => {
      const ok = await checkApiStatus();
      setApiAvailable(ok);
    };
    void check();
  }, []);

  useEffect(() => {
    if (!settingsMessage) return;
    const timer = window.setTimeout(() => setSettingsMessage(null), 5200);
    return () => window.clearTimeout(timer);
  }, [settingsMessage]);

  const handleSaveSettings = async () => {
    if (!selectedProject) {
      setSettingsMessage({ text: "Проект не найден", tone: "error" });
      return;
    }
    try {
      setSavingKey(true);
      const current = selectedProject.settings || {};
      const llm = (current.llm || {}) as NonNullable<ProjectSettings["llm"]>;
      const nextSettings = {
        ...current,
        llm: {
          ...llm,
          provider: "local",
          base_url: llm.base_url || "http://127.0.0.1:11434",
          model: modelName.trim() || llm.model || "llama2-uncensored:7b"
        }
      };
      const updated = await updateProject(selectedProject.id, { settings: nextSettings });
      setProjects((prev) => prev.map((proj) => (proj.id === updated.id ? updated : proj)));
      setSelectedProject(updated);
      setSettingsMessage({
        text: "Модель сохранена",
        tone: "success"
      });
    } catch {
      setSettingsMessage({ text: "Не удалось сохранить", tone: "error" });
    } finally {
      setSavingKey(false);
    }
  };

  return (
    <div className="settings-only">
      <SettingsPanel
        modelName={modelName}
        onModelChange={setModelName}
        apiAvailable={apiAvailable}
        permissions={permissions}
        mode={mode}
        modeOptions={MODE_OPTIONS}
        onModeChange={setMode}
        animatedBg={false}
        onAnimatedBgChange={() => undefined}
        onSave={handleSaveSettings}
        saving={savingKey}
        message={settingsMessage}
        onClose={() => undefined}
        onRefreshPermissions={() =>
          checkPermissions()
            .then(setPermissions)
            .catch(() => setPermissions(null))
        }
        isStandalone
      />
    </div>
  );
}
