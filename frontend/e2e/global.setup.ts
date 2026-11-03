import { clerkSetup } from "@clerk/testing/playwright";
import { test as setup } from "@playwright/test";

/**
 * Obtain the Clerk Testing Token once per run.
 *
 * Without it every sign-in hits the instance's bot protection. Skipped — rather than
 * failed — when Clerk is not configured, so `npm run test:e2e` still runs the public
 * smoke suite in a bare checkout.
 */
setup("clerk", async () => {
  if (!process.env.CLERK_SECRET_KEY) {
    setup.skip(true, "CLERK_SECRET_KEY is not set; authenticated specs will be skipped.");
  }
  await clerkSetup();
});
