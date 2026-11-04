import { expect, requiresClerk, test } from "./support/fixtures";

/**
 * The admin surface, from an ordinary player's side.
 *
 * The suite cannot grant itself platform-admin — that is the point of the role — so
 * what it can assert, and what matters most, is that the gate holds. The pages
 * themselves are covered by the backend's permission matrix and by the dashboard's own
 * payload tests.
 */
test.describe("admin surface", () => {
  requiresClerk();

  for (const path of ["/admin/dashboard", "/admin/support"]) {
    test(`${path} is not reachable by an ordinary player`, async ({ signedInPage: page }) => {
      await page.goto(path);

      // The layout answers `notFound()` for a non-admin, so the page itself never
      // renders — which is what has to hold.
      await expect(page.getByRole("heading", { name: /How it's going|Support/ })).toHaveCount(0);
      await expect(page.getByText(/404|not found/i).first()).toBeVisible();
    });
  }
});
