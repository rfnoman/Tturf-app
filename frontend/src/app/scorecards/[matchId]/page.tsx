import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { createPublicApiClient } from "@/lib/api/client";
import { ScorecardView } from "@/components/scoring/scorecard-view";
import { Button } from "@/components/ui/button";

/**
 * The shareable scorecard: no sign-in, no actions, only locked cards (DOMAIN §7).
 *
 * This is the link a player pastes into a group chat, so the Open Graph tags carry the
 * result — the preview has to say the score without anybody opening it.
 */
async function fetchScorecard(matchId: string) {
  const api = createPublicApiClient();
  const { data } = await api.GET("/api/v1/public/matches/{match_id}/scorecard", {
    params: { path: { match_id: matchId } },
  });
  return data;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ matchId: string }>;
}): Promise<Metadata> {
  const { matchId } = await params;
  const card = await fetchScorecard(matchId);
  if (!card) return { title: "Scorecard" };

  const teamA = card.teams.find((team) => team.side === "A")?.display_name ?? "Team A";
  const teamB = card.teams.find((team) => team.side === "B")?.display_name ?? "Team B";
  const title = `${teamA} ${card.team_a_score} – ${card.team_b_score} ${teamB}`;
  const description = [
    card.sport,
    card.turf_name,
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Dhaka",
      day: "numeric",
      month: "short",
      year: "numeric",
    }).format(new Date(card.played_at)),
    card.motm_name ? `MOTM: ${card.motm_name}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return {
    title,
    description,
    openGraph: { title, description, type: "article" },
    twitter: { card: "summary", title, description },
  };
}

export default async function PublicScorecardPage({
  params,
}: {
  params: Promise<{ matchId: string }>;
}) {
  const { matchId } = await params;
  const card = await fetchScorecard(matchId);
  // A card that is not locked yet simply does not exist publicly.
  if (!card) notFound();

  const t = await getTranslations("publicScorecard");

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-10">
      <ScorecardView scorecard={card} />

      <div className="flex flex-wrap items-center gap-3 border-t pt-6">
        <p className="text-muted-foreground text-sm">{t("tagline")}</p>
        <Button size="sm" asChild>
          <Link href="/play">{t("cta")}</Link>
        </Button>
      </div>
    </main>
  );
}
