import { apiBaseUrl } from "./support/clerk-users";
import { expect, requiresClerk, test } from "./support/fixtures";

/** Settings and the public player card, once a player is onboarded. */
test.describe("profile", () => {
  requiresClerk();

  test.beforeEach(async ({ signedInPage: page }) => {
    await page.goto("/onboarding");
    await page.getByLabel("Area").fill("Banani");
    await page.getByRole("button", { name: "Next" }).click();
    await page.getByRole("button", { name: /Badminton/ }).click();
    await page.getByRole("button", { name: "Next" }).click();
    await page.getByRole("button", { name: "Next" }).click();
    await page.getByRole("button", { name: "Finish" }).click();
    await expect(page).toHaveURL(/\/profile/);
  });

  test("a player can add a sport from settings and see a new card", async ({
    signedInPage: page,
  }) => {
    await page.getByRole("link", { name: "Edit profile" }).click();
    await expect(page).toHaveURL(/\/settings/);

    await page
      .locator("div", { hasText: /^⚽\s*Football/ })
      .getByRole("button", { name: "Add" })
      .first()
      .click();
    await expect(page.getByRole("status")).toContainText("Saved");

    await page.goto("/profile");
    await expect(page.getByRole("tab", { name: /Football/ })).toBeVisible();
    await expect(page.getByRole("tab", { name: /Badminton/ })).toBeVisible();
  });

  test("turning off discoverability still leaves the direct link working", async ({
    signedInPage: page,
  }) => {
    await page.goto("/settings");
    await page.getByRole("switch", { name: "Appear in player search" }).click();
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByRole("status")).toContainText("Saved");

    // DOMAIN §3: `discoverable` gates search, never a direct profile link.
    // `process` does not exist in the page, so the origin is passed in.
    const playerId = await page.evaluate(async (base) => {
      const token = await (
        window as never as { Clerk: { session: { getToken(): Promise<string> } } }
      ).Clerk.session.getToken();
      const response = await fetch(`${base}/api/v1/me/profile`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return (await response.json()).id as string;
    }, apiBaseUrl());

    await page.goto(`/players/${playerId}`);
    await expect(page.getByRole("heading", { level: 1, name: "E2E Player" })).toBeVisible();
    // The public card carries no owner-only affordance.
    await expect(page.getByRole("link", { name: "Edit profile" })).toHaveCount(0);
  });
});
