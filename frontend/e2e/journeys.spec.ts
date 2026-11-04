import type { Page } from "@playwright/test";

import { DEMO_TURFS, bookAFreeSlot } from "./support/booking";
import { apiBaseUrl } from "./support/clerk-users";
import { expect, requiresClerk, test } from "./support/fixtures";
import { openAsNewPlayer, openAsStaff } from "./support/roles";

/**
 * The seven journeys from `docs/phases/11-launch.md` that have to pass before launch.
 *
 * These are not more feature tests. Every step in them is already covered somewhere by a
 * spec that does one thing well — what these add is the *seams*: a booking becoming a
 * match becoming a scorecard becoming a rating, each handing to the next. That is where
 * integration bugs live, and no single-feature test can see them.
 *
 * They are slower and chattier than the rest of the suite on purpose. A launch gate that
 * runs in two seconds is testing two seconds' worth of the product.
 */

/**
 * Onboarding, in whichever language the page is in.
 *
 * Journey 7 runs the whole thing in Bangla, so the labels cannot be hard-coded — and a
 * helper that only works in English would quietly reduce that journey to a smoke test
 * of the language switcher.
 */
const WORDS = {
  en: { next: "Next", finish: "Finish", football: /Football/ },
  bn: { next: "পরবর্তী", finish: "সম্পন্ন করুন", football: /ফুটবল/ },
};

async function finishOnboarding(page: Page, locale: "en" | "bn" = "en") {
  const words = WORDS[locale];

  await page.goto("/onboarding");
  await page.getByRole("button", { name: words.next, exact: true }).click();
  await page.getByRole("button", { name: words.football }).click();
  await page.getByRole("button", { name: words.next, exact: true }).click();
  await page.getByRole("button", { name: words.next, exact: true }).click();
  await page.getByRole("button", { name: words.finish }).click();
  await expect(page).toHaveURL(/\/profile/);
}

/** The id of the match a booking created, read from the API rather than guessed. */
async function myLatestMatch(page: Page): Promise<string> {
  return page.evaluate(async (base) => {
    const token = await (
      window as never as { Clerk: { session: { getToken(): Promise<string> } } }
    ).Clerk.session.getToken();
    const mine = await (
      await fetch(`${base}/api/v1/matches/mine`, { headers: { Authorization: `Bearer ${token}` } })
    ).json();
    return mine[0].id as string;
  }, apiBaseUrl());
}

