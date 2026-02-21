import type {
  Approval,
  PlanStep,
  Project,
  ProjectSettings,
  Reminder,
  Run,
  RunIntentResponse,
  Snapshot,
  StatusResponse,
  UserMemory
} from "../types/api";
import { getApiBaseUrl } from "./config";
import { ApiError, readErrorDetail } from "./errors";
import { getToken, setLastRequest, setLastResponse } from "./authController";

type ApiOptions = Omit<RequestInit, "headers"> & { headers?: Record<string, string> };

const API_BASE = getApiBaseUrl();

function authHeaders() {
  const token = getToken();
  return (token ? { Authorization: `Bearer ${token}` } : {}) as Record<string, string>;
}

async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  setLastRequest(method, path);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...(options.headers || {})
      },
      ...options
    });
  } catch {
    const origin = new URL(API_BASE).origin;
    setLastResponse(null, `Сервер недоступен (${origin})`);
    throw new ApiError("network", `Сервер недоступен (${origin})`);
  }

  if (res.ok) {
    setLastResponse(res.status, null);
    if (res.status === 204) return {} as T;
    return (await res.json()) as T;
  }

  const detail = await readErrorDetail(res);
  setLastResponse(res.status, detail.detail || res.statusText);
  const isAuth = res.status === 401 || res.status === 403 || detail.detail === "Неверный токен";
  if (isAuth) {
    throw new ApiError("auth", detail.detail || "Требуется подключение", { status: res.status, detail: detail.detail });
  }

  throw new ApiError("server", detail.detail || res.statusText, { status: res.status, detail: detail.detail });
}

export async function checkApiStatus(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/auth/status`);
    return res.ok;
  } catch {
    return false;
  }
}

export function apiBase() {
  return getApiBaseUrl();
}

export function listProjects(): Promise<Project[]> {
  return api<Project[]>("/projects");
}

export function createProject(payload: { name: string; tags: string[]; settings: ProjectSettings }): Promise<Project> {
  return api<Project>("/projects", { method: "POST", body: JSON.stringify(payload) });
}

export function listRuns(projectId: string, limit = 50): Promise<Run[]> {
  return api<Run[]>(`/projects/${projectId}/runs?limit=${limit}`);
}

export function createRun(
  projectId: string,
  payload: { query_text: string; mode: string; parent_run_id?: string | null; purpose?: string | null }
): Promise<RunIntentResponse> {
  return api<RunIntentResponse>(`/projects/${projectId}/runs`, { method: "POST", body: JSON.stringify(payload) });
}

export function createPlan(runId: string): Promise<PlanStep[]> {
  return api<PlanStep[]>(`/runs/${runId}/plan`, { method: "POST" });
}

export function startRun(runId: string): Promise<StatusResponse> {
  return api<StatusResponse>(`/runs/${runId}/start`, { method: "POST" });
}

export function cancelRun(runId: string): Promise<StatusResponse> {
  return api<StatusResponse>(`/runs/${runId}/cancel`, { method: "POST" });
}

export function pauseRun(runId: string): Promise<StatusResponse> {
  return api<StatusResponse>(`/runs/${runId}/pause`, { method: "POST" });
}

export function resumeRun(runId: string): Promise<StatusResponse> {
  return api<StatusResponse>(`/runs/${runId}/resume`, { method: "POST" });
}

export function getSnapshot(runId: string): Promise<Snapshot> {
  return api<Snapshot>(`/runs/${runId}/snapshot`);
}

export function listApprovals(runId: string): Promise<Approval[]> {
  return api<Approval[]>(`/runs/${runId}/approvals`);
}

export function listUserMemory(query = "", tag = "", limit = 50): Promise<UserMemory[]> {
  const params = new URLSearchParams();
  if (query) params.set("query", query);
  if (tag) params.set("tag", tag);
  params.set("limit", String(limit));
  return api<UserMemory[]>(`/memory/list?${params.toString()}`);
}

export function deleteUserMemory(memoryId: string): Promise<StatusResponse> {
  return api<StatusResponse>(`/memory/${memoryId}`, { method: "DELETE" });
}

export function listReminders(status = "", limit = 200): Promise<Reminder[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("limit", String(limit));
  return api<Reminder[]>(`/reminders?${params.toString()}`);
}

export function createReminder(payload: {
  due_at: string;
  text: string;
  delivery?: string;
  run_id?: string | null;
  source?: string;
}): Promise<Reminder> {
  return api<Reminder>("/reminders/create", { method: "POST", body: JSON.stringify(payload) });
}

export function cancelReminder(reminderId: string): Promise<Reminder> {
  return api<Reminder>(`/reminders/${reminderId}`, { method: "DELETE" });
}
