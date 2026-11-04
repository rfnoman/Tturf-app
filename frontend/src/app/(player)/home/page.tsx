import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { StreakBadge } from "@/components/fitness/streak-badge";
import { WeekRing } from "@/components/fitness/week-ring";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatWhen } from "@/i18n/formats";

export const metadata = { title: "Home · TurfApp" };

/**
 * The player's home: the next match, the week so far, and one thing to do about it.
 *
 * Everything here is a link onwards. A dashboard that only reports is a dashboard
 * nobody opens twice.
 */
export default async function HomePage() {
  const api = await getServerApiClient();
  const [dashboard, mine, board] = await Promise.all([
    api.GET("/api/v1/me/dashboard"),
    api.GET("/api/v1/matches/mine"),
    api.GET("/api/v1/matches/board"),
  ]);

  const t = await getTranslations("fitness");
  const locale = await getLocale();
  const week = dashboard.data?.week;
  const goals = dashboard.data?.goals ?? [];
  const nextMatch = (mine.data ?? [])[0];
  const openMatches = (board.data ?? []).slice(0, 3);

  // The first goal is the one the ring tracks; the rest sit under it as bars.
  const headline = goals[0];
  const bundles = nextMatch
    ? await api.GET("/api/v1/bundles", { params: { query: { match: String(nextMatch.id) } } })
    : { data: [] };

  const when = (value: string) => formatWhen(value, locale, "full");

  return (
    <div className="flex flex-col gap-6" data-testid="home-dashboard">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
        <p className="text-muted-foreground text-sm">{t("body")}</p>
      </header>

      {nextMatch ? (
        <Card className="border-primary/40" data-testid="next-match">
          <CardHeader>
            <CardTitle className="text-sm">{t("nextMatch")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="font-medium">
                {nextMatch.sport.name} · {nextMatch.turf_name}
              </p>
              <p className="text-muted-foreground text-sm">{when(nextMatch.starts_at)}</p>
              {nextMatch.needed > 0 && (
                <Badge variant="secondary" className="mt-1">
                  {t("stillNeeds", { count: nextMatch.needed })}
                </Badge>
              )}
            </div>
            <Button size="sm" asChild>
              <Link href={`/matches/${nextMatch.id}`}>{t("openMatch")}</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-5">
            <p className="text-sm">{t("noMatch")}</p>
            <Button size="sm" asChild>
              <Link href="/play">{t("findMatch")}</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("thisWeek")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <WeekRing
              percent={headline?.percent ?? 0}
              label={t("minutes", { minutes: week?.minutes ?? 0 })}
              sublabel={
                headline
                  ? t("ofGoal", { target: headline.target, label: headline.label })
                  : t("noGoal")
              }
            />
            <p className="text-muted-foreground text-sm">
              {t("weekSummary", {
                matches: week?.matches ?? 0,
                calories: week?.calories ?? 0,
              })}
              {week?.is_estimate && ` · ${t("estimated")}`}
            </p>
            <Button size="sm" variant="outline" className="self-start" asChild>
              <Link href="/activity">{t("seeActivity")}</Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("streak")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {dashboard.data?.streak && <StreakBadge streak={dashboard.data.streak} />}

            {goals.length > 0 && (
              <ul className="flex flex-col gap-2">
                {goals.map((goal) => (
                  <li key={String(goal.id)} className="flex flex-col gap-1">
                    <span className="flex items-baseline justify-between text-xs">
                      <span>{goal.label}</span>
                      <span className="text-muted-foreground font-mono tabular-nums">
                        {goal.achieved}/{goal.target}
                      </span>
                    </span>
                    <span className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
                      <span
                        className="bg-primary block h-full rounded-full"
                        style={{ width: `${goal.percent}%` }}
                      />
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {(bundles.data ?? []).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">
              {nextMatch ? t("forNextMatch", { turf: nextMatch.turf_name }) : t("bundles")}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {(bundles.data ?? []).map((bundle) => (
              <Link
                key={String(bundle.id)}
                href="/store"
                className="hover:border-primary/40 flex min-w-48 flex-col gap-1 rounded-xl border p-3 text-sm transition-colors"
              >
                <span className="font-medium">{bundle.name}</span>
                <span className="text-muted-foreground text-xs">
                  {bundle.items.map((item) => `${item.quantity}× ${item.product_name}`).join(", ")}
                </span>
              </Link>
            ))}
          </CardContent>
        </Card>
      )}

      {openMatches.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("openNearby")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-1.5">
            {openMatches.map((match) => (
              <Link
                key={String(match.id)}
                href={`/matches/${match.id}`}
                className="hover:bg-muted/50 -mx-2 flex flex-wrap items-center justify-between gap-2 rounded px-2 py-1.5 text-sm"
              >
                <span className="truncate">
                  {match.sport.icon} {match.turf_name} · {when(match.starts_at)}
                </span>
                <Badge variant="outline">{t("stillNeeds", { count: match.needed })}</Badge>
              </Link>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
