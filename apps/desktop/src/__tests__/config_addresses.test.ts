/// <reference types="node" />
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolveApiBaseUrlFromEnv } from "../shared/api/config";

describe("address config", () => {
  it("test_desktop_config_resolves_base_url", () => {
    const resolved = resolveApiBaseUrlFromEnv({
      VITE_ASTRA_API_BASE_URL: "http://127.0.0.1:18055/api/v1/"
    });
    assert.equal(resolved, "http://127.0.0.1:18055/api/v1");
  });

  it("requires explicit VITE_ASTRA_API_BASE_URL", () => {
    assert.throws(() => resolveApiBaseUrlFromEnv({}), /Missing VITE_ASTRA_API_BASE_URL/);
  });
});
