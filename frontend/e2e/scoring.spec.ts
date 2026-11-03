import type { Page } from "@playwright/test";

import { apiBaseUrl } from "./support/clerk-users";
import { expect, requiresClerk, test } from "./support/fixtures";

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

/**
 * Book a slot so this player organises a match of their own. Returns the match id.
 *
 * The day differs per test and project, and the slot is picked at random.
 */
async function organiseAMatch(
  page: Page,
  slug: string,
  { dayOffset = 2, sport }: { dayOffset?: number; sport?: string } = {},
): Promise<string> {
  // The two projects run the same specs against one database at the same time, so they
  // book different days as well as different slots: two of them reaching for the same
  // slot is a 409, which is correct behaviour and a useless test failure.
  const shift = test.info().project.name === "mobile" ? 3 : 0;

  await page.goto(`/turfs/${slug}`);
  await page.getByLabel("Date").fill(dhakaDate(dayOffset + shift));

  if (sport) {
    // A turf hosts several grounds and the picker defaults to the first, which is not
    // necessarily the sport whose validator a test is about.
    const option = page.locator("#ground option").filter({ hasText: sport }).first();
    await page.getByLabel("Ground").selectOption(await option.getAttribute("value"));
  }

  const open = page.locator("[data-slot-start][data-slot-available='true']");
  await expect(open.first()).toBeVisible();
  const slot = open.nth(Math.floor(Math.random() * (await open.count())));
  await slot.click();
  await page.getByRole("button", { name: /^Book for/ }).click();
  await expect(page).toHaveURL(/\/bookings\/[0-9a-f-]+$/);

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
      dayOffset: 2,
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
      dayOffset: 3,
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
    const matchId = await organiseAMatch(page, "banani-sports-hub", { dayOffset: 4 });

    const response = await page.goto(`/scorecards/${matchId}`);
    expect(response?.status()).toBe(404);
  });
});
