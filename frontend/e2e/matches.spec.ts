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

/** Book a slot so the player organises a match. Returns the match id. */
async function organiseAMatch(page: Page, slug: string): Promise<string> {
  await page.goto(`/turfs/${slug}`);
  await page.getByLabel("Date").fill(dhakaDate(2));

  const slot = page.locator("[data-slot-start][data-slot-available='true']").first();
  await slot.click();
  await page.getByRole("button", { name: /^Book for/ }).click();
  await expect(page).toHaveURL(/\/bookings\/[0-9a-f-]+$/);

  // The booking page links to nothing match-shaped yet, so the id comes from the API.
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

test.describe("match board", () => {
  requiresClerk();

  test.beforeEach(async ({ signedInPage: page }) => {
    await finishOnboarding(page);
  });

  test("shows open matches with what they need", async ({ signedInPage: page }) => {
    await page.goto("/play");
    await expect(page.getByRole("heading", { level: 1, name: "Find a match" })).toBeVisible();

    // The seeded demo data has open board matches.
    const firstCard = page.getByTestId("match-board").locator('a[href^="/matches/"]').first();
    await expect(firstCard).toBeVisible();
    await expect(firstCard).toContainText(/Need \d+/);
  });

  test("filters by sport", async ({ signedInPage: page }) => {
    await page.goto("/play");
    const board = page.getByTestId("match-board");
    await expect(board.locator('a[href^="/matches/"]').first()).toBeVisible();

    // By id: the "I'm free" panel on this page has a Sport select of its own.
    await page.locator("#board-sport").selectOption("badminton");
    // Debounced; the count line is what settles last.
    await expect(page.getByText(/open match/)).toBeVisible();
    const cards = board.locator('a[href^="/matches/"]');
    const count = await cards.count();
    for (let index = 0; index < count; index += 1) {
      await expect(cards.nth(index)).toContainText("🏸");
    }
  });

  test("a match I organise is not on my own board", async ({ signedInPage: page }) => {
    const matchId = await organiseAMatch(page, "dhanmondi-arena");

    await page.goto("/play");
    // Scoped to the board: the "Your matches" shortcut above it links to the same place,
    // which is the point — you see your match, you just are not asked to join it.
    await expect(
      page.getByTestId("match-board").locator(`a[href="/matches/${matchId}"]`),
    ).toHaveCount(0);
    await expect(page.getByText("Your matches")).toBeVisible();
  });
});

test.describe("match page", () => {
  requiresClerk();

  test("the organiser sees their roster and no join form", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    const matchId = await organiseAMatch(page, "mirpur-turf-club");

    await page.goto(`/matches/${matchId}`);
    await expect(page.getByText(/Roster \(1\//)).toBeVisible();
    // The roster row links to the player's profile; "E2E Player" also appears in
    // "Organised by", hence the role.
    await expect(page.getByRole("link", { name: "E2E Player" })).toBeVisible();
    // The organiser is on the roster, so there is nothing to ask for.
    await expect(page.getByRole("button", { name: "Ask to join" })).toHaveCount(0);
    await expect(page.getByText("On the match board")).toBeVisible();
  });

  test("a player can ask to join somebody else's match", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    await page.goto("/play");

    const card = page.locator('a[href^="/matches/"]').first();
    await expect(card).toBeVisible();
    await card.click();

    await expect(page.getByRole("button", { name: "Ask to join" })).toBeVisible();
    await page.getByLabel("Message (optional)").fill("Right back, can make it");
    await page.getByRole("button", { name: "Ask to join" }).click();

    // The form is replaced by the reason they cannot ask again.
    await expect(page.getByText(/already asked/)).toBeVisible();
  });

  test("a private match is not reachable by an outsider", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    const response = await page.goto("/matches/00000000-0000-0000-0000-000000000000");
    expect(response?.status()).toBe(404);
  });
});

test.describe("squads", () => {
  requiresClerk();

  test("create an open squad and see what that means", async ({ signedInPage: page }) => {
    await finishOnboarding(page);

    await page.goto("/squads");
    await expect(page.getByText("You are not in a squad yet.")).toBeVisible();
    await page.getByRole("link", { name: "Create a squad" }).first().click();

    const name = `E2E Squad ${Date.now()}`;
    await page.getByLabel("Squad name").fill(name);
    await page.getByLabel("Area").fill("Dhanmondi");

    // Closed by default — the hint has to say so, because it decides how every future
    // match of this squad behaves (DOMAIN §6).
    await expect(page.getByText(/Squad only\./)).toBeVisible();
    await page.getByRole("switch", { name: "Open squad" }).click();
    await expect(page.getByText(/reach the match board/)).toBeVisible();

    await page.getByRole("button", { name: "Create squad" }).click();

    await expect(page).toHaveURL(/\/squads\/e2e-squad/);
    await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
    // The creator is the leader and already a member.
    await expect(page.getByText("1 member")).toBeVisible();
    await expect(page.getByText("Leader", { exact: true })).toBeVisible();
    await expect(page.getByText(/Hand leadership over/)).toBeVisible();
  });

  test("the leader can flip the squad open and closed", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    await page.goto("/squads/new");
    await page.getByLabel("Squad name").fill(`E2E Toggle ${Date.now()}`);
    await page.getByRole("button", { name: "Create squad" }).click();
    await expect(page).toHaveURL(/\/squads\/e2e-toggle/);

    await expect(page.getByText("Closed").first()).toBeVisible();
    await page.getByRole("switch", { name: "Open squad" }).click();
    await expect(page.getByText("Open").first()).toBeVisible();
  });
});
