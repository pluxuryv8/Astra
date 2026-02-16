import { ASTRA_BASE_DIR, ASTRA_DATA_DIR, getApiBaseUrl } from "./config";
import { ApiError, readErrorDetail } from "./errors";

const TOKEN_KEY = "astra.auth.token";
const LAST_ERROR_KEY = "astra.auth.last_error";

export type AuthDiagnostics = {
  baseUrl: string;
  tokenPresent: boolean;
  lastStatus: number | null;
  lastErrorDetail: string | null;
  lastAttemptAt: string | null;
  lastOkAt: string | null;
  lastRequest: string | null;
  authMode: "local" | "strict" | null;
  tokenRequired: boolean | null;
};

let cachedToken: string | null = null;
let cachedTokenPath: string | null = null;
let lastStatus: number | null = null;
let lastErrorDetail: string | null = null;
let lastAttemptAt: string | null = null;
let lastOkAt: string | null = null;
let lastRequest: string | null = null;
let lastAuthMode: "local" | "strict" | null = null;
let lastTokenRequired: boolean | null = null;
const API_BASE = getApiBaseUrl();

function isTauriEnv() {
  return typeof window !== "undefined" && "__TAURI__" in window;
}

function hasStorage() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function readStoredToken(): string | null {
  if (!hasStorage()) return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

function trimSlash(value: string) {
  return value.replace(/\/$/, "");
}

async function resolveTokenCandidates(): Promise<string[]> {
  const candidates: string[] = [];
  if (ASTRA_DATA_DIR) {
    candidates.push(`${trimSlash(ASTRA_DATA_DIR)}/auth.token`);
  }
  if (ASTRA_BASE_DIR) {
    candidates.push(`${trimSlash(ASTRA_BASE_DIR)}/.astra/auth.token`);
  }
  if (!isTauriEnv()) {
    return candidates;
  }
  try {
    const pathApi = await import("@tauri-apps/api/path");
    const app = await pathApi.appDir();
    candidates.push(await pathApi.resolve(app, ".astra", "auth.token"));
    candidates.push(await pathApi.resolve(app, "..", ".astra", "auth.token"));
    candidates.push(await pathApi.resolve(app, "..", "..", ".astra", "auth.token"));
  } catch {
    // ignore
  }
  try {
    const pathApi = await import("@tauri-apps/api/path");
    const home = await pathApi.homeDir();
    candidates.push(await pathApi.join(home, ".astra", "auth.token"));
  } catch {
    // ignore
  }
  return Array.from(new Set(candidates.filter(Boolean)));
}

async function readTokenFromDisk(): Promise<string | null> {
  if (!isTauriEnv()) return null;
  try {
    const fsApi = await import("@tauri-apps/api/fs");
    const candidates = await resolveTokenCandidates();
    for (const candidate of candidates) {
      try {
        const exists = await fsApi.exists(candidate);
        if (!exists) continue;
        const raw = await fsApi.readTextFile(candidate);
        const token = raw.trim();
        if (token) {
          cachedTokenPath = candidate;
          return token;
        }
      } catch {
        // ignore and try next
      }
    }
  } catch {
    // ignore
  }
  try {
    const tauri = await import("@tauri-apps/api/tauri");
    const token = await tauri.invoke<string | null>("read_auth_token");
    if (token) {
      return token;
    }
  } catch {
    // ignore
  }
  return null;
}

async function writeTokenToDisk(token: string): Promise<void> {
  if (!isTauriEnv()) return;
  try {
    const fsApi = await import("@tauri-apps/api/fs");
    const pathApi = await import("@tauri-apps/api/path");
    const target = cachedTokenPath ?? (await resolveTokenCandidates())[0];
    if (!target) return;
    const parent = await pathApi.dirname(target);
    if (parent) {
      await fsApi.createDir(parent, { recursive: true });
    }
    await fsApi.writeTextFile(target, token);
    cachedTokenPath = target;
  } catch {
    // ignore
  }
}

export async function syncTokenFromDisk(): Promise<string | null> {
  const token = await readTokenFromDisk();
  if (token) {
    setToken(token);
  }
  return token;
}

export async function regenerateToken(): Promise<string> {
  const token = generateToken();
  await writeTokenToDisk(token);
  setToken(token);
  return token;
}

function persistError(detail: string | null, status?: number | null) {
  lastAttemptAt = new Date().toISOString();
  lastStatus = status ?? null;
  lastErrorDetail = detail || null;
  if (lastStatus && lastStatus >= 200 && lastStatus < 300) {
    lastOkAt = lastAttemptAt;
  }
  if (!hasStorage()) return;
  const payload = JSON.stringify({
    detail: lastErrorDetail,
    status: lastStatus,
    at: lastAttemptAt,
    ok_at: lastOkAt,
    request: lastRequest,
    auth_mode: lastAuthMode,
    token_required: lastTokenRequired
  });
  window.localStorage.setItem(LAST_ERROR_KEY, payload);
}

function clearError() {
  lastAttemptAt = new Date().toISOString();
  lastStatus = null;
  lastErrorDetail = null;
  if (!hasStorage()) return;
  const payload = JSON.stringify({
    detail: lastErrorDetail,
    status: lastStatus,
    at: lastAttemptAt,
    request: lastRequest,
    auth_mode: lastAuthMode,
    token_required: lastTokenRequired
  });
  window.localStorage.setItem(LAST_ERROR_KEY, payload);
}

function loadErrorFromStorage() {
  if (!hasStorage()) return;
  const raw = window.localStorage.getItem(LAST_ERROR_KEY);
  if (!raw) return;
  try {
    const parsed = JSON.parse(raw) as {
      detail?: string;
      status?: number;
      at?: string;
      ok_at?: string;
      request?: string;
      auth_mode?: "local" | "strict";
      token_required?: boolean;
    };
    lastErrorDetail = parsed.detail ?? null;
    lastStatus = typeof parsed.status === "number" ? parsed.status : null;
    lastAttemptAt = parsed.at ?? null;
    lastOkAt = parsed.ok_at ?? null;
    lastRequest = parsed.request ?? null;
    lastAuthMode = parsed.auth_mode ?? null;
    lastTokenRequired = typeof parsed.token_required === "boolean" ? parsed.token_required : null;
  } catch {
    // ignore
  }
}

export function getToken(): string | null {
  if (cachedToken) return cachedToken;
  cachedToken = readStoredToken();
  return cachedToken;
}

export function setToken(token: string) {
  cachedToken = token;
  if (!hasStorage()) return;
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  cachedToken = null;
  cachedTokenPath = null;
  if (!hasStorage()) return;
  window.localStorage.removeItem(TOKEN_KEY);
}

export function hasToken(): boolean {
  return Boolean(getToken());
}

export function generateToken(): string {
  if (typeof crypto !== "undefined") {
    if (typeof crypto.randomUUID === "function") {
      return crypto.randomUUID().replace(/-/g, "");
    }
    if (typeof crypto.getRandomValues === "function") {
      const bytes = new Uint8Array(32);
      crypto.getRandomValues(bytes);
      return Array.from(bytes)
        .map((byte) => byte.toString(16).padStart(2, "0"))
        .join("");
    }
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

export function getDiagnostics(): AuthDiagnostics {
  if (!lastAttemptAt && hasStorage()) {
    loadErrorFromStorage();
  }
  return {
    baseUrl: API_BASE,
    tokenPresent: Boolean(getToken()),
    lastStatus,
    lastErrorDetail,
    lastAttemptAt,
    lastOkAt,
    lastRequest,
    authMode: lastAuthMode,
    tokenRequired: lastTokenRequired
  };
}

export function setLastRequest(method: string, path: string) {
  lastRequest = `${method.toUpperCase()} ${path}`;
  persistError(lastErrorDetail, lastStatus);
}

export function setLastResponse(status: number | null, detail: string | null = null) {
  persistError(detail, status ?? null);
}

function authHeader(): Record<string, string> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

export async function checkStatus(): Promise<{
  initialized: boolean;
  auth_mode?: "local" | "strict";
  token_required?: boolean;
}> {
  setLastRequest("GET", "/auth/status");
  try {
    const res = await fetch(`${API_BASE}/auth/status`, { headers: { ...authHeader() } });
    if (!res.ok) {
      const detail = await readErrorDetail(res);
      setLastResponse(res.status, detail.detail);
      if (res.status === 401 || res.status === 403 || detail.detail.includes("Неверный токен")) {
        throw new ApiError("auth", detail.detail, { status: res.status, detail: detail.detail });
      }
      throw new ApiError("server", detail.detail, { status: res.status, detail: detail.detail });
    }
    const payload = (await res.json()) as {
      initialized: boolean;
      auth_mode?: "local" | "strict";
      token_required?: boolean;
    };
    lastAuthMode = payload.auth_mode ?? null;
    lastTokenRequired = typeof payload.token_required === "boolean" ? payload.token_required : null;
    setLastResponse(res.status, null);
    return payload;
  } catch (err) {
    if (err instanceof ApiError) throw err;
    setLastResponse(null, "Сервер недоступен");
    throw new ApiError("network", "Сервер недоступен");
  }
}

export async function bootstrap(token: string): Promise<void> {
  setLastRequest("POST", "/auth/bootstrap");
  try {
    const res = await fetch(`${API_BASE}/auth/bootstrap`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...authHeader()
      },
      body: JSON.stringify({ token })
    });
    if (!res.ok) {
      const detail = await readErrorDetail(res);
      setLastResponse(res.status, detail.detail);
      if (res.status === 401 || res.status === 403 || detail.detail.includes("Неверный токен") || res.status === 409) {
        throw new ApiError("auth", detail.detail, { status: res.status, detail: detail.detail });
      }
      throw new ApiError("server", detail.detail, { status: res.status, detail: detail.detail });
    }
    await res.json().catch(() => ({}));
    setLastResponse(res.status, null);
  } catch (err) {
    if (err instanceof ApiError) throw err;
    setLastResponse(null, "Сервер недоступен");
    throw new ApiError("network", "Сервер недоступен");
  }
}

export async function connect(reason: "auto" | "manual" | "auth_error" = "manual"): Promise<string> {
  const diskToken = await readTokenFromDisk();
  if (diskToken) {
    setToken(diskToken);
  }

  let token = getToken();
  const status = await checkStatus();
  if (status.token_required === false) {
    return token || "";
  }
  if (!token && status.token_required == null) {
    // Статус без режима (старый сервер). Не блокируем UI — проверка пройдёт на /projects.
    return "";
  }

  if (!token) {
    if (!status.initialized) {
      token = generateToken();
      await writeTokenToDisk(token);
      setToken(token);
    } else {
      persistError("Токен не найден", 401);
      throw new ApiError("auth", "Токен не найден");
    }
  }

  await bootstrap(token);
  if (!status.initialized || reason === "auth_error") {
    await checkStatus();
  }
  return token;
}

export function setLastError(message: string, status?: number | null) {
  persistError(message, status ?? null);
}

export function clearLastError() {
  clearError();
}
