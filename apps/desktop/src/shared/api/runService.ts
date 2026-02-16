import type { EventItem, RunIntentResponse, Snapshot } from "../types/api";
import { createRun, getSnapshot, startRun } from "./client";
import { getApiBaseUrl } from "./config";
import { createEventStreamManager, type StreamCallbacks, type StreamState } from "./eventStream";

export type RunService = {
  createRun: (projectId: string, payload: { query_text: string; mode: string; parent_run_id?: string | null }) => Promise<RunIntentResponse>;
  startRun: (runId: string) => Promise<void>;
  fetchSnapshot: (runId: string) => Promise<Snapshot>;
  openEventStream: (
    runId: string,
    options: {
      token?: string | null;
      lastEventId?: number | null;
      eventTypes: string[];
      onEvent: (event: EventItem) => void;
      onStateChange: (state: StreamState) => void;
      onError?: (message: string) => void;
      onReconnect?: () => void;
      getLastEventId?: () => number | null;
    }
  ) => { disconnect: () => void };
};

export function createRunService(callbacks?: Partial<StreamCallbacks>): RunService {
  return {
    createRun: (projectId, payload) => createRun(projectId, payload),
    startRun: async (runId) => {
      await startRun(runId);
    },
    fetchSnapshot: (runId) => getSnapshot(runId),
    openEventStream: (runId, options) => {
      const manager = createEventStreamManager(getApiBaseUrl(), options.eventTypes, {
        onEvent: options.onEvent,
        onStateChange: options.onStateChange,
        onError: options.onError ?? callbacks?.onError,
        onReconnect: options.onReconnect,
        getLastEventId: options.getLastEventId
      });
      manager.connect({
        runId,
        token: options.token,
        lastEventId: options.lastEventId
      });
      return {
        disconnect: manager.disconnect
      };
    }
  };
}
