import { expect, test } from "@playwright/test";

/**
 * The policy pages, signed out.
 *
 * A refund policy a player cannot read before deciding to pay is not a policy, and
 * SSLCommerz's merchant onboarding asks for URLs that resolve without an account — so
 * "it is public" is the thing worth testing, not the prose.
 */
const DOCUMENTS = [
  { slug: "terms", heading: "Terms of use" },
  { slug: "privacy", heading: "Privacy policy" },
  { slug: "refunds", heading: "Cancellation and refund policy" },
  { slug: "owners", heading: "Turf owner agreement" },
];

test.describe("policy pages", () => {
  for (const { slug, heading } of DOCUMENTS) {
    test(`${slug} is readable without signing in`, async ({ page }) => {
      await page.goto(`/legal/${slug}`);

      await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
      // Every page carries the Bangla summary and says which version governs.
      await expect(page.getByText(/সংক্ষেপে/).first()).toBeVisible();
    });
  }

  test("they are linked from every page", async ({ page }) => {
    await page.goto("/");

    await expect(
      page.getByRole("contentinfo").getByRole("link", { name: "Cancellation and refund policy" }),
    ).toBeVisible();
  });

  test("an unknown document is a 404, not a blank page", async ({ page }) => {
    const response = await page.goto("/legal/whatever");
    expect(response?.status()).toBe(404);
  });
});
