import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { useAppStore } from "../shared/store/appStore";

describe("notifications store", () => {
  it("auto dismisses notification after timer callback", () => {
    const originalSetTimeout = globalThis.setTimeout;
    const originalClearTimeout = globalThis.clearTimeout;

    const callbacks = new Map<number, () => void>();
    let seq = 0;

    globalThis.setTimeout = (((handler: TimerHandler) => {
      seq += 1;
      const id = seq;
      callbacks.set(id, () => {
        if (typeof handler === "function") {
          handler();
        }
      });
      return id as unknown as ReturnType<typeof setTimeout>;
    }) as typeof setTimeout);

    globalThis.clearTimeout = (((id?: number | undefined) => {
      if (typeof id === "number") {
        callbacks.delete(id);
      }
    }) as typeof clearTimeout);

    try {
      useAppStore.getState().clearNotifications();
      useAppStore.getState().addNotification({
        id: "test-info-1",
        ts: new Date().toISOString(),
        title: "Инфо",
        body: "Должно исчезнуть",
        severity: "info"
      });

      assert.equal(useAppStore.getState().notifications.length, 1);
      assert.equal(callbacks.size, 1);

      const callback = callbacks.values().next().value;
      assert.equal(typeof callback, "function");
      callback();

      assert.equal(useAppStore.getState().notifications.length, 0);
    } finally {
      globalThis.setTimeout = originalSetTimeout;
      globalThis.clearTimeout = originalClearTimeout;
      useAppStore.getState().clearNotifications();
    }
  });
});
