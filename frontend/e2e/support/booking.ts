import type { Page } from "@playwright/test";

/** Dhaka-local YYYY-MM-DD, which is what every date control in the app expects. */
export function dhakaDate(offsetDays = 0): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Dhaka" }).format(
    new Date(Date.now() + offsetDays * 86_400_000),
  );
}

/** Every approved turf in the demo data. */
export const DEMO_TURFS = [
  "bashundhara-play-zone",
  "gulshan-sports-arena",
  "mirpur-turf-club",
  "dhanmondi-arena",
  "banani-sports-hub",
  "uttara-green-ground",
];

export const OPEN_SLOT = "[data-slot-start][data-slot-available='true']";

/**
 * The days to try, in an order that depends on which worker is asking.
 *
 * Workers run in parallel against one database, so two of them starting at tomorrow
 * reach for the same slot and one gets a 409 — correct behaviour, useless failure.
 */
function daysToTry(days: number): number[] {
  const shift = Number(process.env.TEST_WORKER_INDEX ?? 0) * 3;
  return Array.from({ length: days }, (_, index) => ((index + shift) % days) + 1);
}

/**
 * Walk the turf page already loaded, yielding each day that has something free.
 *
 * Every run of this suite books real slots and nothing releases them, so a test that
 * insists on one ground on one day eventually fails for a reason that has nothing to do
 * with what it is testing. The grid is fetched after the date and ground change, so each
 * combination is given a moment to arrive: counting straight after a change counts an
 * empty grid, not a busy ground.
 */
async function* openSlotDays(
  page: Page,
  { sport, days = 14 }: { sport?: string; days?: number },
): AsyncGenerator<string> {
  const open = page.locator(OPEN_SLOT);

  for (const day of daysToTry(days)) {
    const date = dhakaDate(day);
    // `#date`, not the label: journey 7 runs this whole flow in Bangla, and a helper
    // keyed on English text would quietly fail there (`#ground` below, same reason).
    await page.locator("#date").fill(date);

    const grounds = await page.locator("#ground option").count();
    for (let index = 0; index < grounds; index += 1) {
      const option = page.locator("#ground option").nth(index);
      if (sport && !((await option.textContent()) ?? "").includes(sport)) continue;

      await page.locator("#ground").selectOption(await option.getAttribute("value"));

      const appeared = await open
        .first()
        .waitFor({ state: "visible", timeout: 2000 })
        .then(() => true)
        .catch(() => false);
      if (appeared) yield date;
    }
  }
}

/** Find a day and ground on the loaded turf page that still has a free slot. */
export async function findOpenSlot(
  page: Page,
  options: { sport?: string; days?: number } = {},
): Promise<string | null> {
  for await (const date of openSlotDays(page, options)) return date;
  return null;
}

/**
 * Find a genuinely free slot anywhere in the demo data and book it.
 *
 * Returns the booking's id along with the day and turf it settled on, because a caller
 * that wants to see the slot marked BOOKED has to look at the right date, on the right
 * turf.
 */
export async function bookAFreeSlot(
  page: Page,
  { turfs, sport, days = 14 }: { turfs: string[]; sport?: string; days?: number },
): Promise<{ id: string; date: string; turf: string }> {
  for (const turf of turfs) {
    await page.goto(`/turfs/${turf}`);

    for await (const date of openSlotDays(page, { sport, days })) {
      const open = page.locator(OPEN_SLOT);
      await open.nth(Math.floor(Math.random() * (await open.count()))).click();
      // The confirm button's label carries the price and is translated, so it is reached
      // by test id — journey 7 runs this whole flow in Bangla.
      await page.getByTestId("confirm-booking").click();

      const booked = await page
        .waitForURL(/\/bookings\/[0-9a-f-]+$/, { timeout: 10_000 })
        .then(() => true)
        .catch(() => false);
      if (booked) return { id: page.url().split("/").pop()!, date, turf };

      // Another worker took the slot between the grid arriving and the click, so the
      // API said 409. Reload and keep hunting from where the walk left off.
      await page.goto(`/turfs/${turf}`);
    }
  }

  throw new Error(
    `No free slot at ${turfs.join(", ")} within ${days} days — re-run \`manage.py seed_demo\`.`,
  );
}
