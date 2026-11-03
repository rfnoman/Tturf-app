import type { Page } from "@playwright/test";

import { apiBaseUrl } from "./support/clerk-users";
import { expect, requiresClerk, test } from "./support/fixtures";

/**
 * Phase 02 happy paths against the seeded demo turfs (`manage.py seed_demo`).
 *
 * The fixtures sign in a brand-new player, so each spec first walks the onboarding
 * wizard — the `(player)` route group bounces an unfinished profile to it, and these
 * specs are about turfs, not about that gate.
 */
async function finishOnboarding(page: Page) {
  await page.goto("/onboarding");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: /Football/ }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Finish" }).click();
  await expect(page).toHaveURL(/\/profile/);
}

test.describe("turf discovery", () => {
  requiresClerk();

  test.beforeEach(async ({ signedInPage: page }) => {
    await finishOnboarding(page);
  });

  test("a player sees the seeded turfs and can filter by sport", async ({ signedInPage: page }) => {
    await page.goto("/turfs");
    await expect(page.getByRole("heading", { level: 1, name: "Find a turf" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Mirpur Turf Club" })).toBeVisible();

    await page.getByLabel("Sport").selectOption("badminton");
    // Debounced, so wait for the result line rather than racing the request.
    await expect(page.getByRole("heading", { name: "Uttara Green Ground" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Dhanmondi Arena" })).toBeVisible();
  });

  test("the map view renders tiles and pins", async ({ signedInPage: page }) => {
    await page.goto("/turfs");
    await page.getByRole("button", { name: "Map", exact: true }).click();

    const map = page.getByRole("application", { name: "Map" });
    await expect(map).toBeVisible();
    // Leaflet is loaded through a browser-only dynamic import, so the pins only exist
    // once it has hydrated — this is the regression guard for that.
    await expect(map.getByRole("button", { name: "Mirpur Turf Club" })).toBeVisible();
  });

  test("an unapproved turf is not reachable", async ({ signedInPage: page }) => {
    const response = await page.goto("/turfs/not-a-real-turf");
    expect(response?.status()).toBe(404);
  });
});

test.describe("turf detail", () => {
  requiresClerk();

  test.beforeEach(async ({ signedInPage: page }) => {
    await finishOnboarding(page);
  });

  test("shows priced slots and lets a player pick one", async ({ signedInPage: page }) => {
    await page.goto("/turfs/dhanmondi-arena");
    await expect(page.getByRole("heading", { level: 1, name: "Dhanmondi Arena" })).toBeVisible();

    // Tomorrow, so the whole day's slots are in the future whatever time the suite runs.
    const tomorrow = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Dhaka" }).format(
      new Date(Date.now() + 86_400_000),
    );
    await page.getByLabel("Date").fill(tomorrow);

    // A turf has several grounds and repeated runs can book one of them out for a day,
    // so this picks the first ground that actually has a slot rather than assuming the
    // default one does.
    const open = page.locator("[data-slot-start][data-slot-available='true']");
    const grounds = await page.locator("#ground option").count();
    for (let index = 0; index < grounds; index += 1) {
      const value = await page.locator("#ground option").nth(index).getAttribute("value");
      await page.locator("#ground").selectOption(value);
      if ((await open.count()) > 0) break;
    }

    // Selected on the data hook, not on the text: once a slot is picked, the review
    // panel adds a "Book for ৳…" button that a price-based locator also matches.
    const slot = open.first();
    await expect(slot).toBeVisible();
    await slot.click();
    await expect(slot).toHaveAttribute("aria-pressed", "true");
  });

  test("slot prices come from the turf's own price rules", async ({ signedInPage: page }) => {
    // Mirpur prices peak evenings at ৳3200 on its 90-minute pitch (demo data).
    await page.goto("/turfs/mirpur-turf-club");
    await page.getByLabel("Ground").selectOption({ label: "Pitch 1 — Football" });

    const tomorrow = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Dhaka" }).format(
      new Date(Date.now() + 86_400_000),
    );
    await page.getByLabel("Date").fill(tomorrow);

    await expect(page.locator("[data-slot-start]", { hasText: "৳3200" }).first()).toBeVisible();
  });

  test("availability matches what the API reports", async ({ signedInPage: page }) => {
    await page.goto("/turfs/dhanmondi-arena");
    const tomorrow = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Dhaka" }).format(
      new Date(Date.now() + 86_400_000),
    );
    await page.getByLabel("Date").fill(tomorrow);
    await expect(page.locator("[data-slot-start]").first()).toBeVisible();

    const fromApi = await page.evaluate(
      async ([base, date]) => {
        const token = await (
          window as never as { Clerk: { session: { getToken(): Promise<string> } } }
        ).Clerk.session.getToken();
        const turf = await (
          await fetch(`${base}/api/v1/turfs/dhanmondi-arena`, {
            headers: { Authorization: `Bearer ${token}` },
          })
        ).json();
        const availability = await (
          await fetch(`${base}/api/v1/grounds/${turf.grounds[0].id}/availability?date=${date}`, {
            headers: { Authorization: `Bearer ${token}` },
          })
        ).json();
        return availability.slots.length as number;
      },
      [apiBaseUrl(), tomorrow] as const,
    );

    await expect(page.locator("[data-slot-start]")).toHaveCount(fromApi);
  });
});

test.describe("turf registration", () => {
  requiresClerk();

  test("an owner registers a turf and it starts as a draft", async ({ signedInPage: page }) => {
    await finishOnboarding(page);

    await page.goto("/owner");
    await expect(page.getByRole("heading", { level: 1, name: "Turf dashboard" })).toBeVisible();
    await page.getByRole("link", { name: "Register a turf" }).first().click();

    await expect(page).toHaveURL(/\/owner\/new/);
    await page.getByLabel("Turf name").fill("E2E Test Turf");
    await page.getByLabel("Address").fill("Road 1, Dhanmondi, Dhaka");
    await page.getByLabel("Area", { exact: true }).fill("Dhanmondi");
    await page.getByRole("button", { name: "Next", exact: true }).click();

    // Step 2 is the map picker; the default Dhaka pin is fine for this.
    await expect(page.getByRole("heading", { name: "Where is it?" })).toBeVisible();
    await page.getByRole("button", { name: "Next", exact: true }).click();

    await page.getByRole("button", { name: "Floodlights" }).click();
    await page.getByRole("button", { name: "Create draft" }).click();

    await expect(page).toHaveURL(/\/owner\/e2e-test-turf/);
    await expect(page.getByText("Draft")).toBeVisible();
    // A draft has no grounds yet, so it cannot be submitted — and the API says why.
    // Matched on the text rather than role=alert: Next's route announcer is one too.
    await page.getByRole("button", { name: "Submit for review" }).click();
    await expect(page.getByText(/Add at least one ground/)).toBeVisible();
  });

  test("a brand-new owner has no turfs", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    await page.goto("/owner");
    await expect(page.getByText("You have not registered a turf yet.")).toBeVisible();
  });
});
