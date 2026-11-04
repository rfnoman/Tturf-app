import type { Page } from "@playwright/test";

import { DEMO_TURFS, bookAFreeSlot } from "./support/booking";
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

test.describe("payments", () => {
  requiresClerk();

  test("a booking offers to be paid for online", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    await bookAFreeSlot(page, { turfs: DEMO_TURFS });

    await expect(page.getByText("Pay for it")).toBeVisible();
    await expect(page.getByRole("button", { name: /^Pay ৳/ })).toBeVisible();
  });

  test("the payment history starts empty and needs signing in", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    await page.goto("/payments");

    await expect(page.getByRole("heading", { level: 1, name: "Payments" })).toBeVisible();
    await expect(page.getByText("You have not paid for anything yet.")).toBeVisible();
  });

  test("a player cannot reach the platform finance screen", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    await page.goto("/admin/finance");

    await expect(page.getByTestId("payout-list")).toHaveCount(0);
    await expect(page.getByTestId("platform-total")).toHaveCount(0);
  });

  test("a turf's finance page is for its owner only", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    const response = await page.goto("/owner/mirpur-turf-club/finance");

    expect(response?.status()).toBe(404);
  });
});
