import { test as base, type Page } from "@playwright/test";
import { clerk } from "@clerk/testing/playwright";

import { clerkSecretKey, createTestUser, deleteTestUser, type TestUser } from "./clerk-users";

/**
 * A page already signed in as a brand-new player.
 *
 * Uses `clerk.signIn`'s **email** overload, which mints a one-time sign-in token through
 * Clerk's Backend API and redeems it with the `ticket` strategy. That matters: the
 * password strategy stops at Clerk's new-device email verification, and the helper's
 * password branch calls `setActive` with a null session id rather than raising — so a
 * failed sign-in looks like a pass and every assertion afterwards fails on a redirect to
 * `/sign-in`. A ticket skips every factor.
 *
 * The helper also installs the Clerk testing token itself, which is what gets past the
 * instance's bot protection — without it Clerk serves a Cloudflare Turnstile challenge
 * no automated run can clear.
 */
export const test = base.extend<{ newPlayer: TestUser; signedInPage: Page }>({
  newPlayer: async ({}, use) => {
    const user = await createTestUser();
    await use(user);
    await deleteTestUser(user.id);
  },

  signedInPage: async ({ page, newPlayer }, use) => {
    // Clerk's client only loads on a real page, and must be loaded before signing in.
    await page.goto("/");
    await clerk.loaded({ page });
    await clerk.signIn({ page, emailAddress: newPlayer.identifier });
    await use(page);
  },
});

/** Skip the authenticated suite where Clerk credentials are not configured. */
export const requiresClerk = () =>
  test.skip(
    !clerkSecretKey() || !process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY,
    "Needs CLERK_SECRET_KEY and NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY.",
  );

export { expect } from "@playwright/test";
