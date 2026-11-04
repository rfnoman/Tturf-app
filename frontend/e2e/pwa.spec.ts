import { expect, test } from "@playwright/test";

/**
 * The installable shell. No sign-in: a manifest the browser cannot read, or an icon
 * that 404s, makes the app silently non-installable, and nothing else in the suite
 * would notice.
 */
test.describe("progressive web app", () => {
  test("serves a manifest the browser can install from", async ({ request }) => {
    const response = await request.get("/manifest.webmanifest");
    expect(response.status()).toBe(200);

    const manifest = await response.json();
    expect(manifest.short_name).toBe("TurfApp");
    expect(manifest.display).toBe("standalone");
    expect(manifest.start_url).toBe("/");

    // Chrome needs a 192 and a 512; Android needs a maskable one or it letterboxes the
    // icon inside a white circle.
    const icons = manifest.icons.map(
      (icon: { sizes: string; purpose: string }) => `${icon.sizes} ${icon.purpose}`,
    );
    expect(icons).toContain("192x192 any");
    expect(icons).toContain("512x512 any");
    expect(icons).toContain("512x512 maskable");
  });

  test("every icon the manifest names is a real PNG", async ({ request }) => {
    const manifest = await (await request.get("/manifest.webmanifest")).json();

    for (const icon of manifest.icons as { src: string }[]) {
      const response = await request.get(icon.src);
      expect(response.status(), icon.src).toBe(200);
      expect(response.headers()["content-type"], icon.src).toContain("image/png");
    }
  });

  test("the offline page stands alone, in both languages", async ({ page }) => {
    // It is cached once at install time, so it cannot depend on a session or a locale
    // cookie — and it has to make sense to whoever is looking at it.
    await page.goto("/offline");
    await expect(page.getByRole("heading", { name: "আপনি অফলাইনে আছেন" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "You are offline" })).toBeVisible();
  });

  test("registers a service worker that caches the offline page", async ({ page }) => {
    await page.goto("/");

    const cached = await page.evaluate(async () => {
      await navigator.serviceWorker.ready;
      const cache = await caches.open("turfapp-offline-v2");
      return Boolean(await cache.match("/offline"));
    });

    expect(cached).toBe(true);
  });
});
