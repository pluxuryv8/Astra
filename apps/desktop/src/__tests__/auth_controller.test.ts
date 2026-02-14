/// <reference types="node" />
import assert from "node:assert/strict";
import { beforeEach, describe, it } from "node:test";
import { ApiError, isNetworkError } from "../shared/api/errors";
import { clearToken, connect, getToken, setToken } from "../shared/api/authController";

function createResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body)
  } as Response;
}

function normalizeUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

beforeEach(() => {
  const store = new Map<string, string>();
  (globalThis as unknown as { localStorage: Storage }).localStorage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => {
      store.clear();
    },
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    get length() {
      return store.size;
    }
  };
  clearToken();
});

describe("auth connect", () => {
  it("uses existing token and bootstraps", async () => {
    setToken("token-1");
    let statusCalls = 0;
    let bootstrapCalls = 0;

    globalThis.fetch = (async (input: RequestInfo | URL, _init?: RequestInit) => {
      void _init;
      const url = normalizeUrl(input);
      if (url.endsWith("/auth/status")) {
        statusCalls += 1;
        return createResponse(200, { initialized: true, token_required: true });
      }
      if (url.endsWith("/auth/bootstrap")) {
        bootstrapCalls += 1;
        return createResponse(200, { status: "ок" });
      }
      return createResponse(200, {});
    }) as typeof fetch;

    const token = await connect("manual");
    assert.equal(token, "token-1");
    assert.equal(statusCalls, 1);
    assert.equal(bootstrapCalls, 1);
    assert.equal(getToken(), "token-1");
  });

  it("generates token when not initialized", async () => {
    clearToken();
    let statusCalls = 0;
    let bootstrapCalls = 0;

    globalThis.fetch = (async (input: RequestInfo | URL, _init?: RequestInit) => {
      void _init;
      const url = normalizeUrl(input);
      if (url.endsWith("/auth/status")) {
        statusCalls += 1;
        if (statusCalls === 1) {
          return createResponse(200, { initialized: false, token_required: true });
        }
        return createResponse(200, { initialized: true, token_required: true });
      }
      if (url.endsWith("/auth/bootstrap")) {
        bootstrapCalls += 1;
        return createResponse(200, { status: "создано" });
      }
      return createResponse(200, {});
    }) as typeof fetch;

    const token = await connect("manual");
    assert.ok(token);
    assert.equal(bootstrapCalls, 1);
    assert.equal(statusCalls, 2);
    assert.ok(getToken());
  });

  it("initialized without token -> auth error", async () => {
    clearToken();
    globalThis.fetch = (async (input: RequestInfo | URL, _init?: RequestInit) => {
      void _init;
      const url = normalizeUrl(input);
      if (url.endsWith("/auth/status")) {
        return createResponse(200, { initialized: true, token_required: true });
      }
      if (url.endsWith("/auth/bootstrap")) {
        return createResponse(200, { status: "ок" });
      }
      return createResponse(200, {});
    }) as typeof fetch;

    await assert.rejects(
      () => connect("manual"),
      (err: unknown) => err instanceof ApiError && err.code === "auth"
    );
  });

  it("network error -> SERVER_UNREACHABLE", async () => {
    globalThis.fetch = (async (input: RequestInfo | URL, _init?: RequestInit) => {
      void input;
      void _init;
      throw new TypeError("Failed to fetch");
    }) as typeof fetch;

    await assert.rejects(
      () => connect("manual"),
      (err: unknown) => isNetworkError(err) && err instanceof ApiError
    );
  });
});
