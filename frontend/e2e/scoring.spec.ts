import type { Page } from "@playwright/test";

import { DEMO_TURFS, bookAFreeSlot } from "./support/booking";
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

/**
 * Book a slot so this player organises a match of their own. Returns the match id.
 *
 * The named turf is only a preference: `bookAFreeSlot` moves on to another turf, day or
 * ground when that one has nothing free, which it eventually does because every run of
 * this suite leaves real bookings behind.
 */
async function organiseAMatch(
  page: Page,
  slug: string,
  { sport }: { sport?: string } = {},
): Promise<string> {
  await bookAFreeSlot(page, { turfs: [slug, ...DEMO_TURFS], sport });

  return page.evaluate(async (base) => {
    const token = await (
      window as never as { Clerk: { session: { getToken(): Promise<string> } } }
    ).Clerk.session.getToken();
    const mine = await (
      await fetch(`${base}/api/v1/matches/mine`, {
        headers: { Authorization: `Bearer ${token}` },
      })
    ).json();
    return mine[0].id as string;
  }, apiBaseUrl());
}

/** Put the organiser (the only player on a fresh match) on team A. */
async function putMyselfOnTeamA(page: Page) {
  await page.getByRole("button", { name: "→ A" }).first().click();
  await page.getByRole("button", { name: "Save teams" }).click();
  // The heading counts what the server came back with, so it settles the save.
  await expect(page.getByRole("heading", { name: /Team A\s*1 player/ })).toBeVisible();
}

test.describe("scorecard", () => {
  requiresClerk();

  test("the organiser builds teams, enters a score and submits it", async ({
    signedInPage: page,
  }) => {
    await finishOnboarding(page);
    const matchId = await organiseAMatch(page, "dhanmondi-arena", {
      sport: "Football",
    });

    await page.goto(`/matches/${matchId}`);
    await page.getByRole("link", { name: "Scorecard" }).click();
    await expect(page).toHaveURL(/\/scorecard$/);
    await expect(page.getByTestId("scorecard-status")).toHaveText("Draft");

    await putMyselfOnTeamA(page);

    await page.getByRole("spinbutton", { name: "Team A", exact: true }).fill("2");
    await page.getByRole("spinbutton", { name: "Team B", exact: true }).fill("1");
    await page.getByRole("button", { name: "Submit for confirmation" }).click();

    await expect(page.getByTestId("scorecard-status")).toHaveText(
      "Submitted, awaiting confirmation",
    );
    // Submitting opens the post-match sheet, which with nobody else on the roster has
    // nothing to ask about.
    await expect(page.getByText("Final score")).toHaveCount(0);
  });

  test("goals that beat the team's score are rejected", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    const matchId = await organiseAMatch(page, "dhanmondi-arena", {
      sport: "Football",
    });

    await page.goto(`/matches/${matchId}/scorecard`);
    await putMyselfOnTeamA(page);

    await page.getByRole("spinbutton", { name: "Team A", exact: true }).fill("1");
    await page
      .getByRole("spinbutton", { name: /Goals$/ })
      .first()
      .fill("3");
    await page.getByRole("button", { name: "Submit for confirmation" }).click();

    // Not `getByRole("alert")`: Next's route announcer is one too.
    await expect(page.getByText(/3 goals between them/)).toBeVisible();
    // Rejected means rejected: the card is still a draft.
    await expect(page.getByTestId("scorecard-status")).toHaveText("Draft");
  });

  test("a card that is not locked has no public page", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    const matchId = await organiseAMatch(page, "banani-sports-hub");

    const response = await page.goto(`/scorecards/${matchId}`);
    expect(response?.status()).toBe(404);
  });
});
