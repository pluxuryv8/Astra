import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { deriveOverlayStatus } from "../ui/overlay_utils";

describe("deriveOverlayStatus", () => {
  it("prioritizes approvals", () => {
    const status = deriveOverlayStatus("running", true, false);
    assert.equal(status.label, "Нужно подтверждение");
    assert.equal(status.tone, "warn");
  });

  it("shows error", () => {
    const status = deriveOverlayStatus("running", false, true);
    assert.equal(status.label, "Ошибка");
    assert.equal(status.tone, "error");
  });

  it("maps run statuses", () => {
    assert.equal(deriveOverlayStatus("running", false, false).tone, "ok");
    assert.equal(deriveOverlayStatus("paused", false, false).tone, "warn");
    assert.equal(deriveOverlayStatus("waiting_approval", false, false).tone, "warn");
    assert.equal(deriveOverlayStatus("done", false, false).tone, "ok");
  });
});
