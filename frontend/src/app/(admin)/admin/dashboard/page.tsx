import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Money } from "@/components/ui/money";
import { Day } from "@/components/ui/when";

import { BookingsChart } from "./bookings-chart";

export const metadata = { title: "Dashboard · TurfApp" };

/**
 * Whether the pilot is working.
 *
 * Every number here was already derivable from rows the app writes; what was missing was
 * anywhere to read them together. A turf owner has a finance page and an admin has four
 * separate queues, but nobody could answer "how many bookings yesterday, and how many of
 * them did somebody turn up to".
 */
export default async function AdminDashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  // `searchParams` is a promise in Next 16.
  const { days } = await searchParams;
  const window = days ?? "30";

  const api = await getServerApiClient();
  const { data } = await api.GET("/api/v1/admin/dashboard", {
    params: { query: { days: Number(window) } },
  });
  const t = await getTranslations("dashboard");

  if (!data) {
    return <p className="text-muted-foreground text-sm">{t("unavailable")}</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
          <p className="text-muted-foreground text-sm">
            <Day day={data.period_start} className="" /> –{" "}
            <Day day={data.period_end} className="" />
          </p>
        </div>
        <nav className="flex gap-2 text-sm">
          {["7", "30", "90"].map((option) => (
            <Link
              key={option}
              href={`/admin/dashboard?days=${option}`}
              className={
                option === window
                  ? "bg-primary text-primary-foreground rounded-md px-3 py-1.5"
                  : "hover:bg-muted rounded-md border px-3 py-1.5"
              }
            >
              {t("lastDays", { days: Number(option) })}
            </Link>
          ))}
        </nav>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Figure
          label={t("bookings")}
          value={data.bookings}
          hint={t("confirmedOf", { count: data.bookings_confirmed })}
        />
        <Figure
          label={t("noShowRate")}
          value={`${data.no_show_rate}%`}
          // Counted against bookings that reached their slot, not every booking ever
          // made: a cancelled booking is not a no-show.
          hint={t("noShowHint", { count: data.no_shows })}
        />
        <Figure
          label={t("activePlayers")}
          value={data.active_players}
          hint={t("newPlayers", { count: data.new_players })}
        />
        <Figure
          label={t("turfsLive")}
          value={data.turfs_live}
          hint={t("turfsPending", { count: data.turfs_pending })}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">{t("platformEarnings")}</CardTitle>
          </CardHeader>
          <CardContent>
            <Money
              amount={data.platform_earnings}
              className="font-mono text-2xl font-bold tabular-nums"
            />
            <p className="text-muted-foreground mt-1 text-xs">
              {t("commission")} <Money amount={data.commission} className="" />
            </p>
          </CardContent>
        </Card>
        <Figure label={t("matches")} value={data.matches} hint="" />
        <Figure
          label={t("orders")}
          value={data.orders}
          hint={t("fulfilled", { count: data.orders_fulfilled })}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">{t("perDay")}</CardTitle>
        </CardHeader>
        <CardContent>
          <BookingsChart rows={data.per_day} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">{t("topTurfs")}</CardTitle>
        </CardHeader>
        <CardContent>
          {data.top_turfs.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("noTurfs")}</p>
          ) : (
            <ol className="flex flex-col gap-2 text-sm">
              {data.top_turfs.map((turf) => (
                <li key={turf.slug} className="flex items-baseline justify-between gap-3">
                  <Link href={`/turfs/${turf.slug}`} className="hover:underline">
                    {turf.name}
                    <span className="text-muted-foreground"> · {turf.area}</span>
                  </Link>
                  <span className="font-mono tabular-nums">{turf.bookings}</span>
                </li>
              ))}
            </ol>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Figure({ label, value, hint }: { label: string; value: string | number; hint: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="font-mono text-2xl font-bold tabular-nums">{value}</p>
        {hint && <p className="text-muted-foreground mt-1 text-xs">{hint}</p>}
      </CardContent>
    </Card>
  );
}
