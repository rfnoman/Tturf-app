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

/** Register a turf, so this run owns a shelf nobody else is touching. */
async function registerTurf(page: Page, name: string): Promise<string> {
  await page.goto("/owner/new");
  await page.getByLabel("Turf name").fill(name);
  await page.getByLabel("Address").fill("Road 1, Dhanmondi, Dhaka");
  await page.getByLabel("Area", { exact: true }).fill("Dhanmondi");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  // Step 2 is the map picker; the default Dhaka pin is fine.
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Floodlights" }).click();
  await page.getByRole("button", { name: "Create draft" }).click();

  // Not just `/owner/<something>`: "/owner/new" matches that too.
  await expect(page).toHaveURL(/\/owner\/e2e-/);
  return page.url().split("/owner/")[1];
}

test.describe("inventory", () => {
  requiresClerk();

  test("an owner stocks a shelf and the ledger says where it came from", async ({
    signedInPage: page,
  }) => {
    await finishOnboarding(page);
    const slug = await registerTurf(page, `E2E Stock ${Date.now()}`);

    await page.goto(`/owner/${slug}/inventory`);
    await expect(page.getByRole("heading", { level: 1, name: "Inventory" })).toBeVisible();
    await expect(page.getByText("Nothing on the shelf yet.")).toBeVisible();

    await page.getByRole("button", { name: "Add a product" }).click();
    await page.getByLabel("Name", { exact: true }).fill("Mineral water 500ml");
    await page.getByLabel("Price (৳)").fill("25");
    await page.getByRole("button", { name: "Add to the shelf" }).click();

    const row = page.locator('tr[data-product="Mineral water 500ml"]');
    await expect(row).toBeVisible();
    await expect(row.getByTestId("on-hand")).toHaveText("0");

    await row.getByLabel("Receive Mineral water 500ml").fill("24");
    await row.getByRole("button", { name: "Receive" }).click();

    await expect(
      page.locator('tr[data-product="Mineral water 500ml"]').getByTestId("on-hand"),
    ).toHaveText("24");
    await expect(page.getByTestId("movement-log")).toContainText("Stock received");
  });

  test("an adjustment will not go through without a reason", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    const slug = await registerTurf(page, `E2E Adjust ${Date.now()}`);

    await page.goto(`/owner/${slug}/inventory`);
    await page.getByRole("button", { name: "Add a product" }).click();
    await page.getByLabel("Name", { exact: true }).fill("Banana");
    await page.getByLabel("Price (৳)").fill("15");
    await page.getByRole("button", { name: "Add to the shelf" }).click();

    const row = page.locator('tr[data-product="Banana"]');
    await row.getByRole("button", { name: "Adjust" }).click();
    await page.getByLabel("Change for Banana").fill("-1");
    await page.getByRole("button", { name: "Save", exact: true }).click();

    await expect(page.getByText(/needs a number and a reason/)).toBeVisible();
  });

  test("the counter rings up a sale and the stock drops", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    const slug = await registerTurf(page, `E2E Counter ${Date.now()}`);

    await page.goto(`/owner/${slug}/inventory`);
    await page.getByRole("button", { name: "Add a product" }).click();
    await page.getByLabel("Name", { exact: true }).fill("Mineral water 500ml");
    await page.getByLabel("Price (৳)").fill("25");
    await page.getByRole("button", { name: "Add to the shelf" }).click();

    const row = page.locator('tr[data-product="Mineral water 500ml"]');
    await row.getByLabel("Receive Mineral water 500ml").fill("10");
    await row.getByRole("button", { name: "Receive" }).click();
    await expect(
      page.locator('tr[data-product="Mineral water 500ml"]').getByTestId("on-hand"),
    ).toHaveText("10");

    await page.goto(`/owner/${slug}/counter`);
    const tile = page.locator('[data-product="Mineral water 500ml"]');
    await tile.click();
    await tile.click();
    await tile.click();
    await expect(page.getByTestId("pos-total")).toHaveText("৳75");

    await page.getByLabel("Cash received (৳)").fill("100");
    await expect(page.getByTestId("change-due")).toHaveText("৳25");
    await page.getByRole("button", { name: "Take payment" }).click();

    await expect(page.getByText(/Sold ৳75/)).toBeVisible();
    await expect(page.getByTestId("todays-sales")).toContainText("3× Mineral water 500ml");

    // The shelf is the point: three fewer than before.
    await page.goto(`/owner/${slug}/inventory`);
    await expect(
      page.locator('tr[data-product="Mineral water 500ml"]').getByTestId("on-hand"),
    ).toHaveText("7");
  });

  test("a player cannot reach a turf's counter", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    const response = await page.goto("/owner/dhanmondi-arena/counter");
    expect(response?.status()).toBe(404);
  });
});
