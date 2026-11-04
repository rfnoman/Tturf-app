import { clerk } from "@clerk/testing/playwright";
import type { Browser, Page } from "@playwright/test";

import { createTestUser, deleteTestUser, type TestUser } from "./clerk-users";

/**
 * The seeded account that holds every role (Phase 11 step 9).
 *
 * `manage.py seed_demo` creates `rafi+clerk_test@turfapp.dev` as a platform admin, the
 * owner of three turfs **and** a rider, and creates it in Clerk as well as in Django.
 * That is what makes the launch journeys testable at all: several of them cross a role
 * boundary — an owner lists a turf and an admin approves it; a player orders and staff
 * fulfils it — and a suite that can only ever be one anonymous new player cannot follow
 * them to the end.
 *
 * One account rather than four because roles here are permissions on an account, not
 * separate kinds of user (DOMAIN §1). Signing in as it is the same ticket flow every
 * other test uses; nothing is faked.
 */
export const SEEDED_STAFF = "rafi+clerk_test@turfapp.dev";

/** A second browser context signed in as the seeded staff account. */
export async function openAsStaff(browser: Browser): Promise<Page> {
  // Its own context: the journeys need two people on screen at once, and sharing one
  // would mean signing out and back in between every step.
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.goto("/");
  await clerk.loaded({ page });
  await clerk.signIn({ page, emailAddress: SEEDED_STAFF });

  return page;
}

/**
 * A second brand-new player, in their own browser context.
 *
 * Several journeys need two people on screen at once — one organises a match, the other
 * asks to join it; one enters a scorecard, the other confirms it. A scorecard cannot
 * lock without the opposing captain, and a rating cannot move without a locked card, so
 * a suite that can only ever be one player stops three steps short of the thing it is
 * meant to prove.
 */
export async function openAsNewPlayer(
  browser: Browser,
): Promise<{ page: Page; user: TestUser; close: () => Promise<void> }> {
  const user = await createTestUser();
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.goto("/");
  await clerk.loaded({ page });
  await clerk.signIn({ page, emailAddress: user.identifier });

  return {
    page,
    user,
    close: async () => {
      await context.close();
      await deleteTestUser(user.id);
    },
  };
}
