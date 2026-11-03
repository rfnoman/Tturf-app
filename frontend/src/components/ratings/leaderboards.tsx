import { getTranslations } from "next-intl/server";

import type { LeaderboardEntry } from "@/lib/api/types";
import { getServerApiClient } from "@/lib/api/server";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Metric = "rating" | "motm" | "top_stat";
type Board = { metric: Metric; statKey: string; rows: LeaderboardEntry[] };

const METRICS: Metric[] = ["rating", "motm", "top_stat"];

/** Which stat each sport's "top of the charts" board is built on, mirroring the task. */
const HEADLINE_STAT: Record<string, string> = {
  football: "goals",
  futsal: "goals",
  cricket: "runs",
  badminton: "aces",
};

/**
 * A turf's boards for one sport (DOMAIN §8).
 *
 * Read from the nightly table rather than computed here — a turf page is read far more
 * often than the standings change.
 */
export async function Leaderboards({
  turfSlug,
  sport,
}: {
  turfSlug: string;
  /** Only the slug and name are needed, so a turf's summary sport is enough. */
  sport: { slug: string; name: string };
}) {
  const api = await getServerApiClient();
  const t = await getTranslations("leaderboard");

  const results = await Promise.all(
    METRICS.map(async (metric): Promise<Board | null> => {
      const statKey = metric === "top_stat" ? (HEADLINE_STAT[sport.slug] ?? "") : "";
      if (metric === "top_stat" && !statKey) return null;

      const { data } = await api.GET("/api/v1/leaderboard", {
        params: {
          query: {
            sport: sport.slug,
            turf: turfSlug,
            metric,
            stat_key: statKey,
            period: "month",
          },
        },
      });
      return { metric, statKey, rows: data ?? [] };
    }),
  );

  const boards = results.filter((board): board is Board => board !== null && board.rows.length > 0);

  if (boards.length === 0) {
    return <p className="text-muted-foreground text-sm">{t("empty")}</p>;
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="leaderboards">
      {boards.map((board) => (
        <Card key={`${board.metric}-${board.statKey}`}>
          <CardHeader>
            <CardTitle className="text-sm">
              {t("title", { metric: board.metric, stat: board.statKey })}
            </CardTitle>
            <p className="text-muted-foreground text-xs">{t("thisMonth")}</p>
          </CardHeader>
          <CardContent>
            <ol className="flex flex-col gap-1.5 text-sm">
              {board.rows.map((row) => (
                <li key={String(row.id)} className="flex items-baseline gap-2">
                  <span className="text-muted-foreground w-5 text-right text-xs tabular-nums">
                    {row.rank}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{row.player_name}</span>
                  <span className="font-mono text-sm font-semibold tabular-nums">
                    {Number(row.value) % 1 === 0 ? Number(row.value) : row.value}
                  </span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
