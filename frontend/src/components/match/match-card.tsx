import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";

import type { MatchSummary } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { ratingTone } from "@/components/player/rating";
import { Money } from "@/components/ui/money";
import { formatWhen } from "@/i18n/formats";

/**
 * One match on the board (DOMAIN §6).
 *
 * The brief's shape: "Mirpur Turf · Ground 2 · Fri 9:00 PM · 7v7 · Need 3 · Avg 68" —
 * the four things a player decides on before opening anything.
 */
export async function MatchCard({ match }: { match: MatchSummary }) {
  const t = await getTranslations("board");
  const locale = await getLocale();

  const when = formatWhen(match.starts_at, locale, "full");

  return (
    <Link
      href={`/matches/${match.id}`}
      className="bg-card hover:bg-muted/40 flex flex-col gap-2 rounded-xl border p-4 shadow-sm transition-colors"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-base font-semibold">
            <span aria-hidden className="mr-1.5">
              {match.sport.icon}
            </span>
            {match.turf_name}
          </h3>
          <p className="text-muted-foreground truncate text-xs">
            {match.ground_name} · {match.area}
            {match.distance_km != null && ` · ${t("kmAway", { km: match.distance_km })}`}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-sm font-medium">{when}</p>
          <p className="text-muted-foreground text-xs">{match.sport_format.name}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="default">{t("needed", { count: match.needed })}</Badge>
          {match.squad && <Badge variant="secondary">{match.squad.name}</Badge>}
          <span className="text-muted-foreground text-xs">
            {t("rosterOf", { count: match.roster_count, capacity: match.capacity })}
          </span>
        </div>
        <div className="flex items-center gap-3 text-xs">
          {match.average_rating != null ? (
            <span className={ratingTone(match.average_rating)}>
              {t("avgRating", { rating: match.average_rating })}
            </span>
          ) : (
            <span className="text-muted-foreground">{t("unrated")}</span>
          )}
          <Money amount={match.price} />
        </div>
      </div>
    </Link>
  );
}
