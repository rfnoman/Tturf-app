/**
 * Service worker: web push only (Phase 09, DECISIONS D55).
 *
 * Deliberately not a caching or offline worker. Caching an authenticated app badly is
 * worse than not caching it at all, and that is a decision for its own phase.
 */

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
      icon: "/favicon.ico",
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
