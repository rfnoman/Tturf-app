"use client";

import dynamic from "next/dynamic";

export type { MapMarker } from "./turf-map-impl";

/**
 * Browser-only wrapper around the Leaflet map.
 *
 * Leaflet reads `window` as its module is evaluated, and `"use client"` alone does not
 * prevent that: Next still evaluates client modules on the server to produce the initial
 * HTML, which made every page importing the map a 500. `ssr: false` is the fix, and it
 * lives here rather than at each call site so server components can keep importing
 * `TurfMap` normally.
 */
export const TurfMap = dynamic(
  () => import("./turf-map-impl").then((module) => module.TurfMapImpl),
  {
    ssr: false,
    loading: () => (
      <div
        className="bg-muted h-80 w-full animate-pulse rounded-xl border"
        role="application"
        aria-label="Map"
        aria-busy="true"
      />
    ),
  },
);
