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

test.describe("store", () => {
  requiresClerk();

  test("a player shops the platform store and places a delivery order", async ({
    signedInPage: page,
  }) => {
    await finishOnboarding(page);
    await page.goto("/store");

    const items = page.getByTestId("store-items");
    await expect(items.locator("li").first()).toBeVisible();

    // Add the first thing on the shelf.
    await items.locator("li").first().getByRole("button", { name: "Add" }).click();
    const cart = page.getByTestId("cart");
    await expect(cart.getByText(/in cart|−/).first()).toBeVisible();

    // Without an address, home delivery explains itself rather than vanishing.
    await expect(cart.getByText(/Choose an address/)).toBeVisible();

    await cart.getByRole("button", { name: "Add an address" }).click();
    const form = page.getByTestId("address-form");
    await form.getByLabel("Address").fill("House 12, Road 27");
    await form.getByLabel("Area").fill("Dhanmondi");
    await form.getByRole("button", { name: "Save" }).click();

    // The zone fee appears once the address is known.
    await expect(cart.getByText(/Delivered to you · ৳/)).toBeVisible();

    await cart.getByRole("button", { name: "Place the order" }).click();
    await expect(page).toHaveURL(/\/orders\/[0-9a-f-]+$/);
    await expect(page.getByTestId("order-status")).toHaveText("Placed");
  });

  test("an order can be cancelled while it is still just placed", async ({
    signedInPage: page,
  }) => {
    await finishOnboarding(page);
    await page.goto("/store");

    const items = page.getByTestId("store-items");
    await expect(items.locator("li").first()).toBeVisible();
    await items.locator("li").first().getByRole("button", { name: "Add" }).click();

    const cart = page.getByTestId("cart");
    await cart.getByRole("button", { name: "Add an address" }).click();
    const form = page.getByTestId("address-form");
    await form.getByLabel("Address").fill("House 9, Road 11");
    await form.getByLabel("Area").fill("Dhanmondi");
    await form.getByRole("button", { name: "Save" }).click();
    await expect(cart.getByText(/Delivered to you · ৳/)).toBeVisible();
    await cart.getByRole("button", { name: "Place the order" }).click();

    await expect(page).toHaveURL(/\/orders\/[0-9a-f-]+$/);
    await page.getByLabel("Why?").fill("Ordered by accident");
    await page.getByRole("button", { name: "Cancel the order" }).click();

    await expect(page.getByTestId("order-status")).toHaveText("Cancelled");
  });

  test("a player with no deliveries sees an empty rider list", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    await page.goto("/rider");
    await expect(page.getByText(/Nothing assigned to you/)).toBeVisible();
  });

  test("the platform order queue is admin only", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    await page.goto("/admin/orders");
    await expect(page.getByTestId("order-queue")).toHaveCount(0);
  });
});
