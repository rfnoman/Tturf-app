import { formatDay } from "@/i18n/formats";
import { getLocale } from "next-intl/server";
import { getTranslations } from "next-intl/server";

type Row = { day: string; total: number; confirmed: number };

/**
 * Bookings a day, as bars.
 *
 * Drawn with divs rather than a charting library: it is one series over at most ninety
 * points, and a dependency that ships a canvas renderer to draw ninety rectangles is a
 * poor trade on a connection this app has to work on.
 *
 * Days with no bookings are rendered as empty columns rather than skipped — a chart that
 * silently drops them draws a line that looks healthy through an outage.
 */
export async function BookingsChart({ rows }: { rows: Row[] }) {
  const locale = await getLocale();
  const t = await getTranslations("dashboard");
  const peak = Math.max(1, ...rows.map((row) => row.total));

  return (
    <div className="flex flex-col gap-2">
      {/* A baseline, so a day with no bookings reads as a zero rather than as nothing. */}
      <div
        className="border-border flex h-32 items-end gap-0.5 border-b"
        role="img"
        aria-label={t("chartLabel")}
      >
        {rows.map((row) => (
          <div
            key={row.day}
            className="bg-muted relative flex-1 rounded-t"
            style={{ height: `${Math.max(2, (row.total / peak) * 100)}%` }}
            title={`${formatDay(row.day, locale)} · ${row.total}`}
          >
            {/* Confirmed sits inside the total, so the gap between them reads as the
                bookings a turf never answered. */}
            <div
              className="bg-primary absolute inset-x-0 bottom-0 rounded-t"
              style={{ height: `${row.total ? (row.confirmed / row.total) * 100 : 0}%` }}
            />
          </div>
        ))}
      </div>
      <p className="text-muted-foreground flex justify-between text-xs">
        <span>{formatDay(rows[0]?.day ?? "", locale)}</span>
        <span>{t("peak", { count: peak })}</span>
        <span>{formatDay(rows.at(-1)?.day ?? "", locale)}</span>
      </p>
    </div>
  );
}
