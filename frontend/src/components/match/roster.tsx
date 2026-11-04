import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { cn } from "cn";

import type { RosterPlayer } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { ratingTone } from "@/components/player/rating";

/**
 * The match roster.
 *
 * Each row links to the player's Phase 01 profile card, which is the point of having
 * made that card reusable: a player judging a match wants to see who is in it.
 */
export async function Roster({
  players,
  capacity,
  action,
}: {
  players: readonly RosterPlayer[];
  capacity: number;
  action?: (player: RosterPlayer) => React.ReactNode;
}) {
  const t = await getTranslations("matchPage");
  const empty = Math.max(0, capacity - players.length);

  return (
    <ul className="flex flex-col gap-2">
      {players.map((entry) => (
        <li
          key={entry.id}
          className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2"
        >
          <span className="flex min-w-0 items-center gap-3">
            {entry.photo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={entry.photo_url}
                alt=""
                loading="lazy"
                decoding="async"
                className="bg-muted size-8 shrink-0 rounded-full object-cover"
              />
            ) : (
              <span
                aria-hidden
                className="bg-muted text-muted-foreground flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold"
              >
                {entry.name.slice(0, 1).toUpperCase()}
              </span>
            )}
            <span className="min-w-0">
              {entry.profile_id ? (
                <Link
                  href={`/players/${entry.profile_id}`}
                  className="block truncate text-sm font-medium underline-offset-2 hover:underline"
                >
                  {entry.name}
                </Link>
              ) : (
                <span className="block truncate text-sm font-medium">{entry.name}</span>
              )}
              <span className="text-muted-foreground block text-xs">
                {entry.area || t(`source.${entry.source}`)}
              </span>
            </span>
          </span>

          <span className="flex shrink-0 items-center gap-2">
            {entry.overall != null && (
              <span
                className={cn(
                  "font-mono text-sm font-semibold tabular-nums",
                  ratingTone(entry.overall),
                )}
                title={entry.is_provisional ? t("unverifiedRating") : undefined}
              >
                {entry.overall}
                {entry.is_provisional && <span aria-hidden>*</span>}
              </span>
            )}
            {action?.(entry)}
          </span>
        </li>
      ))}

      {Array.from({ length: empty }).map((_, index) => (
        <li
          key={`empty-${index}`}
          className="text-muted-foreground border-border/60 rounded-lg border border-dashed px-3 py-2 text-sm"
        >
          {t("emptySpot")}
        </li>
      ))}

      {players.some((entry) => entry.is_provisional) && (
        <li className="text-muted-foreground text-xs">
          <Badge variant="outline" className="mr-1.5 text-[0.625rem]">
            *
          </Badge>
          {t("unverifiedRating")}
        </li>
      )}
    </ul>
  );
}
