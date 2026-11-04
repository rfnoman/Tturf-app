import { useLocale } from "next-intl";

import { cn } from "@/lib/utils";
import { formatMoney } from "@/i18n/formats";

/**
 * An amount of money.
 *
 * No `"use client"`: `useLocale` works in both Server and Client Components, so a server
 * page renders this without shipping any JavaScript for it, and a client component uses
 * the same one.
 */
export function Money({
  amount,
  className,
}: {
  amount: string | number | null | undefined;
  className?: string;
}) {
  const locale = useLocale();
  return (
    <span className={cn("font-mono tabular-nums", className)}>{formatMoney(amount, locale)}</span>
  );
}
