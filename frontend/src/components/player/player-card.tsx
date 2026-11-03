import { getTranslations } from "next-intl/server";
import { cn } from "cn";

import type { PlayerCardProfile, PlayerSportCard } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";

import { RatingBar, ratingTone } from "./rating";

/**
 * The FIFA-style card for one (player, sport).
 *
 * Built as a reusable server component because every later phase renders it: the match
 * board (Phase 04), scorecards (Phase 05), player search and leaderboards (Phase 06).
 * It therefore takes only the data in {@link PlayerCardProfile} — the shape both
 * `/me/profile` and `/players/{id}` return — and never fetches anything itself.
 *
 * `compact` drops the skill bars and record, for list contexts.
 */
export async function PlayerSportCardView({
  player,
  card,
  compact = false,
  className,
}: {
  player: Pick<PlayerCardProfile, "name" | "photo_url" | "area">;
  card: PlayerSportCard;
  compact?: boolean;
  className?: string;
}) {
  const t = await getTranslations("playerCard");
  const unverified = card.is_provisional || !card.is_verified;

  return (
    <article
      className={cn(
        // Capped width: a stat bar stretched across a 1200px column reads as a
        // progress indicator, not a rating. Full width below `sm`.
        "bg-card text-card-foreground relative w-full max-w-xl overflow-hidden rounded-xl border shadow-sm",
        className,
      )}
      aria-label={t("ariaLabel", { name: player.name, sport: card.sport.name })}
    >
      {/* A faint wash keyed to the rating band, so a card reads before it is read. */}
      <div
        aria-hidden
        className="from-primary/8 pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b to-transparent"
      />

      <div className="relative flex items-start gap-4 p-4">
        <div className="flex flex-col items-center">
          <span
            className={cn(
              "font-mono text-4xl leading-none font-bold tabular-nums",
              ratingTone(card.overall),
            )}
          >
            {card.overall}
          </span>
          <span className="text-muted-foreground mt-1 text-[0.625rem] tracking-widest uppercase">
            {t("overall")}
          </span>
          {card.positions.length > 0 && (
            <span className="mt-2 text-xs font-semibold tracking-wide">
              {card.positions.join(" / ")}
            </span>
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="truncate text-base leading-tight font-semibold">{player.name}</h3>
              <p className="text-muted-foreground mt-0.5 flex items-center gap-1.5 text-xs">
                <span aria-hidden>{card.sport.icon}</span>
                <span>{card.sport.name}</span>
                {player.area ? <span>· {player.area}</span> : null}
              </p>
            </div>
            {unverified && (
              <Badge variant="outline" className="shrink-0 text-[0.625rem]">
                {t("unverified")}
              </Badge>
            )}
          </div>

          {!compact && card.skills.length > 0 && (
            <div className="mt-3 flex flex-col gap-1.5">
              {card.skills.map((skill) => (
                <RatingBar key={skill.key} label={skill.label} value={skill.value} />
              ))}
            </div>
          )}
        </div>
      </div>

      {!compact && (
        <dl className="bg-muted/40 grid grid-cols-4 divide-x border-t text-center">
          {(
            [
              ["matches", card.matches_played],
              ["wins", card.wins],
              ["losses", card.losses],
              ["motm", card.motm_awards],
            ] as const
          ).map(([key, value]) => (
            <div key={key} className="px-1 py-2">
              <dt className="text-muted-foreground text-[0.625rem] tracking-wide uppercase">
                {t(key)}
              </dt>
              <dd className="font-mono text-sm font-semibold tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </article>
  );
}

/**
 * The shared attributes (DOMAIN §3) — they belong to the player, not a sport, so they
 * sit beside the sport cards rather than inside them.
 */
export async function PlayerAttributes({
  player,
  className,
}: {
  player: Pick<PlayerCardProfile, "attributes">;
  className?: string;
}) {
  const t = await getTranslations("playerCard");

  if (player.attributes.length === 0) {
    return <p className="text-muted-foreground text-sm">{t("noAttributes")}</p>;
  }

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      {player.attributes.map((attribute) => (
        <RatingBar key={attribute.key} label={attribute.label} value={attribute.value} />
      ))}
    </div>
  );
}
