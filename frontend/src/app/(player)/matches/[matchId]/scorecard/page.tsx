import Link from "next/link";
import { notFound } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { ScorecardView } from "@/components/scoring/scorecard-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { ConductReportForm } from "@/components/ratings/conduct-report-form";

import { PostMatchSheet } from "./post-match";
import { ScorecardDecision, ScorecardEditor } from "./scorecard-editor";
import { TeamBuilder } from "./team-builder";
import { formatWhen } from "@/i18n/formats";

/**
 * One page, four readers: the scorer entering the card, the opposing captain confirming
 * it, turf staff settling a dispute, and everybody else reading it. Which one you are is
 * decided by the API (`can_edit` / `can_confirm` / `can_resolve`), never re-derived here.
 */
export default async function ScorecardPage({ params }: { params: Promise<{ matchId: string }> }) {
  const { matchId } = await params;
  const api = await getServerApiClient();

  const [match, scorecard, teams, profile] = await Promise.all([
    api.GET("/api/v1/matches/{id}", { params: { path: { id: matchId } } }),
    api.GET("/api/v1/matches/{match_id}/scorecard", {
      params: { path: { match_id: matchId } },
    }),
    // This GET creates the two team rows if they do not exist yet, which is what makes
    // the team builder's first render meaningful.
    api.GET("/api/v1/matches/{match_id}/teams", {
      params: { path: { match_id: matchId } },
    }),
    api.GET("/api/v1/me/profile"),
  ]);

  if (!match.data || !scorecard.data) notFound();

  const t = await getTranslations("scorecardPage");
  const locale = await getLocale();
  const card = scorecard.data;
  const teamRows = teams.data ?? card.teams;
  const isDraft = card.status === "draft";
  const isPublic = card.status === "locked";
  const canRate = card.submitted_at !== null && match.data.is_on_roster;

  const when = formatWhen(card.played_at, locale, "full");

  return (
    <div className="flex flex-col gap-6" data-testid="scorecard-page">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
          <p className="text-muted-foreground text-sm">
            {card.sport} · {card.turf_name} · {when}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge variant={isDraft ? "outline" : "secondary"} data-testid="scorecard-status">
              {card.status_label}
            </Badge>
            {card.scorer_name && (
              <span className="text-muted-foreground text-xs">
                {t("scorer", { name: card.scorer_name })}
              </span>
            )}
          </div>
        </div>
        <Button variant="ghost" size="sm" asChild>
          <Link href={`/matches/${matchId}`}>{t("backToMatch")}</Link>
        </Button>
      </header>

      {/* Only while it is open: the reason outlives the dispute on the row, and a
          settled card showing "disputed" reads as unresolved. */}
      {card.status === "disputed" && card.dispute_reason && (
        <Card>
          <CardHeader>
            <CardTitle className="text-destructive text-sm">{t("disputed")}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">{card.dispute_reason}</CardContent>
        </Card>
      )}

      {card.can_edit && isDraft && <TeamBuilder match={match.data} teams={teamRows} />}

      {/* Resolving comes first: a disputed card is editable by its scorer too, but for
          somebody who can settle it, settling is the action that matters. */}
      {card.can_resolve ? (
        <ScorecardEditor match={match.data} scorecard={card} teams={teamRows} mode="resolve" />
      ) : card.can_edit ? (
        <ScorecardEditor match={match.data} scorecard={card} teams={teamRows} />
      ) : (
        <ScorecardView scorecard={card} />
      )}

      {card.can_confirm && <ScorecardDecision match={match.data} />}

      {canRate && (
        <PostMatchSheet
          match={match.data}
          scorecard={card}
          myProfileId={profile.data?.id ? String(profile.data.id) : null}
        />
      )}

      {canRate && (
        <ConductReportForm
          matchId={matchId}
          players={match.data.roster.filter(
            (entry) => entry.profile_id && String(entry.profile_id) !== String(profile.data?.id),
          )}
        />
      )}

      {isPublic && (
        <div className="flex flex-wrap items-center gap-3 border-t pt-4">
          <Button variant="outline" size="sm" asChild>
            <Link href={`/scorecards/${matchId}`}>{t("viewPublic")}</Link>
          </Button>
          <span className="text-muted-foreground text-xs">{t("shareHint")}</span>
        </div>
      )}

      {card.events.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("history")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="flex flex-col gap-1.5 text-sm">
              {card.events.map((event) => (
                <li key={String(event.id)} className="flex flex-wrap gap-x-2">
                  <span className="font-medium">{event.to_status_label}</span>
                  {event.actor_name && (
                    <span className="text-muted-foreground">{event.actor_name}</span>
                  )}
                  <span className="text-muted-foreground">
                    {formatWhen(event.created_at, locale, "dayMonthTime")}
                  </span>
                  {event.note && <span className="text-muted-foreground">— {event.note}</span>}
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
