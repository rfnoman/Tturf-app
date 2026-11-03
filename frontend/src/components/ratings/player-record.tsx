import { getServerApiClient } from "@/lib/api/server";

import { FairPlayBadge } from "./fair-play-badge";
import { RatingHistory } from "./rating-history";
import { TrackRecord } from "./track-record";

/**
 * Everything Phase 06 adds to a profile, fetched in one place.
 *
 * Three requests in parallel rather than one combined endpoint: they are independent,
 * they cache differently, and a profile with no history still renders the rest.
 */
export async function PlayerRecord({
  playerId,
  sport,
}: {
  playerId: string;
  /** Which sport's rating chart to draw. Omitted when the player has no sports. */
  sport?: string;
}) {
  const api = await getServerApiClient();

  const [record, fairPlay, history] = await Promise.all([
    api.GET("/api/v1/players/{player_id}/track-record", {
      params: { path: { player_id: playerId } },
    }),
    api.GET("/api/v1/players/{player_id}/fair-play", {
      params: { path: { player_id: playerId } },
    }),
    sport
      ? api.GET("/api/v1/players/{player_id}/rating-history", {
          params: { path: { player_id: playerId }, query: { sport } },
        })
      : Promise.resolve({ data: [] }),
  ]);

  return (
    <div className="flex flex-col gap-6">
      {fairPlay.data && (
        <div className="flex flex-wrap items-center gap-2">
          <FairPlayBadge fairPlay={fairPlay.data} />
        </div>
      )}
      {record.data && <TrackRecord record={record.data} />}
      {history.data && history.data.length > 0 && <RatingHistory changes={history.data} />}
    </div>
  );
}
