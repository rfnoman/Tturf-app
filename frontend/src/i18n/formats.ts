/**
 * How numbers, money and dates are shaped — in one place, for both languages.
 *
 * Phase 11 centralised this because it was not: 38 places interpolated a decimal
 * straight out of the API next to a ৳, which renders "৳1200.00" — trailing paisa that
 * are always zero, and Western digits regardless of language.
 */

/**
 * Which digits Bangla uses.
 *
 * `beng` is ০১২৩; `latn` is 0123. The default is **latn**, deliberately: every app
 * these players already use for money — bKash, Nagad, Pathao, Daraz — writes Bangla
 * words with Western digits, and a price is the one thing in the UI nobody should have
 * to read twice. Set this to "beng" to switch the whole app over; it is the only place
 * that decides (DECISIONS D62).
 */
export const NUMERALS: "latn" | "beng" = "latn";

/** The options every `Intl` call in the app shares. */
export const NUMBERING = { numberingSystem: NUMERALS } as const;

/** Bangladesh runs on Dhaka time whoever is looking (CLAUDE.md). */
export const DHAKA = "Asia/Dhaka";

/**
 * The regional variant each language formats with.
 *
 * `en` alone means `en-US` to `Intl`: 12-hour clocks and month-before-day. Bangladesh
 * writes 5 Nov and a 19:30 kick-off, so English here is **en-GB** — which is also what
 * every call site spelled out before Phase 11 centralised them.
 */
export function formattingLocale(locale: string): string {
  return locale === "bn" ? "bn-BD" : "en-GB";
}

/**
 * An amount in taka.
 *
 * Paisa are shown only when there are any: a turf charges ৳1200, not ৳1200.00, and a
 * refund of ৳337.50 has to keep its fifty paisa. `null` is "—" rather than ৳0, because
 * "no price set" and "free" are different facts.
 */
export function formatMoney(amount: string | number | null | undefined, locale: string): string {
  if (amount === null || amount === undefined || amount === "") return "—";

  const value = Number(amount);
  if (!Number.isFinite(value)) return "—";

  const paisa = Math.round(value * 100) % 100 !== 0;
  return `৳${new Intl.NumberFormat(formattingLocale(locale), {
    ...NUMBERING,
    minimumFractionDigits: paisa ? 2 : 0,
    maximumFractionDigits: 2,
  }).format(value)}`;
}

/**
 * The date shapes the app actually uses.
 *
 * Named rather than spelled out at each call site, because Phase 11 found twenty-two
 * `Intl.DateTimeFormat("en-GB", …)` calls: every date in the app stayed English when
 * the rest of it turned Bangla, and six near-identical option objects had drifted apart.
 */
export const WHEN = {
  /** 19:30 */
  time: { hour: "2-digit", minute: "2-digit" },
  /** 4 Nov */
  dayMonth: { day: "numeric", month: "short" },
  /** 4 Nov, 19:30 */
  dayMonthTime: { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" },
  /** 4 Nov 2026 */
  dayMonthYear: { day: "numeric", month: "short", year: "numeric" },
  /** Wed 4 Nov, 19:30 */
  full: {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  },
  /** Wed 19:30 */
  weekdayTime: { weekday: "short", hour: "2-digit", minute: "2-digit" },
} as const satisfies Record<string, Intl.DateTimeFormatOptions>;

export type WhenStyle = keyof typeof WHEN;

/** A moment, in Dhaka time and the reader's language. */
export function formatWhen(
  value: string | number | Date,
  locale: string,
  style: WhenStyle = "full",
): string {
  return new Intl.DateTimeFormat(formattingLocale(locale), {
    ...WHEN[style],
    ...NUMBERING,
    timeZone: DHAKA,
  }).format(new Date(value));
}

/** A plain `YYYY-MM-DD` day, read as noon in Dhaka so no time zone can shift it. */
export function formatDay(day: string, locale: string, style: WhenStyle = "dayMonth"): string {
  return formatWhen(`${day}T12:00:00+06:00`, locale, style);
}
