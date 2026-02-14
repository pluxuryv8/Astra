import { API_BASE, ASTRA_BASE_DIR } from "../api/config";
import { getDiagnostics, checkStatus } from "../api/authController";
import { listProjects, getSnapshot } from "../api/client";
import { useAppStore } from "../store/appStore";
import type { Message } from "../types/ui";
import type { Snapshot } from "../types/api";

const MAX_SNAPSHOTS = 10;

export type ExportResult =
  | { ok: true; path: string; logsIncluded?: boolean }
  | { ok: false; error: string };

export type ExportProgress = (message: string) => void;

type ExportMeta = {
  exported_at: string;
  app_version?: string;
  app_name?: string;
  platform?: string;
  os_version?: string;
  arch?: string;
  user_agent?: string;
};

type ExportData = {
  meta: ExportMeta;
  connection: {
    baseUrl: string;
    auth_status?: {
      initialized?: boolean;
      auth_mode?: string;
      token_required?: boolean;
    };
    lastRequest?: string | null;
    lastStatus?: number | null;
    lastErrorDetail?: string | null;
  };
  ui_prefs: Record<string, string | null>;
  conversation?: {
    id: string;
    title: string;
    updated_at: string;
    run_ids: string[];
    messages: Message[];
  } | null;
  runs: Array<{
    id: string;
    status: string;
    mode: string;
    query_text: string;
    created_at?: string;
    started_at?: string | null;
    finished_at?: string | null;
  }>;
  snapshots: Array<{ run_id: string; snapshot?: Snapshot; error?: string }>;
  projects?: Array<{ id: string; name: string; tags: string[] }>;
};

const UI_PREF_KEYS = [
  "astra.ui.sidebarWidth",
  "astra.ui.activityWidth",
  "astra.ui.activityOpen",
  "astra.ui.lastSelectedPage",
  "astra.ui.lastSelectedChatId",
  "astra.ui.density",
  "astra.ui.grain",
  "astra.ui.activityDetailed",
  "astra.ui.defaultActivityOpen",
  "astra.ui.overlayOpen",
  "astra.ui.overlay.behavior",
  "astra.ui.overlay.cornerPreference",
  "astra.ui.overlay.mini",
  "astra.ui.overlayBounds",
  "astra.ui.overlay.lastNormalBounds"
] as const;

function isTauri() {
  return typeof window !== "undefined" && "__TAURI__" in window;
}

function redactString(value: string) {
  let output = value;
  output = output.replace(/Bearer\s+[A-Za-z0-9._-]+/g, "Bearer [REDACTED]");
  output = output.replace(/sk-[A-Za-z0-9]{10,}/g, "[REDACTED]");
  output = output.replace(/token=([A-Za-z0-9._-]+)/gi, "token=[REDACTED]");
  output = output.replace(/api[_-]?key=([A-Za-z0-9._-]+)/gi, "api_key=[REDACTED]");
  return output;
}

function sanitizeValue(value: unknown): unknown {
  if (typeof value === "string") {
    return redactString(value);
  }
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeValue(item));
  }
  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const safe: Record<string, unknown> = {};
    for (const [entryKey, entryValue] of Object.entries(obj)) {
      const lowered = entryKey.toLowerCase();
      if (
        lowered.includes("token") ||
        lowered.includes("api_key") ||
        lowered.includes("secret") ||
        lowered.includes("password") ||
        lowered.includes("authorization") ||
        lowered.includes("screenshot_text") ||
        lowered.includes("ocr_text") ||
        lowered.includes("confidential")
      ) {
        safe[entryKey] = "[REDACTED]";
      } else {
        safe[entryKey] = sanitizeValue(entryValue);
      }
    }
    return safe;
  }
  return value;
}

function sanitizeMessage(message: Message): Message {
  return {
    ...message,
    text: redactString(message.text)
  };
}

