export type ApiErrorCode = "network" | "auth" | "server";

export class ApiError extends Error {
  code: ApiErrorCode;
  status?: number;
  detail?: string;

  constructor(code: ApiErrorCode, message: string, options?: { status?: number; detail?: string }) {
    super(message);
    this.code = code;
    this.status = options?.status;
    this.detail = options?.detail;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

export function isAuthError(error: unknown): error is ApiError {
  return isApiError(error) && error.code === "auth";
}

export function isNetworkError(error: unknown): error is ApiError {
  return isApiError(error) && error.code === "network";
}

export async function readErrorDetail(res: Response): Promise<{ detail: string; raw: string }> {
  const raw = await res.text();
  if (!raw) return { detail: res.statusText || "Ошибка запроса", raw: "" };
  try {
    const parsed = JSON.parse(raw) as { detail?: string };
    if (parsed?.detail) {
      return { detail: parsed.detail, raw };
    }
  } catch {
    // ignore
  }
  return { detail: raw, raw };
}
