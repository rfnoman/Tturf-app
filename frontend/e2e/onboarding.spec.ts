import { apiBaseUrl } from "./support/clerk-users";
import { expect, requiresClerk, test } from "./support/fixtures";

/**
 * Phase 01 happy path: a brand-new player is forced through onboarding and lands on a
 * FIFA-style profile card (acceptance checklist, docs/phases/01).
 */
test.describe("onboarding", () => {
  requiresClerk();

  test("a new player is forced through onboarding and lands on their card", async ({
    signedInPage: page,
  }) => {
    // Any player-area URL must bounce to the wizard until onboarding is finished.
    await page.goto("/profile");
    await expect(page).toHaveURL(/\/onboarding/);
    await expect(page.getByRole("heading", { name: "Tell us about you" })).toBeVisible();

    await page.getByLabel("Area").fill("Dhanmondi");
    await page.getByRole("button", { name: "Next", exact: true }).click();

    // Step 2 cannot be left without a sport.
    await expect(page.getByRole("heading", { name: "What do you play?" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Next", exact: true })).toBeDisabled();

    await page.getByRole("button", { name: /Football/ }).click();
    await page.getByRole("button", { name: "Next", exact: true }).click();

    // Step 3: positions and the self-assessment sliders for the chosen sport.
    await expect(page.getByRole("heading", { name: "Rate yourself" })).toBeVisible();
    await page.getByRole("button", { name: "MID", exact: true }).click();
    await page.getByRole("button", { name: "Next", exact: true }).click();

    await expect(page.getByRole("heading", { name: "Your physical attributes" })).toBeVisible();
    await page.getByRole("button", { name: "Finish" }).click();

    await expect(page).toHaveURL(/\/profile/);
    await expect(page.getByRole("heading", { level: 1, name: "E2E Player" })).toBeVisible();
    await expect(page.getByText("OVERALL")).toBeVisible();
    await expect(page.getByText("MID", { exact: true })).toBeVisible();
    // Self-assessed, so the card must say so (DOMAIN §3).
    await expect(page.getByText("Unverified")).toBeVisible();

    // And the gate must now let them through rather than bouncing back.
    await page.goto("/profile");
    await expect(page).toHaveURL(/\/profile/);
  });

  test("self-assessment sliders cannot exceed the configured cap", async ({
    signedInPage: page,
  }) => {
    await page.goto("/onboarding");
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await page.getByRole("button", { name: /Football/ }).click();
    await page.getByRole("button", { name: "Next", exact: true }).click();

    const slider = page.getByRole("slider").first();
    await slider.focus();
    await slider.press("End");

    // The ceiling comes from the backend's SELF_ASSESSED_RATING_CAP via /api/v1/config,
    // so this asserts the two sides agree rather than hard-coding 75 twice.
    // `process` does not exist in the page, so the origin is passed in.
    const cap = await page.evaluate(async (base) => {
      const response = await fetch(`${base}/api/v1/config`);
      return (await response.json()).self_assessed_rating_cap as number;
    }, apiBaseUrl());

    await expect(slider).toHaveAttribute("aria-valuenow", String(cap));
  });
});
