import { notFound } from "next/navigation";

import { getServerApiClient } from "@/lib/api/server";
import { PlayerProfileView } from "@/components/player/player-profile-view";
import { RecentResults } from "@/components/scoring/recent-results";

/**
 * Another player's public card.
 *
 * `discoverable` gates player *search* only — a direct link always resolves
 * (DOMAIN §3), which is what makes a shared profile URL useful.
 */
export default async function PlayerPage({ params }: { params: Promise<{ playerId: string }> }) {
  // `params` is a promise in Next 16.
  const { playerId } = await params;

  const api = await getServerApiClient();
  const { data } = await api.GET("/api/v1/players/{player_id}", {
    params: { path: { player_id: playerId } },
  });

  if (!data) notFound();

  return <PlayerProfileView player={data} footer={<RecentResults playerId={String(data.id)} />} />;
}
