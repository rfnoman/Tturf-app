import type { Page } from "@playwright/test";

import { DEMO_TURFS, bookAFreeSlot, dhakaDate } from "./support/booking";
import { apiBaseUrl } from "./support/clerk-users";
import { expect, requiresClerk, test } from "./support/fixtures";

async function finishOnboarding(page: Page) {
  await page.goto("/onboarding");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: /Football/ }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Finish" }).click();
  await expect(page).toHaveURL(/\/profile/);
}

test.describe("booking a slot", () => {
  requiresClerk();

  test.beforeEach(async ({ signedInPage: page }) => {
    await finishOnboarding(page);
  });

  test("a new player's booking waits for the turf to confirm", async ({ signedInPage: page }) => {
    await bookAFreeSlot(page, { turfs: ["dhanmondi-arena", ...DEMO_TURFS] });

    // DECISIONS D3: no track record, so it is held rather than confirmed. "Reserved"
    // appears twice on the page — as the status badge and as a timeline entry.
    await expect(page.getByText("Reserved").first()).toBeVisible();
    await expect(page.getByText(/has not confirmed yet/)).toBeVisible();
    // Exact: the Phase 10 payment card also says "cash at the turf" in its hint.
    await expect(page.getByText("Cash at the turf", { exact: true })).toBeVisible();
  });

  test("the booking appears in my bookings and the slot is no longer free", async ({
    signedInPage: page,
  }) => {
    const booked = await bookAFreeSlot(page, { turfs: ["banani-sports-hub", ...DEMO_TURFS] });
    // Which turf the helper settled on depends on what is still free, so the name is
    // read off the booking rather than assumed.
    const turfName = await page.getByRole("heading", { level: 1 }).textContent();

    await page.goto("/bookings");
    await expect(page.getByRole("heading", { name: turfName! })).toBeVisible();

    // The Phase 02 availability selector picks bookings up through the provider
    // registry, so a booked slot must now read as taken — on the day it was booked.
    await page.goto(`/turfs/${booked.turf}`);
    await page.getByLabel("Date").fill(booked.date);
    await expect(page.getByText("BOOKED").first()).toBeVisible();
  });

  test("a player can cancel their own booking", async ({ signedInPage: page }) => {
    await bookAFreeSlot(page, { turfs: ["uttara-green-ground", ...DEMO_TURFS] });

    await page.getByLabel("Reason").fill("Plans changed");
    await page.getByRole("button", { name: "Cancel booking" }).click();

    await expect(page.getByText("Cancelled").first()).toBeVisible();
    await expect(page.getByText("Plans changed").first()).toBeVisible();
  });

  test("the timeline records every transition", async ({ signedInPage: page }) => {
    await bookAFreeSlot(page, { turfs: ["bashundhara-play-zone", ...DEMO_TURFS] });

    const timeline = page.locator("ol");
    await expect(timeline.getByText("Reserved")).toBeVisible();

    await page.getByRole("button", { name: "Cancel booking" }).click();
    await expect(timeline.getByText("Cancelled")).toBeVisible();
  });
});

test.describe("staff actions", () => {
  requiresClerk();

  test("the counter refuses a walk-in until the turf is approved", async ({
    signedInPage: page,
  }) => {
    await finishOnboarding(page);

    // The turf is built through the API: this spec is about the *counter* flow, and
    // re-driving the whole registration UI here would only re-test Phase 02 while
    // making the failure message useless when something else breaks.
    const slug = await page.evaluate(async (base) => {
      const token = await (
        window as never as { Clerk: { session: { getToken(): Promise<string> } } }
      ).Clerk.session.getToken();
      const headers = {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      };

      const turf = await (
        await fetch(`${base}/api/v1/me/turfs`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            name: `E2E Counter Turf ${Date.now()}`,
            address: "Road 1, Dhanmondi",
            area: "Dhanmondi",
            latitude: 23.7465,
            longitude: 90.376,
          }),
        })
      ).json();

      for (let weekday = 0; weekday < 7; weekday += 1) {
        await fetch(`${base}/api/v1/me/turfs/${turf.slug}/hours`, {
          method: "POST",
          headers,
          body: JSON.stringify({ weekday, open_time: "06:00", close_time: "23:00" }),
        });
      }

      const sports = await (await fetch(`${base}/api/v1/sports`, { headers })).json();
      const football = sports.find((s: { slug: string }) => s.slug === "football");

      const ground = await (
        await fetch(`${base}/api/v1/me/turfs/${turf.slug}/grounds`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            name: "Pitch",
            max_players: 10,
            slot_minutes: 60,
            sport_format_ids: [football.formats[0].id],
          }),
        })
      ).json();

      await fetch(`${base}/api/v1/me/turfs/${turf.slug}/grounds/${ground.id}/prices`, {
        method: "POST",
        headers,
        // Equal times mean the full 24 hours, so every open minute is priced.
        body: JSON.stringify({
          weekdays: [],
          start_time: "00:00",
          end_time: "00:00",
          price: "2000.00",
        }),
      });
      await fetch(`${base}/api/v1/me/turfs/${turf.slug}/grounds/${ground.id}/activate`, {
        method: "POST",
        headers,
      });

      return turf.slug as string;
    }, apiBaseUrl());

    await page.goto(`/owner/${slug}/bookings?date=${dhakaDate(1)}`);

    await page.getByLabel("Name", { exact: true }).fill("Karim Uddin");
    await page.getByLabel("Phone", { exact: true }).fill("+8801711222333");
    await page.getByLabel("Start time").fill("10:00");
    await page.getByRole("button", { name: "Book", exact: true }).click();

    // The turf is still a draft, and only an approved turf takes bookings — including
    // at its own counter. What this asserts is that the API's reason reaches the
    // cashier rather than failing silently.
    //
    // Approving needs a platform admin, which an end-to-end run cannot grant itself,
    // so the rest of the counter flow (walk-in -> confirmed -> paid) is covered by the
    // backend tests in apps/bookings/tests/test_api.py.
    await expect(page.getByRole("alert").first()).toContainText("not accepting bookings");
    await expect(page.getByText("Karim Uddin")).toHaveCount(0);
  });
});

test.describe("notifications", () => {
  requiresClerk();

  test("booking produces a notification the bell can show", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    await bookAFreeSlot(page, { turfs: ["mirpur-turf-club", ...DEMO_TURFS] });

    // The bell reads its count on mount and then every 30s, so the page is reloaded
    // rather than waiting out a poll.
    await page.reload();
    await page.getByRole("button", { name: /unread notification/ }).click();
    await expect(page.getByText(/Booking requested/).first()).toBeVisible();

    // "Mark all read" is only rendered while something is unread, and the trigger
    // itself is hidden from the a11y tree while the menu is open — so its absence is
    // what says the badge cleared.
    await page.getByRole("button", { name: "Mark all read" }).click();
    await expect(page.getByRole("button", { name: "Mark all read" })).toHaveCount(0);
  });
});
