import { afterEach, describe, expect, it, vi } from "vitest";

import { CLIENT_CONFIG_FALLBACK, fetchClientConfig } from "../config-queries";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchClientConfig", () => {
  it("returns what the backend reports", async () => {
    const payload = { ...CLIENT_CONFIG_FALLBACK, self_assessed_rating_cap: 60 };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })),
    );

    await expect(fetchClientConfig()).resolves.toMatchObject({
      self_assessed_rating_cap: 60,
    });
  });

  it("falls back instead of throwing when the API is down", async () => {
    // A page that cannot reach Django should still render with sane limits.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("ECONNREFUSED");
      }),
    );

    await expect(fetchClientConfig()).resolves.toEqual(CLIENT_CONFIG_FALLBACK);
  });

  it("falls back on a non-2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("nope", { status: 503 })),
    );

    await expect(fetchClientConfig()).resolves.toEqual(CLIENT_CONFIG_FALLBACK);
  });

  it("mirrors the backend defaults, so a stale fallback is obvious", () => {
    expect(CLIENT_CONFIG_FALLBACK.self_assessed_rating_cap).toBe(75);
    expect(CLIENT_CONFIG_FALLBACK.rating_max).toBe(99);
    expect(CLIENT_CONFIG_FALLBACK.currency).toBe("BDT");
  });
});
