"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";
import { Star } from "lucide-react";
import { cn } from "cn";

import type { MatchDetail, Scorecard } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * The post-match sheet: one MOTM vote, and a quick 1–5 rating for the other players.
 *
 * Peer ratings are anonymous to the recipient (DOMAIN §7) — the copy says so, because a
 * player who thinks the subject will see it rates everybody a 4.
 *
 * `myProfileId` comes from the page rather than being guessed here: the API refuses a
 * self vote or self rating, and the fix for that is not to offer it.
 */
export function PostMatchSheet({
  match,
  scorecard,
  myProfileId,
}: {
  match: MatchDetail;
  scorecard: Scorecard;
  myProfileId: string | null;
}) {
  const t = useTranslations("postMatch");
  const router = useRouter();
  const api = useApiClient();

  const [vote, setVote] = useState<string | null>(
    scorecard.my_motm_vote ? String(scorecard.my_motm_vote) : null,
  );
  // Seeded from what this player already gave, so a reload shows their stars back.
  const [ratings, setRatings] = useState<Record<string, number>>(
    () => scorecard.my_peer_ratings ?? {},
  );
  const [busy, setBusy] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const path = { path: { match_id: match.id } };
  const others = match.roster.filter(
    (entry) => entry.profile_id && String(entry.profile_id) !== myProfileId,
  );

  async function castVote(profileId: string) {
    setBusy(profileId);
    setError(null);
    const { error: apiError } = await api.POST("/api/v1/matches/{match_id}/motm", {
      params: path,
      body: { player_id: profileId } as never,
    });
    setBusy(null);
    if (apiError) {
      setError(t("voteFailed"));
      return;
    }
    setVote(profileId);
    router.refresh();
  }

  async function saveRatings() {
    setBusy("ratings");
    setError(null);
    const { error: apiError } = await api.POST("/api/v1/matches/{match_id}/peer-ratings", {
      params: path,
      body: {
        ratings: Object.entries(ratings).map(([playerId, overall]) => ({
          player_id: playerId,
          overall,
        })),
      } as never,
    });
    setBusy(null);
    if (apiError) {
      setError(t("ratingsFailed"));
      return;
    }
    setSaved(true);
    router.refresh();
  }

  // Nobody else played, or the reader is a spectator: there is nothing to rate.
  if (others.length === 0 || !myProfileId) return null;

  return (
    <div className="flex flex-col gap-4" data-testid="post-match">
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      {scorecard.motm_voting_open && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("motmHeading")}</CardTitle>
            <p className="text-muted-foreground text-xs">{t("motmHint")}</p>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {others.map((entry) => (
              <Button
                key={entry.id}
                size="sm"
                variant={vote === String(entry.profile_id) ? "default" : "outline"}
                aria-pressed={vote === String(entry.profile_id)}
                disabled={busy !== null}
                onClick={() => castVote(String(entry.profile_id))}
              >
                {entry.name}
              </Button>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("ratingsHeading")}</CardTitle>
          <p className="text-muted-foreground text-xs">{t("ratingsHint")}</p>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {others.map((entry) => (
            <div key={entry.id} className="flex flex-wrap items-center justify-between gap-2">
              <span className="truncate text-sm">{entry.name}</span>
              <span className="flex gap-0.5">
                {[1, 2, 3, 4, 5].map((star) => {
                  const chosen = (ratings[String(entry.profile_id)] ?? 0) >= star;
                  return (
                    <button
                      key={star}
                      type="button"
                      aria-label={t("starLabel", { name: entry.name, stars: star })}
                      aria-pressed={chosen}
                      onClick={() =>
                        setRatings((current) => ({
                          ...current,
                          [String(entry.profile_id)]: star,
                        }))
                      }
                      className="p-1"
                    >
                      <Star
                        aria-hidden
                        className={cn(
                          "size-5",
                          chosen ? "fill-amber-400 text-amber-400" : "text-muted-foreground/40",
                        )}
                      />
                    </button>
                  );
                })}
              </span>
            </div>
          ))}

          <div className="flex items-center gap-3 border-t pt-3">
            <Button
              size="sm"
              disabled={busy !== null || Object.keys(ratings).length === 0}
              onClick={saveRatings}
            >
              {busy === "ratings" ? t("saving") : t("saveRatings")}
            </Button>
            {saved && (
              <span role="status" className="text-muted-foreground text-sm">
                {t("ratingsSaved")}
              </span>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
