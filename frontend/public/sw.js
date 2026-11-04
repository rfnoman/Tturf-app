/**
 * Service worker: web push (Phase 09, D55) and one offline page (Phase 11).
 *
 * Deliberately **not** a caching worker. Almost everything here is per-player data
 * behind a session, and a cache that serves one player's bookings to the next is worse
 * than no cache at all — so nothing authenticated is ever stored.
 *
 * What it does cache is a single static page, shown when a *navigation* fails. On a
 * Dhaka 3G connection the difference between the browser's error page and "you are
 * offline, your bookings are still there" is the difference between a bug report and a
 * shrug.
 */

// Bump this whenever the offline page changes: the old cache is deleted on activate.
const OFFLINE_CACHE = "turfapp-offline-v2";
const OFFLINE_URL = "/offline";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(OFFLINE_CACHE)
      .then((cache) => cache.add(new Request(OFFLINE_URL, { cache: "reload" }))),
  );
  // Replace the push-only worker from Phase 09 without waiting for every tab to close.
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== OFFLINE_CACHE).map((key) => caches.delete(key))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  // Only page loads, and only when the network has actually failed. Every other
  // request — API calls included — goes straight to the network, uncached.
  if (event.request.mode !== "navigate") return;

  event.respondWith(
    fetch(event.request).catch(async () => {
      const cache = await caches.open(OFFLINE_CACHE);
      return (await cache.match(OFFLINE_URL)) ?? Response.error();
    }),
  );
});

self.addEventListener("push", (event) => {
  if (!event.data) return;

  let payload = {};
  try {
    payload = event.data.json();
  } catch {
    payload = { title: "TurfApp", body: event.data.text() };
  }

  event.waitUntil(
    self.registration.showNotification(payload.title || "TurfApp", {
      body: payload.body || "",
      // One tag per kind, so three hydration nudges do not stack into a wall.
      tag: payload.kind || "turfapp",
      data: { url: payload.url || "/" },
      icon: "/icons/192.png",
      badge: "/icons/192.png",
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data?.url || "/";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      // Focus a tab that is already open rather than opening a fourth one.
      for (const client of clients) {
        if ("focus" in client) {
          client.navigate(url);
          return client.focus();
        }
      }
      return self.clients.openWindow(url);
    }),
  );
});
