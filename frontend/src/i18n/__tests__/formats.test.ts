import { describe, expect, it } from "vitest";

import { formatDay, formatMoney, formatWhen } from "../formats";

describe("formatMoney", () => {
  it("drops the paisa nobody charges", () => {
    // The API sends Decimals as strings: "1200.00" rendered straight into `৳{price}`
    // read as ৳1200.00 on every price in the app before Phase 11.
    expect(formatMoney("1200.00", "en")).toBe("৳1,200");
    expect(formatMoney(1200, "en")).toBe("৳1,200");
  });

  it("keeps the paisa somebody is owed", () => {
    expect(formatMoney("337.50", "en")).toBe("৳337.50");
  });

  it("says nothing rather than zero when there is no price", () => {
    // "No price set" and "free" are different facts, and a ground with no price rule
    // cannot be booked — showing ৳0 would invite somebody to try.
    expect(formatMoney(null, "en")).toBe("—");
    expect(formatMoney("", "en")).toBe("—");
    expect(formatMoney("not a number", "en")).toBe("—");
  });

  it("writes Bangla with the digits Bangladeshi money apps use", () => {
    // DECISIONS D62: Bangla words, Western digits — bKash, Nagad and Pathao all do
    // this, and a price is the one thing nobody should have to read twice.
    expect(formatMoney("1200.00", "bn")).toBe("৳1,200");
  });
});

describe("formatWhen", () => {
  const kickoff = "2026-11-05T13:30:00Z"; // 19:30 in Dhaka

  it("shows Dhaka time whoever is looking", () => {
    // A player checking a booking from abroad still has to be at the turf at 19:30.
    expect(formatWhen(kickoff, "en", "time")).toBe("19:30");
  });

  it("translates the month", () => {
    expect(formatWhen(kickoff, "en", "dayMonth")).toBe("5 Nov");
    expect(formatWhen(kickoff, "bn", "dayMonth")).toContain("নভে");
  });

  it("reads a plain day as noon so no time zone can shift it", () => {
    // `2026-11-05` parsed as UTC midnight is 05:00 in Dhaka — fine — but the same date
    // one hour earlier in UTC would print the 4th. Noon has six hours of slack.
    expect(formatDay("2026-11-05", "en")).toBe("5 Nov");
  });
});

describe("env", () => {
  it("treats an empty variable as unset", async () => {
    // `process.env.X ?? fallback` does not do this: `??` catches null and undefined, and
    // an environment variable set to "" is neither. Docker turns an unset ARG into an
    // empty ENV, so the production build died on `new URL("")` — which is how this
    // function came to exist (Phase 11 step 8).
    const { env } = await import("../../lib/env");

    expect(env("", "fallback")).toBe("fallback");
    expect(env("   ", "fallback")).toBe("fallback");
    expect(env(undefined, "fallback")).toBe("fallback");
    expect(env("https://turfapp.com.bd", "fallback")).toBe("https://turfapp.com.bd");
  });
});