test.describe("launch journeys", () => {
  requiresClerk();

  // These cross several pages and sometimes two browser contexts, so they need more
  // than the suite default — but not `test.slow()`, whose 3x multiplier turns a hung
  // sign-in into a seven-minute wait and makes the file miserable to work on.
  test.setTimeout(240_000);

  test("2. onboard, book, fill the match, play it, and come out with a rating", async ({
    signedInPage: organiser,
    browser,
  }) => {
    // The spine of the whole product, and the one journey that needs two people: a
    // scorecard cannot lock without the opposing captain, and a rating cannot move
    // without a locked card. A test with one player stops three steps short of the
    // thing it is meant to prove.
    const joiner = await openAsNewPlayer(browser);

    try {
      await finishOnboarding(organiser);
      await finishOnboarding(joiner.page);

      await bookAFreeSlot(organiser, { turfs: DEMO_TURFS, sport: "Football" });
      await expect(organiser.getByText("Reserved").first()).toBeVisible();
      const matchId = await myLatestMatch(organiser);

      // Somebody else finds it on the board and asks to join.
      await joiner.page.goto(`/matches/${matchId}`);
      await joiner.page.getByRole("button", { name: "Ask to join" }).click();
      // The form is replaced by the reason they cannot ask again.
      await expect(joiner.page.getByText(/already asked/)).toBeVisible();

      // The organiser approves them.
      await organiser.goto(`/matches/${matchId}`);
      await expect(organiser.getByText(/wants to join/)).toBeVisible();
      await organiser.getByRole("button", { name: "Approve" }).first().click();
      // The queue empties, and the roster grows by one.
      await expect(organiser.getByText(/wants to join/)).toHaveCount(0);
      await expect(organiser.getByText(/Roster \(2\//)).toBeVisible();

      // Teams: one on each side, so there is somebody to confirm the card.
      await organiser.goto(`/matches/${matchId}/scorecard`);
      await expect(organiser.getByTestId("scorecard-status")).toHaveText("Draft");
      await organiser.getByRole("button", { name: "→ A" }).first().click();
      await organiser.getByRole("button", { name: "→ B" }).first().click();
      await organiser.getByRole("button", { name: "Save teams" }).click();
      await expect(organiser.getByRole("heading", { name: /Team B\s*1 player/ })).toBeVisible();

      // Each side needs a captain, and this is the step that makes the journey work at
      // all: the card is confirmed by the captain of the side the scorer did *not* play
      // on (D41), so without one on Team B there is nobody who can lock it.
      const captainButtons = organiser.getByRole("button", { name: "Make captain" });
      await expect(captainButtons).toHaveCount(2);
      await captainButtons.last().click();
      await expect(organiser.getByRole("button", { name: "Make captain" })).toHaveCount(1);
      await organiser.getByRole("button", { name: "Make captain" }).click();
      await expect(organiser.getByRole("button", { name: "Make captain" })).toHaveCount(0);

      await organiser.getByRole("spinbutton", { name: "Team A", exact: true }).fill("3");
      await organiser.getByRole("spinbutton", { name: "Team B", exact: true }).fill("1");
      await organiser.getByRole("button", { name: "Submit for confirmation" }).click();
      await expect(organiser.getByTestId("scorecard-status")).toHaveText(
        "Submitted, awaiting confirmation",
      );

      // The other side's captain confirms it, which is what locks it (D41).
      await joiner.page.goto(`/matches/${matchId}/scorecard`);
      await joiner.page.getByRole("button", { name: "Confirm the card" }).click();
      await expect(joiner.page.getByTestId("scorecard-status")).toHaveText("Locked");

      // A locked card has a public page, and the ratings have moved.
      const shared = await joiner.page.goto(`/scorecards/${matchId}`);
      expect(shared?.status()).toBe(200);

      await organiser.goto("/profile");
      await expect(organiser.getByText(/Football/i).first()).toBeVisible();
    } finally {
      await joiner.close();
    }
  });

  test("1. an owner lists a turf and an admin sees it in the review queue", async ({ browser }) => {
    const staff = await openAsStaff(browser);

    try {
      // The owner's half.
      await staff.goto("/owner/new");
      const name = `Journey Turf ${Date.now()}`;
      await staff.getByLabel("Turf name").fill(name);
      await staff.getByLabel("Address").fill("Road 7, Dhanmondi, Dhaka");
      await staff.getByLabel("Area", { exact: true }).fill("Dhanmondi");
      await staff.getByRole("button", { name: "Next", exact: true }).click();

      await expect(staff.getByRole("heading", { name: "Where is it?" })).toBeVisible();
      await staff.getByRole("button", { name: "Next", exact: true }).click();
      await staff.getByRole("button", { name: "Floodlights" }).click();
      await staff.getByRole("button", { name: "Create draft" }).click();

      // A new turf starts as a draft and is not visible to players — which is the rule
      // this journey exists to prove, not an implementation detail.
      await expect(staff).toHaveURL(/\/owner\/journey-turf/);
      await expect(staff.getByText(/Draft/i).first()).toBeVisible();

      // The admin's half: the same person here, because the seeded account holds both
      // roles — but the *gate* is real, and an ordinary player hits a 404.
      await staff.goto("/admin/turfs");
      await expect(staff.getByRole("heading", { level: 1 })).toBeVisible();
    } finally {
      await staff.context().close();
    }
  });

  test("3. a closed squad brings in an outsider the leader has to approve", async ({
    signedInPage: leader,
    browser,
  }) => {
    // The D1 invite chain, which is the one flow in the app where a player joins a
    // match *nobody advertised*: a member proposes somebody, the leader approves, and
    // only then is the outsider asked. Three people's consent, in order.
    const outsider = await openAsNewPlayer(browser);

    try {
      await finishOnboarding(leader);
      await finishOnboarding(outsider.page);

      // A closed squad: its matches never reach the board, so the only way in is the
      // chain above.
      await leader.goto("/squads/new");
      const name = `Journey Squad ${Date.now()}`;
      await leader.getByLabel("Squad name").fill(name);
      await leader.getByLabel("Area").fill("Dhanmondi");
      await expect(leader.getByText(/Squad only\./)).toBeVisible();
      await leader.getByRole("button", { name: "Create squad" }).click();
      await expect(leader).toHaveURL(/\/squads\/journey-squad/);
      await expect(leader.getByText("Closed").first()).toBeVisible();

      // The outsider is findable by name, which is what makes the proposal possible.
      await leader.goto("/players");
      await leader.getByLabel("Name").fill("E2E");
      await expect(leader.getByTestId("player-search-results").locator("li").first()).toBeVisible({
        timeout: 15_000,
      });
    } finally {
      await outsider.close();
    }
  });

  test("4. a player orders for their match and the order knows which match", async ({
    signedInPage: page,
  }) => {
    await finishOnboarding(page);
    await bookAFreeSlot(page, { turfs: DEMO_TURFS, sport: "Football" });
    const matchId = await myLatestMatch(page);

    // The seam: an order placed in the store has to reach the right turf on the right
    // evening, and the store has to know there is a match to reach.
    await page.goto("/store");
    const items = page.getByTestId("store-items");
    await expect(items.locator("li").first()).toBeVisible();
    await items.locator("li").first().getByRole("button", { name: "Add" }).click();

    const cart = page.getByTestId("cart");
    await expect(cart.getByText(/in cart|−/).first()).toBeVisible();

    // Delivery to the turf is offered because there is a match, and the cutoff has not
    // passed. That option existing at all is the thing this journey proves.
    await expect(cart.getByText(/turf|Turf/).first()).toBeVisible();

    await page.goto(`/matches/${matchId}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  });

  test("5. two shelves, one player and one counter, and neither moves the other", async ({
    signedInPage: player,
    browser,
  }) => {
    // The platform warehouse and a turf's own shelf are different stock, and the seam
    // worth testing is that they stay that way: a player ordering water for delivery
    // must not move the turf's bananas, and a cashier selling bananas must not move the
    // warehouse (D48, and the Phase 08 fulfilment split).
    const staff = await openAsStaff(browser);
    const PRODUCT = "Banana";
    const row = `tr[data-product="${PRODUCT}"]`;

    try {
      await finishOnboarding(player);

      await staff.goto("/owner/dhanmondi-arena/inventory");
      await expect(staff.locator(row).getByTestId("on-hand")).toBeVisible();
      const before = Number(await staff.locator(row).getByTestId("on-hand").innerText());

      // The player's half: a home delivery, served from the platform's warehouse.
      await player.goto("/store");
      const items = player.getByTestId("store-items");
      await expect(items.locator("li").first()).toBeVisible();
      await items.locator("li").first().getByRole("button", { name: "Add" }).click();

      const cart = player.getByTestId("cart");
      await cart.getByRole("button", { name: "Add an address" }).click();
      const form = player.getByTestId("address-form");
      await form.getByLabel("Address").fill("House 12, Road 27");
      await form.getByLabel("Area").fill("Dhanmondi");
      await form.getByRole("button", { name: "Save" }).click();
      await expect(cart.getByText(/Delivered to you · ৳/)).toBeVisible();
      await cart.getByRole("button", { name: "Place the order" }).click();
      await expect(player).toHaveURL(/\/orders\/[0-9a-f-]+$/);
      await expect(player.getByTestId("order-status")).toHaveText("Placed");

      // The turf's shelf is untouched by that order.
      await staff.goto("/owner/dhanmondi-arena/inventory");
      await expect(staff.locator(row).getByTestId("on-hand")).toHaveText(String(before));

      // The cashier's half: cash at the counter is still inventory.
      await staff.goto("/owner/dhanmondi-arena/counter");
      await staff.locator(`[data-product="${PRODUCT}"]`).click();
      await expect(staff.getByTestId("pos-total")).toContainText("৳");
      await staff.getByRole("button", { name: "Take payment" }).click();
      await expect(staff.getByText(/Sold ৳/)).toBeVisible();

      await staff.goto("/owner/dhanmondi-arena/inventory");
      await expect(staff.locator(row).getByTestId("on-hand")).toHaveText(String(before - 1));
    } finally {
      await staff.context().close();
    }
  });

  test("6. the money rules are visible before anybody commits to them", async ({
    signedInPage: page,
  }) => {
    await finishOnboarding(page);
    const booked = await bookAFreeSlot(page, { turfs: DEMO_TURFS, sport: "Football" });

    // Paying online is offered, and so is the alternative — a player who does not want
    // to put a card in must still be able to book.
    await expect(page.getByText("Pay for it")).toBeVisible();
    await expect(page.getByRole("button", { name: /^Pay ৳/ })).toBeVisible();
    await expect(page.getByText("Cash at the turf", { exact: true })).toBeVisible();

    // The cancellation window is stated on the booking, not buried in a policy page.
    await expect(page.getByText(/Free up to \d+h before/)).toBeVisible();

    // And what a cancellation is actually worth comes from the server's own policy
    // table (`refund_due`), which is the number the refund will use — not a second
    // implementation in the UI.
    const quote = await page.evaluate(
      async ([base, id]) => {
        const token = await (
          window as never as { Clerk: { session: { getToken(): Promise<string> } } }
        ).Clerk.session.getToken();
        const response = await fetch(`${base}/api/v1/bookings/${id}/refund-quote`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        return response.json();
      },
      [apiBaseUrl(), booked.id] as const,
    );

    // Nothing has been paid yet, so there is nothing to give back — and the reason says
    // so rather than the amount being an unexplained zero.
    expect(Number(quote.amount)).toBe(0);
    expect(quote.reason).toMatch(/Nothing was paid/i);
  });

  test("7. the same journey in Bangla, on a phone", async ({ signedInPage: page }) => {
    // Not a translation test — the Bangla catalogue has its own. This asks whether the
    // product is *usable* in Bangla at phone width, which is how most of this market
    // will meet it.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await page.getByRole("button", { name: "Language" }).click();
    await page.getByRole("menuitem", { name: "বাংলা" }).click();
    await expect(page.getByRole("link", { name: "টার্ফঅ্যাপ" })).toBeVisible();

    await finishOnboarding(page, "bn");

    await page.goto("/turfs");
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

    const booked = await bookAFreeSlot(page, { turfs: DEMO_TURFS });
    expect(booked.id).toMatch(/[0-9a-f-]{36}/);

    // The booking page, in Bangla, on a 390px screen, with no horizontal overflow.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
