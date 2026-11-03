import { afterEach, describe, expect, it, vi } from "vitest";

import { createApiClient, createPublicApiClient } from "@/lib/api/client";

const BASE = "http://api.test";

function mockFetch(): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("createApiClient", () => {
  it("attaches the Clerk token as a bearer header", async () => {
    const fetchMock = mockFetch();
    const client = createApiClient(async () => "session-token-abc", BASE);

    await client.GET("/api/v1/me");

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.headers.get("Authorization")).toBe("Bearer session-token-abc");
    expect(request.url).toBe(`${BASE}/api/v1/me`);
  });

  it("sends no Authorization header when nobody is signed in", async () => {
    const fetchMock = mockFetch();
    const client = createApiClient(async () => null, BASE);

    await client.GET("/api/v1/me");

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.headers.get("Authorization")).toBeNull();
  });

  it("asks for a fresh token on every request", async () => {
    // Clerk session tokens are short-lived, so a token must never be cached per client.
    mockFetch();
    const getToken = vi.fn(async () => "token");
    const client = createApiClient(getToken, BASE);

    await client.GET("/api/v1/me");
    await client.GET("/api/v1/me");

    expect(getToken).toHaveBeenCalledTimes(2);
  });

  it("builds URLs without duplicating the /api/v1 prefix", async () => {
    const fetchMock = mockFetch();
    const client = createPublicApiClient(BASE);

    await client.GET("/api/v1/health");

    const request = fetchMock.mock.calls[0][0] as Request;
    expect(request.url).toBe(`${BASE}/api/v1/health`);
  });
});
