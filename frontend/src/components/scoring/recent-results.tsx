import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { cn } from "cn";

import { getServerApiClient } from "@/lib/api/server";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatWhen } from "@/i18n/formats";

/**
 * A player's recent results — the track record on their profile.
 *
 * Every row links to the public card rather than the match page: it is the view that
 * works for a reader who is not in that match, which on a profile is everybody.
 */
export async function RecentResults({ playerId }: { playerId: string }) {
  const api = await getServerApiClient();
  const { data } = await api.GET("/api/v1/players/{player_id}/results", {
    params: { path: { player_id: playerId } },
  });

  // A fixed, bounded list (the most recent 20) rather than a paginated one — a profile
  // shows a track record, not an archive.
  const results = data ?? [];
  if (results.length === 0) return null;

  const t = await getTranslations("results");
  const locale = await getLocale();

  return (
    <Card className="w-full max-w-xl" data-testid="recent-results">
      <CardHeader>
        <CardTitle className="text-sm">{t("heading")}</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col divide-y">
          {results.map((row) => (
            <li key={String(row.match_id)}>
              <Link
                href={`/scorecards/${row.match_id}`}
                className="hover:bg-muted/50 -mx-2 flex items-center gap-3 rounded px-2 py-2"
              >
                <span
                  className={cn(
                    "w-5 shrink-0 text-center text-xs font-bold",
                    row.outcome === "win" && "text-emerald-600 dark:text-emerald-400",
                    row.outcome === "loss" && "text-destructive",
                    row.outcome === "draw" && "text-muted-foreground",
                  )}
                  aria-label={t("outcome", { outcome: row.outcome })}
                >
                  {t("outcomeShort", { outcome: row.outcome })}
                </span>
                <span className="font-mono text-sm tabular-nums">
                  {row.my_side === "B"
                    ? `${row.team_b_score}–${row.team_a_score}`
                    : `${row.team_a_score}–${row.team_b_score}`}
                </span>
                <span className="text-muted-foreground min-w-0 flex-1 truncate text-xs">
                  {row.sport} · {row.turf_name} · {formatWhen(row.played_at, locale, "dayMonth")}
                </span>
                {row.is_motm && <Badge variant="outline">{t("motm")}</Badge>}
                {row.verified_by_staff && <Badge variant="secondary">{t("verified")}</Badge>}
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
