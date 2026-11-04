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

test.describe("fitness", () => {
  requiresClerk();

  test("a new player's home invites them to find a match", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    await page.goto("/home");

    await expect(page.getByTestId("home-dashboard")).toBeVisible();
    await expect(page.getByText("Nothing booked yet.")).toBeVisible();
    await expect(page.getByText(/Set a goal to track the week/)).toBeVisible();
  });

  test("a player logs a gym session and it lands in the week", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    await page.goto("/activity");

    await expect(page.getByText("Nothing logged yet.")).toBeVisible();

    await page.getByLabel("Minutes", { exact: true }).fill("45");
    await page.getByLabel("Note").fill("Gym, legs");
    await page.getByRole("button", { name: "Add", exact: true }).click();

    const history = page.getByTestId("activity-history");
    await expect(history).toContainText("Gym, legs");
    await expect(history).toContainText("45m");

    // The home ring reads the same week.
    await page.goto("/home");
    await expect(page.getByText("45 min")).toBeVisible();
  });

  test("a weekly goal shows progress once there is activity", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    await page.goto("/activity");

    await page.getByLabel("Minutes", { exact: true }).fill("60");
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.getByTestId("activity-history")).toContainText("60m");

    await page.getByLabel("Minutes a week").fill("120");
    await page
      .getByRole("button", { name: /^(Set|Update)$/ })
      .nth(1)
      .click();

    await page.goto("/home");
    await expect(page.getByText("of 120 · Minutes a week")).toBeVisible();
  });

  test("reminder settings can be switched off", async ({ signedInPage: page }) => {
    await finishOnboarding(page);
    await page.goto("/settings");

    const panel = page.getByTestId("reminder-settings");
    await expect(panel).toBeVisible();

    const hydration = panel.locator("#reminder-hydration");
    await expect(hydration).toBeChecked();

    // The switch moves optimistically, so the reload has to wait for the save itself
    // rather than for the checkbox.
    await Promise.all([
      page.waitForResponse(
        (response) =>
          response.url().includes("/me/reminders") && response.request().method() === "PATCH",
      ),
      hydration.uncheck(),
    ]);

    await page.reload();
    await expect(
      page.getByTestId("reminder-settings").locator("#reminder-hydration"),
    ).not.toBeChecked();
  });
});
