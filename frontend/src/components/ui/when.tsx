import { useLocale } from "next-intl";

import { formatDay, formatWhen, type WhenStyle } from "@/i18n/formats";

/**
 * A moment in Dhaka time, in the reader's language.
 *
 * Like `Money`, no `"use client"`: `useLocale` works on both sides, so a server page
 * ships no JavaScript for it.
 */
export function When({
  at,
  style = "full",
  className,
}: {
  at: string | number | Date;
  style?: WhenStyle;
  className?: string;
}) {
  const locale = useLocale();
  return (
    <span className={className ?? "font-mono tabular-nums"}>{formatWhen(at, locale, style)}</span>
  );
}

/** A `YYYY-MM-DD` day with no time of day — a ledger line, an activity log entry. */
export function Day({
  day,
  style = "dayMonth",
  className,
}: {
  day: string;
  style?: WhenStyle;
  className?: string;
}) {
  const locale = useLocale();
  return (
    <span className={className ?? "font-mono tabular-nums"}>{formatDay(day, locale, style)}</span>
  );
}
