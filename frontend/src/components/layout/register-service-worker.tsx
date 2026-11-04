"use client";

import { useEffect } from "react";

/**
 * Registers the service worker on every visit.
 *
 * Phase 09 registered it only when a player turned push notifications on, which meant
 * the offline page was cached for nobody else. Registration is cheap and idempotent;
 * push stays opt-in because it needs a *subscription*, which this does not create.
 */
export function RegisterServiceWorker() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    // Failure is not worth reporting: no worker means no offline page, and every other
    // part of the app works exactly as before.
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }, []);

  return null;
}
