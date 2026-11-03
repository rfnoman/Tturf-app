/**
 * Locale configuration.
 *
 * TurfApp does not prefix URLs with the locale (DECISIONS D13): `/bookings` stays
 * `/bookings` in both languages and the choice lives in a cookie. That keeps route
 * groups flat for every later phase and leaves Clerk's proxy untouched.
 */

export const locales = ["en", "bn"] as const;

export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "en";

/** Name of the cookie holding the reader's choice. */
export const LOCALE_COOKIE = "NEXT_LOCALE";

/** One year: the preference should survive well beyond a single session. */
export const LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

export const localeLabels: Record<Locale, string> = {
  en: "English",
  bn: "বাংলা",
};

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (locales as readonly string[]).includes(value);
}
