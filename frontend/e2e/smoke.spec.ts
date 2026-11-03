import { expect, test } from "@playwright/test";

test.describe("public shell", () => {
  test("home page loads with the header and sign-in affordance", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("link", { name: "TurfApp" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });

  test("language switches to Bangla and the choice sticks", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Language" }).click();
    await page.getByRole("menuitem", { name: "বাংলা" }).click();

    await expect(page.getByRole("link", { name: "টার্ফঅ্যাপ" })).toBeVisible();

    // Cookie-based, so it must survive a reload without any URL change (D13).
    await page.reload();
    await expect(page.getByRole("link", { name: "টার্ফঅ্যাপ" })).toBeVisible();
    expect(new URL(page.url()).pathname).toBe("/");
  });

  test("signed-out visitors are redirected away from the player area", async ({ page }) => {
    await page.goto("/play");

    // auth.protect() sends unauthenticated users to Clerk's sign-in.
    await expect(page).toHaveURL(/sign-in/);
  });
});
