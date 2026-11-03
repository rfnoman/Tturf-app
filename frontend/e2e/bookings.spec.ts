import type { Page } from "@playwright/test";

import { apiBaseUrl } from "./support/clerk-users";
import { expect, requiresClerk, test } from "./support/fixtures";

/** Dhaka-local YYYY-MM-DD, which is what every date control in the app expects. */
function dhakaDate(offsetDays = 0): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Dhaka" }).format(
    new Date(Date.now() + offsetDays * 86_400_000),
  );
}

async function finishOnboarding(page: Page) {
  await page.goto("/onboarding");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: /Football/ }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Finish" }).click();
  await expect(page).toHaveURL(/\/profile/);
}

/** Book the first free slot on a turf, returning the booking's id. */
async function bookFirstFreeSlot(page: Page, slug: string): Promise<string> {
  await page.goto(`/turfs/${slug}`);
  await page.getByLabel("Date").fill(dhakaDate(1));

  // A turf has several grounds, and a run that books every slot on one of them must not
  // break the next run: take the first ground that still has something free.
  const open = page.locator("[data-slot-start][data-slot-available='true']");
  const grounds = await page.locator("#ground option").count();
  for (let index = 0; index < grounds; index += 1) {
    const value = await page.locator("#ground option").nth(index).getAttribute("value");
    await page.locator("#ground").selectOption(value);
    if ((await open.count()) > 0) break;
  }

  const slot = open.first();
  await expect(slot).toBeVisible();
  await slot.click();
  await page.getByRole("button", { name: /^Book for/ }).click();

  await expect(page).toHaveURL(/\/bookings\/[0-9a-f-]+$/);
  return page.url().split("/").pop()!;
}

test.describe("booking a slot", () => {
  requiresClerk();

  test.beforeEach(async ({ signedInPage: page }) => {
    await finishOnboarding(page);
  });

  test("a new player's booking waits for the turf to confirm", async ({ signedInPage: page }) => {
    await bookFirstFreeSlot(page, "dhanmondi-arena");

    // DECISIONS D3: no track record, so it is held rather than confirmed. "Reserved"
    // appears twice on the page — as the status badge and as a timeline entry.
    await expect(page.getByText("Reserved").first()).toBeVisible();
    await expect(page.getByText(/has not confirmed yet/)).toBeVisible();
    await expect(page.getByText("Cash at the turf")).toBeVisible();
  });

  test("the booking appears in my bookings and the slot is no longer free", async ({
    signedInPage: page,
  }) => {
    await bookFirstFreeSlot(page, "banani-sports-hub");

    await page.goto("/bookings");
    await expect(page.getByRole("heading", { name: "Banani Sports Hub" })).toBeVisible();

    // The Phase 02 availability selector picks bookings up through the provider
    // registry, so a booked slot must now read as taken.
    await page.goto("/turfs/banani-sports-hub");
    await page.getByLabel("Date").fill(dhakaDate(1));
    await expect(page.getByText("BOOKED").first()).toBeVisible();
  });

  test("a player can cancel their own booking", async ({ signedInPage: page }) => {
    await bookFirstFreeSlot(page, "uttara-green-ground");

    await page.getByLabel("Reason").fill("Plans changed");
    await page.getByRole("button", { name: "Cancel booking" }).click();

    await expect(page.getByText("Cancelled").first()).toBeVisible();
    await expect(page.getByText("Plans changed").first()).toBeVisible();
  });

  test("the timeline records every transition", async ({ signedInPage: page }) => {
    await bookFirstFreeSlot(page, "bashundhara-play-zone");

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
    await bookFirstFreeSlot(page, "mirpur-turf-club");

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
