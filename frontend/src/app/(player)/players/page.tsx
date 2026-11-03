import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { PlayerSearch } from "./player-search";

export const metadata = { title: "Find players · TurfApp" };

/**
 * Player discovery (DOMAIN §3).
 *
 * The filters and the results live in a client component so a change to a filter does
 * not reload the page; the sports list and the reader's own upcoming matches are
 * fetched here, because both are needed before the first search.
 */
export default async function PlayersPage() {
  const api = await getServerApiClient();
  const [sports, mine, squads] = await Promise.all([
    api.GET("/api/v1/sports"),
    api.GET("/api/v1/matches/mine"),
    api.GET("/api/v1/squads"),
  ]);

  const t = await getTranslations("playerSearch");

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
        <p className="text-muted-foreground text-sm">{t("body")}</p>
      </header>

      <PlayerSearch
        sports={sports.data ?? []}
        matches={(mine.data ?? []).filter((match) => match.needed > 0)}
        squads={squads.data?.results ?? []}
      />
    </div>
  );
}
