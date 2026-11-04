import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const nextConfig: NextConfig = {
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
