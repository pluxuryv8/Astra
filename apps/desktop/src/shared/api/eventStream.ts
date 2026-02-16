import type { EventItem } from "../types/api";

export type StreamState = "idle" | "connecting" | "open" | "reconnecting" | "offline" | "closed";

export type StreamCallbacks = {
  onEvent: (event: EventItem) => void;
  onStateChange: (state: StreamState) => void;
  onError?: (message: string) => void;
  onReconnect?: () => void;
  getLastEventId?: () => number | null;
};

export type StreamOptions = {
  runId: string;
  token?: string | null;
  lastEventId?: number | null;
};

const HEARTBEAT_TIMEOUT = 25000;
const HEARTBEAT_CHECK = 4000;
const PREFLIGHT_TIMEOUT = 4000;
const RECONNECT_BASE = 800;
const RECONNECT_CAP = 20000;
const MAX_RECONNECT_ATTEMPTS = 6;
const DEDUP_LIMIT = 2400;

function buildEventHash(event: EventItem): string {
  const payload = event.payload && typeof event.payload === "object" ? event.payload : {};
  const subset = {
    id: (payload as Record<string, unknown>).id ?? null,
    step_id: (payload as Record<string, unknown>).step_id ?? null,
    task_id: (payload as Record<string, unknown>).task_id ?? null,
    status: (payload as Record<string, unknown>).status ?? null
  };
  return `${event.type}|${event.ts ?? ""}|${event.id ?? ""}|${JSON.stringify(subset)}`;
}

export function createEventStreamManager(baseUrl: string, eventTypes: string[], callbacks: StreamCallbacks) {
  let eventSource: EventSource | null = null;
  let state: StreamState = "idle";
  let reconnectAttempt = 0;
  let reconnectTimer: number | null = null;
  let heartbeatTimer: number | null = null;
  let lastEventAt = 0;
  let current: StreamOptions | null = null;
  let wasReconnecting = false;
  let connectNonce = 0;

  const seenSeq = new Set<number>();
  const seenHashes = new Set<string>();
  const hashQueue: string[] = [];
  const seqQueue: number[] = [];

  const setState = (next: StreamState) => {
    if (state === next) return;
    state = next;
    callbacks.onStateChange(next);
  };

  const clearTimers = () => {
    if (reconnectTimer) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (heartbeatTimer) {
      window.clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
  };

  const closeSource = () => {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  };

  const markSeq = (seq: number) => {
    if (seenSeq.has(seq)) return false;
    seenSeq.add(seq);
    seqQueue.push(seq);
    if (seqQueue.length > DEDUP_LIMIT) {
      const removed = seqQueue.shift();
      if (typeof removed === "number") seenSeq.delete(removed);
    }
    return true;
  };

  const markHash = (hash: string) => {
    if (seenHashes.has(hash)) return false;
    seenHashes.add(hash);
    hashQueue.push(hash);
    if (hashQueue.length > DEDUP_LIMIT) {
      const removed = hashQueue.shift();
      if (removed) seenHashes.delete(removed);
    }
    return true;
  };

  const handleEvent = (event: EventItem) => {
    lastEventAt = Date.now();
    if (typeof event.seq === "number") {
      if (!markSeq(event.seq)) return;
    } else {
      const hash = buildEventHash(event);
      if (!markHash(hash)) return;
    }
    callbacks.onEvent(event);
  };

  const scheduleReconnect = () => {
    const target = current;
    if (!target) return;
    if (reconnectTimer) return;
    reconnectAttempt += 1;
    if (reconnectAttempt > MAX_RECONNECT_ATTEMPTS) {
      setState("offline");
      return;
    }
    const base = Math.min(RECONNECT_CAP, RECONNECT_BASE * Math.pow(2, reconnectAttempt));
    const jitter = Math.round(base * (0.25 * Math.random()));
    const delay = base + jitter;
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      wasReconnecting = true;
      connect(target);
    }, delay);
  };

  const startHeartbeat = () => {
    if (heartbeatTimer) return;
    heartbeatTimer = window.setInterval(() => {
      if (!eventSource) return;
      if (Date.now() - lastEventAt > HEARTBEAT_TIMEOUT) {
        callbacks.onError?.("Поток событий молчит слишком долго");
        reconnectAttempt = Math.max(1, reconnectAttempt);
        closeSource();
        setState("reconnecting");
        scheduleReconnect();
      }
    }, HEARTBEAT_CHECK);
  };

  const buildStreamUrl = (options: StreamOptions): URL => {
    const url = new URL(`${baseUrl}/runs/${options.runId}/events`);
    if (options.token) {
      url.searchParams.set("token", options.token);
    }
    const lastEventId = callbacks.getLastEventId?.() ?? options.lastEventId;
    if (lastEventId) {
      url.searchParams.set("last_event_id", String(lastEventId));
    }
    return url;
  };

  const preflightUrl = (url: URL): URL => {
    const probe = new URL(url.toString());
    probe.searchParams.set("once", "1");
    return probe;
  };

  const preflightErrorMessage = (status: number, url: URL): string => {
    if (status === 401) {
      return `SSE недоступен: 401 (token required/invalid). URL: ${url.origin}`;
    }
    if (status === 404) {
      return `SSE недоступен: run не найден (404). URL: ${url.origin}`;
    }
    return `SSE недоступен: HTTP ${status}. URL: ${url.origin}`;
  };

  const openEventSource = (url: URL) => {
    eventSource = new EventSource(url.toString());
    eventSource.onopen = () => {
      lastEventAt = Date.now();
      setState("open");
      startHeartbeat();
      if (wasReconnecting) {
        callbacks.onReconnect?.();
        wasReconnecting = false;
      }
      reconnectAttempt = 0;
    };
    eventSource.onerror = () => {
      callbacks.onError?.(`SSE соединение потеряно. Проверь API (${url.origin}) и токен.`);
      closeSource();
      setState("reconnecting");
      scheduleReconnect();
    };

    eventTypes.forEach((type) => {
      eventSource?.addEventListener(type, (evt) => {
        try {
          const parsed = JSON.parse((evt as MessageEvent).data) as EventItem;
          handleEvent(parsed);
        } catch {
          callbacks.onError?.("Не удалось прочитать событие");
        }
      });
    });
  };

  const connect = (options: StreamOptions) => {
    const nonce = ++connectNonce;
    current = options;
    closeSource();
    clearTimers();
    setState(reconnectAttempt > 0 ? "reconnecting" : "connecting");
    const url = buildStreamUrl(options);
    const probeUrl = preflightUrl(url);
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), PREFLIGHT_TIMEOUT);
    fetch(probeUrl.toString(), { method: "GET", cache: "no-store", signal: controller.signal })
      .then((response) => {
        window.clearTimeout(timer);
        if (nonce !== connectNonce) return;
        if (!response.ok) {
          callbacks.onError?.(preflightErrorMessage(response.status, url));
          closeSource();
          setState("offline");
          scheduleReconnect();
          return;
        }
        openEventSource(url);
      })
      .catch(() => {
        window.clearTimeout(timer);
        if (nonce !== connectNonce) return;
        callbacks.onError?.(`SSE недоступен: API unreachable (${url.origin}). Проверь URL/порт.`);
        closeSource();
        setState("offline");
        scheduleReconnect();
      });
  };

  const disconnect = () => {
    connectNonce += 1;
    clearTimers();
    closeSource();
    current = null;
    reconnectAttempt = 0;
    wasReconnecting = false;
    setState("closed");
  };

  return {
    connect,
    disconnect,
    getState: () => state
  };
}