function collectUiPrefs(): Record<string, string | null> {
  if (typeof window === "undefined" || typeof window.localStorage === "undefined") {
    return {};
  }
  const prefs: Record<string, string | null> = {};
  UI_PREF_KEYS.forEach((key) => {
    prefs[key] = window.localStorage.getItem(key);
  });
  return prefs;
}

async function getAppMeta(): Promise<ExportMeta> {
  const meta: ExportMeta = {
    exported_at: new Date().toISOString(),
    user_agent: typeof navigator !== "undefined" ? navigator.userAgent : undefined
  };
  if (!isTauri()) return meta;
  try {
    const appApi = await import("@tauri-apps/api/app");
    meta.app_version = await appApi.getVersion();
    meta.app_name = await appApi.getName();
  } catch {
    // ignore
  }
  try {
    const osApi = await import("@tauri-apps/api/os");
    meta.platform = await osApi.platform();
    meta.os_version = await osApi.version();
    meta.arch = await osApi.arch();
  } catch {
    // ignore
  }
  return meta;
}

async function buildExportData(): Promise<ExportData> {
  const state = useAppStore.getState();
  const diagnostics = getDiagnostics();
  const meta = await getAppMeta();
  let authStatus: { initialized?: boolean; auth_mode?: string; token_required?: boolean } | undefined;
  try {
    authStatus = await checkStatus();
  } catch {
    authStatus = undefined;
  }

  const conversationId = state.lastSelectedChatId;
  const conversation = conversationId
    ? state.conversations.find((item) => item.id === conversationId) || null
    : null;
  const messages = conversationId ? state.conversationMessages[conversationId] || [] : [];

  const runIds = conversation?.run_ids?.length
    ? [...conversation.run_ids]
    : state.runs.slice(0, MAX_SNAPSHOTS).map((run) => run.id);
  const uniqueRunIds = Array.from(new Set(runIds)).slice(0, MAX_SNAPSHOTS);

  const snapshots: Array<{ run_id: string; snapshot?: Snapshot; error?: string }> = [];
  for (const runId of uniqueRunIds) {
    try {
      const snapshot = await getSnapshot(runId);
      snapshots.push({ run_id: runId, snapshot: sanitizeValue(snapshot) as Snapshot });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Не удалось загрузить snapshot";
      snapshots.push({ run_id: runId, error: message });
    }
  }

  let projects: Array<{ id: string; name: string; tags: string[] }> | undefined;
  try {
    const items = await listProjects();
    projects = items.map((project) => ({ id: project.id, name: project.name, tags: project.tags || [] }));
  } catch {
    projects = undefined;
  }

  const runsSummary = state.runs.map((run) => ({
    id: run.id,
    status: run.status,
    mode: run.mode,
    query_text: redactString(run.query_text || ""),
    created_at: run.created_at,
    started_at: run.started_at,
    finished_at: run.finished_at
  }));

  const safeConversation = conversation
    ? {
        ...conversation,
        messages: messages.map(sanitizeMessage)
      }
    : null;

  return {
    meta,
    connection: {
      baseUrl: diagnostics.baseUrl || API_BASE,
      auth_status: authStatus,
      lastRequest: diagnostics.lastRequest,
      lastStatus: diagnostics.lastStatus,
      lastErrorDetail: diagnostics.lastErrorDetail
    },
    ui_prefs: collectUiPrefs(),
    conversation: safeConversation,
    runs: runsSummary,
    snapshots,
    projects
  };
}

async function writeFileWithRedaction(path: string, content: string) {
  const fsApi = await import("@tauri-apps/api/fs");
  const safe = redactString(content);
  await fsApi.writeTextFile(path, safe);
}

