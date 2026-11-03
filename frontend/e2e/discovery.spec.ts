import type { Page } from "@playwright/test";

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

test.describe("player discovery", () => {
  requiresClerk();

  test("the search page lists players and filters them", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    await page.goto("/players");

    const results = page.getByTestId("player-search-results");
    await expect(results.locator("li").first()).toBeVisible();

    // A nonsense area empties the list rather than silently ignoring the filter.
    await page.getByLabel("Area").fill("Nowhere-at-all");
    await expect(page.getByText(/Nobody matches that yet/)).toBeVisible();
  });

  test("a player posts when they are free and can take it back", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    await page.goto("/play");

    const panel = page.getByTestId("availability");
    await expect(panel).toBeVisible();
    await panel.getByLabel("Area").fill("Mirpur");
    await panel.getByRole("button", { name: "Save" }).click();

    await expect(panel.getByText("Mirpur")).toBeVisible();
    await panel.getByRole("button", { name: "Remove" }).click();
    await expect(panel.getByRole("button", { name: "Remove" })).toHaveCount(0);
  });

  test("a brand-new player has a profile with no record yet", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    await page.goto("/profile");

    // Fair play starts clean; the track record and chart only appear once they play.
    await expect(page.getByTestId("fair-play")).toContainText("100");
    await expect(page.getByTestId("track-record")).toHaveCount(0);
    await expect(page.getByTestId("rating-history")).toHaveCount(0);
  });

  test("the conduct queue is not reachable by an ordinary player", async ({
    signedInPage: page,
  }) => {
    await finishOnboarding(page);
    const response = await page.goto("/admin/conduct");
    // The admin route group redirects or refuses; either way the queue is not shown.
    expect(response?.status()).toBeGreaterThanOrEqual(200);
    await expect(page.getByTestId("conduct-queue")).toHaveCount(0);
  });
});
