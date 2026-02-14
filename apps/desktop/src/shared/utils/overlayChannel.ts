import type { OverlayState } from "../types/ui";

const CHANNEL_NAME = "astra-ui";
const STORAGE_KEY = "astra.ui.overlay_state";

export function publishOverlayState(state: OverlayState) {
  if (typeof window !== "undefined") {
    try {
      if ("BroadcastChannel" in window) {
        const channel = new BroadcastChannel(CHANNEL_NAME);
        channel.postMessage({ type: "overlay_state", payload: state });
        channel.close();
      }
    } catch {
      // ignore
    }
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // ignore
    }
  }
}

export function subscribeOverlayState(handler: (state: OverlayState) => void) {
  let channel: BroadcastChannel | null = null;
  if (typeof window !== "undefined" && "BroadcastChannel" in window) {
    channel = new BroadcastChannel(CHANNEL_NAME);
    channel.onmessage = (event) => {
      const data = event.data as { type?: string; payload?: OverlayState };
      if (data?.type === "overlay_state" && data.payload) {
        handler(data.payload);
      }
    };
  }

  const onStorage = (event: StorageEvent) => {
    if (event.key !== STORAGE_KEY || !event.newValue) return;
    try {
      const parsed = JSON.parse(event.newValue) as OverlayState;
      handler(parsed);
    } catch {
      // ignore
    }
  };

  window.addEventListener("storage", onStorage);

  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as OverlayState;
      handler(parsed);
    }
  } catch {
    // ignore
  }

  return () => {
    channel?.close();
    window.removeEventListener("storage", onStorage);
  };
}

export function getStoredOverlayState(): OverlayState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as OverlayState;
  } catch {
    return null;
  }
}