async function resolveLatestLogDir(baseDir: string): Promise<string | null> {
  if (!baseDir) return null;
  const fsApi = await import("@tauri-apps/api/fs");
  const pathApi = await import("@tauri-apps/api/path");
  const latestPointer = await pathApi.join(baseDir, ".astra", "dev_logs", "latest");
  try {
    if (await fsApi.exists(latestPointer)) {
      const latest = (await fsApi.readTextFile(latestPointer)).trim();
      if (latest && (await fsApi.exists(latest))) {
        return latest;
      }
    }
  } catch {
    // ignore
  }

  try {
    const logsRoot = await pathApi.join(baseDir, "artifacts", "dev_logs");
    if (!(await fsApi.exists(logsRoot))) return null;
    const entries = await fsApi.readDir(logsRoot);
    const dirs = entries.filter((entry) => entry.children !== undefined).map((entry) => entry.name || "");
    const sorted = dirs.filter(Boolean).sort();
    if (!sorted.length) return null;
    return await pathApi.join(logsRoot, sorted[sorted.length - 1]);
  } catch {
    return null;
  }
}

export async function exportJson(onProgress?: ExportProgress): Promise<ExportResult> {
  onProgress?.("Собираю данные…");
  const payload = await buildExportData();
  const json = JSON.stringify(sanitizeValue(payload), null, 2);

  if (!isTauri()) {
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    anchor.href = url;
    anchor.download = `astra-export-${stamp}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    return { ok: true, path: anchor.download };
  }

  try {
    onProgress?.("Сохраняю файл…");
    const dialog = await import("@tauri-apps/api/dialog");
    const fsApi = await import("@tauri-apps/api/fs");
    const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 16);
    const filePath = await dialog.save({
      defaultPath: `astra-export-${stamp}.json`,
      filters: [{ name: "JSON", extensions: ["json"] }]
    });
    if (!filePath) return { ok: false, error: "Сохранение отменено" };
    await fsApi.writeTextFile(filePath, json);
    return { ok: true, path: filePath };
  } catch (err) {
    const message = err instanceof Error ? err.message : "Не удалось сохранить файл";
    return { ok: false, error: message };
  }
}

export async function exportDiagnosticsPack(onProgress?: ExportProgress): Promise<ExportResult> {
  if (!isTauri()) {
    return { ok: false, error: "Пакет диагностики доступен только в десктоп-приложении." };
  }

  try {
    onProgress?.("Собираю данные…");
    const payload = await buildExportData();
    const json = JSON.stringify(sanitizeValue(payload), null, 2);

    const dialog = await import("@tauri-apps/api/dialog");
    const fsApi = await import("@tauri-apps/api/fs");
    const pathApi = await import("@tauri-apps/api/path");
    const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 16);
    const base = await dialog.open({ directory: true, multiple: false });
    if (!base || typeof base !== "string") return { ok: false, error: "Сохранение отменено" };
    const folder = await pathApi.join(base, `astra-diagnostics-${stamp}`);
    await fsApi.createDir(folder, { recursive: true });
    await fsApi.writeTextFile(await pathApi.join(folder, "export.json"), json);

    let logsIncluded = false;
    const homeDir = await pathApi.homeDir();
    const appDir = await pathApi.appDir();
    const candidates = Array.from(
      new Set([ASTRA_BASE_DIR, homeDir, appDir].filter((value): value is string => Boolean(value)))
    );
    let resolvedLogDir: string | null = null;
    for (const candidate of candidates) {
      resolvedLogDir = await resolveLatestLogDir(candidate);
      if (resolvedLogDir) break;
    }
    if (resolvedLogDir) {
      const apiLog = await pathApi.join(resolvedLogDir, "api.log");
      const tauriLog = await pathApi.join(resolvedLogDir, "tauri.log");
      if (await fsApi.exists(apiLog)) {
        const raw = await fsApi.readTextFile(apiLog);
        await writeFileWithRedaction(await pathApi.join(folder, "api.log"), raw);
        logsIncluded = true;
      }
      if (await fsApi.exists(tauriLog)) {
        const raw = await fsApi.readTextFile(tauriLog);
        await writeFileWithRedaction(await pathApi.join(folder, "tauri.log"), raw);
        logsIncluded = true;
      }
    }

    return { ok: true, path: folder, logsIncluded };
  } catch (err) {
    const message = err instanceof Error ? err.message : "Не удалось сохранить пакет";
    return { ok: false, error: message };
  }
}
