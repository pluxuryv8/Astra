import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { mergeEvents, statusTone } from "../legacy_ui/ui/utils";
import type { EventItem } from "../legacy_ui/types";

describe("mergeEvents", () => {
  it("deduplicates by seq and preserves order", () => {
    const base: EventItem[] = [
      { id: "a", seq: 1, type: "run_started", message: "", ts: 1 },
      { id: "b", seq: 2, type: "task_started", message: "", ts: 2 }
    ];
    const incoming: EventItem[] = [
      { id: "dup", seq: 2, type: "task_started", message: "", ts: 3 },
      { id: "c", seq: 3, type: "task_done", message: "", ts: 4 }
    ];
    const result = mergeEvents(base, incoming, 10);
    assert.equal(result.events.length, 3);
    assert.deepEqual(result.events.map((e) => e.seq), [1, 2, 3]);
    assert.equal(result.lastSeq, 3);
  });

  it("trims to limit", () => {
    const events: EventItem[] = [
      { id: "a", seq: 1, type: "run_started", message: "", ts: 1 },
      { id: "b", seq: 2, type: "task_started", message: "", ts: 2 },
      { id: "c", seq: 3, type: "task_done", message: "", ts: 3 }
    ];
    const result = mergeEvents([], events, 2);
    assert.equal(result.events.length, 2);
    assert.deepEqual(result.events.map((e) => e.seq), [2, 3]);
  });
});

describe("statusTone", () => {
  it("maps statuses to tones", () => {
    assert.equal(statusTone("running"), "ok");
    assert.equal(statusTone("paused"), "warn");
    assert.equal(statusTone("waiting_approval"), "warn");
    assert.equal(statusTone("failed"), "error");
    assert.equal(statusTone("unknown"), "muted");
  });
});
