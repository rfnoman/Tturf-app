import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

/**
 * Security headers that do not change per response.
 *
 * The content policy is *not* here — it needs a fresh nonce for each page, so it is set
 * in `src/proxy.ts`. Django sets its own equivalents for API responses; these cover the
 * pages a player actually loads.
 */
const SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // The app asks for geolocation ("near me") and notifications, and nothing else.
  {
    key: "Permissions-Policy",
    value: "geolocation=(self), notifications=(self), camera=(), microphone=(), payment=()",
  },
  { key: "X-Frame-Options", value: "DENY" },
];

const nextConfig: NextConfig = {
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },

  // Cache Components stays off (DECISIONS D14), revisited in Phase 11 as that note
  // asked. The reason has not changed and is not a matter of effort: almost every page
  // here renders one player's own data — their bookings, their matches, their profile —
  // so there is nothing a shared render cache can hold. What *is* shared and expensive
  // is cached server-side instead, where it can be invalidated when the data changes
  // (`apps/core/cache.py`): the turf page and the leaderboards.
  cacheComponents: false,

  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

// Points next-intl at src/i18n/request.ts.
const withNextIntl = createNextIntlPlugin();

export default withNextIntl(nextConfig);
