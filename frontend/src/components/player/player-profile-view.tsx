import Image from "next/image";
import { getTranslations } from "next-intl/server";

import type { PlayerCardProfile } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { PlayerAttributes, PlayerSportCardView } from "./player-card";
import { SportTabs, type SportTab } from "./sport-tabs";

/**
 * The whole profile page body: header, shared attributes, one tab per sport.
 *
 * Serves both `/profile` (mine) and `/players/{id}` (someone else's) — the only
 * difference is which serializer filled `player`, so the component takes the common
 * {@link PlayerCardProfile} shape and an optional `action` slot for owner-only buttons.
 */
export async function PlayerProfileView({
  player,
  action,
}: {
  player: PlayerCardProfile;
  action?: React.ReactNode;
}) {
  const t = await getTranslations("profile");
  const cards = player.sport_cards;

  const tabs: SportTab[] = await Promise.all(
    cards.map(async (card) => ({
      value: card.sport.slug,
      label: card.sport.name,
      icon: card.sport.icon,
      content: <PlayerSportCardView player={player} card={card} />,
    })),
  );

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-start gap-4">
        {player.photo_url ? (
          <Image
            src={player.photo_url}
            alt=""
            width={64}
            height={64}
            className="bg-muted size-16 shrink-0 rounded-full object-cover"
            unoptimized
          />
        ) : (
          <div
            aria-hidden
            className="bg-muted text-muted-foreground flex size-16 shrink-0 items-center justify-center rounded-full text-xl font-semibold"
          >
            {player.name.slice(0, 1).toUpperCase()}
          </div>
        )}

        <div className="min-w-0 flex-1">
          <h1 className="truncate text-2xl font-semibold tracking-tight">{player.name}</h1>
          {player.area && <p className="text-muted-foreground text-sm">{player.area}</p>}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge variant="secondary">
              {t("reliability", { score: player.reliability_score })}
            </Badge>
            {cards.length > 0 && (
              <Badge variant="outline">{t("sportCount", { count: cards.length })}</Badge>
            )}
          </div>
          {player.bio && <p className="mt-3 text-sm leading-relaxed">{player.bio}</p>}
        </div>

        {action}
      </header>

      {cards.length === 0 ? (
        <Card>
          <CardContent className="text-muted-foreground py-8 text-center text-sm">
            {t("noSports")}
          </CardContent>
        </Card>
      ) : (
        <SportTabs tabs={tabs} />
      )}

      <Card className="w-full max-w-xl">
        <CardHeader>
          <CardTitle className="text-sm">{t("attributesHeading")}</CardTitle>
          <p className="text-muted-foreground text-xs">{t("attributesHint")}</p>
        </CardHeader>
        <CardContent>
          <PlayerAttributes player={player} />
        </CardContent>
      </Card>
    </div>
  );
}
