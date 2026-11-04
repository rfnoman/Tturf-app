import { createPublicApiClient } from "./client";
import type { components } from "./schema";

export type ClientConfig = components["schemas"]["ClientConfig"];

/**
 * Business rules the UI needs, read from the backend rather than duplicated here
 * (CLAUDE.md: configurable rules live in one place).
 *
 * `fetchClientConfig` never throws: a page that cannot reach the API should still
 * render with sane limits rather than a 500, so the server's own defaults are mirrored
 * as a last resort.
 */
export const CLIENT_CONFIG_FALLBACK: ClientConfig = {
  rating_min: 1,
  rating_max: 99,
  self_assessed_rating_cap: 75,
  onboarding_default_rating: 50,
  rating_provisional_matches: 10,
  default_player_weight_kg: 70,
  booking_horizon_days: 30,
  turf_delivery_cutoff_hours: 16,
  currency: "BDT",
  time_zone: "Asia/Dhaka",
  // 5 = Saturday, the day a Bangladeshi week starts (DECISIONS D56).
  week_starts_on: 5,
  // No key means no push, which is the right answer when the API is unreachable too.
  vapid_public_key: "",
};

export async function fetchClientConfig(): Promise<ClientConfig> {
  try {
    const { data } = await createPublicApiClient().GET("/api/v1/config");
    return data ?? CLIENT_CONFIG_FALLBACK;
  } catch {
    return CLIENT_CONFIG_FALLBACK;
  }
}
