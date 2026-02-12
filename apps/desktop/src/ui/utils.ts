import type { EventItem } from "../types";

type MergeResult = {
  events: EventItem[];
  lastSeq: number;
};

export function mergeEvents(existing: EventItem[], incoming: EventItem[], limit: number): MergeResult {
  const merged = [...existing];
  const seenSeq = new Set<number>();
  let lastSeq = 0;

  for (const event of existing) {
    if (typeof event.seq === "number") {
      seenSeq.add(event.seq);
      if (event.seq > lastSeq) lastSeq = event.seq;
    }
  }

  for (const event of incoming) {
    const seq = typeof event.seq === "number" ? event.seq : null;
    if (seq !== null && seenSeq.has(seq)) continue;
    if (seq !== null) {
      seenSeq.add(seq);
      if (seq > lastSeq) lastSeq = seq;
    }
    merged.push(event);
  }

  merged.sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0));

  let trimmed = merged;
  if (trimmed.length > limit) {
    trimmed = trimmed.slice(-limit);
  }

  return { events: trimmed, lastSeq };
}

export function statusTone(status?: string | null): "ok" | "warn" | "error" | "muted" {
  if (!status) return "muted";
  if (status === "running") return "ok";
  if (status === "paused" || status === "planning" || status.includes("waiting")) return "warn";
  if (status === "failed" || status === "canceled") return "error";
  return "muted";
}
