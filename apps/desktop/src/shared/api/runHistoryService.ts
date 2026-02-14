import type { Run, Snapshot } from "../types/api";
import { ApiError } from "./errors";
import { getSnapshot, listRuns } from "./client";

export type ServiceError = {
  status: number | null;
  detail: string;
};

export type ServiceResult<T> = { ok: true; data: T } | { ok: false; error: ServiceError };

function normalizeError(err: unknown): ServiceError {
  if (err instanceof ApiError) {
    return {
      status: err.status ?? null,
      detail: err.detail || err.message
    };
  }
  if (err instanceof Error) {
    return { status: null, detail: err.message };
  }
  return { status: null, detail: "Неизвестная ошибка" };
}

export async function listRunsHistory(projectId: string, limit = 200): Promise<ServiceResult<Run[]>> {
  try {
    const runs = await listRuns(projectId, limit);
    return { ok: true, data: runs };
  } catch (err) {
    return { ok: false, error: normalizeError(err) };
  }
}

export async function getRunSnapshot(runId: string): Promise<ServiceResult<Snapshot>> {
  try {
    const snapshot = await getSnapshot(runId);
    return { ok: true, data: snapshot };
  } catch (err) {
    return { ok: false, error: normalizeError(err) };
  }
}
