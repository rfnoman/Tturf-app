"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { cn } from "cn";

import type { MatchDetail, MatchTeam, Scorecard } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { ScoreStepper } from "@/components/scoring/score-stepper";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Stats = Record<string, Record<string, number>>;

/** A DRF 400 maps field → messages; the entry form shows each against its input. */
function fieldErrors(error: unknown): Record<string, string> {
  if (!error || typeof error !== "object") return {};
  const out: Record<string, string> = {};
  for (const [field, value] of Object.entries(error as Record<string, unknown>)) {
    out[field] = Array.isArray(value) ? value.join(" ") : String(value);
  }
  return out;
}

/**
 * Scorecard entry, built for a phone at the side of a pitch.
 *
 * Every stat input is a stepper, the form is generated from the sport's
 * `stat_definitions`, and validation errors come back from the API mapped to fields so
 * they can be shown inline rather than as one wall of text.
 */
export function ScorecardEditor({
  match,
  scorecard,
  teams,
  mode = "score",
}: {
  match: MatchDetail;
  scorecard: Scorecard;
  teams: MatchTeam[];
  /**
   * `resolve` is the same form in the hands of turf staff settling a dispute: the
   * numbers and the validators are identical, only the endpoint and the wording differ.
   */
  mode?: "score" | "resolve";
}) {
  const t = useTranslations("scorecardEditor");
  const router = useRouter();
  const api = useApiClient();

  const [teamA, setTeamA] = useState(scorecard.team_a_score);
  const [teamB, setTeamB] = useState(scorecard.team_b_score);
  const [stats, setStats] = useState<Stats>(() => {
    const seed: Stats = {};
    for (const row of scorecard.rows) {
      seed[String(row.player_id)] = Object.fromEntries(
        Object.entries(row.stats).map(([key, value]) => [key, Number(value)]),
      );
    }
    return seed;
  });
  const [busy, setBusy] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);

  const definitions = scorecard.stat_definitions;
  const path = { path: { match_id: match.id } };

  const players = useMemo(
    () =>
      teams.flatMap((team) =>
        team.players.map((player) => ({ ...player, side: team.side, teamName: team.display_name })),
      ),
    [teams],
  );

  function setStat(playerId: string, key: string, value: number) {
    setStats((current) => ({
      ...current,
      [playerId]: { ...(current[playerId] ?? {}), [key]: value },
    }));
  }

  function body() {
    return {
      team_a_score: teamA,
      team_b_score: teamB,
      // Zeroes are dropped: an untouched stepper is "not recorded", not "zero of it".
      stats: Object.fromEntries(
        Object.entries(stats)
          .map(([playerId, values]) => [
            playerId,
            Object.fromEntries(Object.entries(values).filter(([, value]) => value !== 0)),
          ])
          .filter(([, values]) => Object.keys(values as object).length > 0),
      ),
    } as never;
  }

  async function save() {
    setBusy("save");
    setErrors({});
    const { error } = await api.PATCH("/api/v1/matches/{match_id}/scorecard", {
      params: path,
      body: body(),
    });
    setBusy(null);
    if (error) {
      setErrors(fieldErrors(error));
      return;
    }
    setSaved(true);
    router.refresh();
  }

  async function resolve() {
    setBusy("submit");
    setErrors({});
    const { error } = await api.POST("/api/v1/matches/{match_id}/scorecard/resolve", {
      params: path,
      body: body(),
    });
    setBusy(null);
    if (error) {
      setErrors(fieldErrors(error));
      return;
    }
    router.refresh();
  }

  async function submit() {
    setBusy("submit");
    setErrors({});
    // Save first, so a validation failure is about the numbers on screen.
    // Destructured rather than accessed as `draft.error`: the generated client types
    // `error` as `never` for operations with no declared error response, and a property
    // access on the narrowed branch is then a type error.
    const { error: draftError } = await api.PATCH("/api/v1/matches/{match_id}/scorecard", {
      params: path,
      body: body(),
    });
    if (draftError) {
      setBusy(null);
      setErrors(fieldErrors(draftError));
      return;
    }

    const { error } = await api.POST("/api/v1/matches/{match_id}/scorecard/submit", {
      params: path,
      body: {} as never,
    });
    setBusy(null);
    if (error) {
      setErrors(fieldErrors(error));
      return;
    }
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-6">
      {errors.teams && (
        <p role="alert" className="text-destructive text-sm">
          {errors.teams}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("finalScore")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end justify-center gap-6">
          {(
            [
              ["A", teamA, setTeamA],
              ["B", teamB, setTeamB],
            ] as const
          ).map(([side, value, set]) => {
            const team = teams.find((item) => item.side === side);
            return (
              <div key={side} className="flex flex-col items-center gap-2">
                <Label htmlFor={`score-${side}`} className="text-xs">
                  {team?.display_name ?? `Team ${side}`}
                </Label>
                <ScoreStepper
                  id={`score-${side}`}
                  label={team?.display_name ?? `Team ${side}`}
                  value={value}
                  onChange={set}
                />
              </div>
            );
          })}
        </CardContent>
      </Card>

      {definitions.length > 0 && players.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("playerStats")}</CardTitle>
            <p className="text-muted-foreground text-xs">{t("playerStatsHint")}</p>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {players.map((player) => (
              <div
                key={player.match_player_id}
                className="flex flex-col gap-2 rounded-lg border p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">{player.name}</span>
                  <Badge variant={player.side === "A" ? "default" : "secondary"}>
                    {player.teamName}
                  </Badge>
                </div>

                <div className="flex flex-wrap gap-x-4 gap-y-2">
                  {definitions.map((definition) => {
                    const value = stats[String(player.player_id)]?.[definition.key] ?? 0;
                    return (
                      <div key={definition.key} className="flex flex-col gap-1">
                        <Label
                          htmlFor={`${player.player_id}-${definition.key}`}
                          className={cn(
                            "text-xs font-normal",
                            errors[definition.key] && "text-destructive",
                          )}
                        >
                          {definition.label}
                        </Label>
                        <ScoreStepper
                          id={`${player.player_id}-${definition.key}`}
                          label={`${player.name} ${definition.label}`}
                          value={value}
                          size="sm"
                          min={Number(definition.min_value)}
                          max={
                            definition.max_value != null ? Number(definition.max_value) : undefined
                          }
                          onChange={(next) =>
                            setStat(String(player.player_id), definition.key, next)
                          }
                        />
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {Object.entries(errors)
        .filter(([field]) => field !== "teams")
        .map(([field, message]) => (
          <p key={field} role="alert" className="text-destructive text-sm">
            {message}
          </p>
        ))}

      <div className="flex flex-wrap items-center gap-3 border-t pt-4">
        {mode === "score" && (
          <Button variant="outline" size="sm" disabled={busy !== null} onClick={save}>
            {busy === "save" ? t("saving") : t("saveDraft")}
          </Button>
        )}
        <Button size="sm" disabled={busy !== null} onClick={mode === "resolve" ? resolve : submit}>
          {busy === "submit" ? t("submitting") : mode === "resolve" ? t("resolve") : t("submit")}
        </Button>
        {saved && (
          <span role="status" className="text-muted-foreground text-sm">
            {t("savedNote")}
          </span>
        )}
      </div>
      <p className="text-muted-foreground text-xs">
        {mode === "resolve" ? t("resolveHint") : t("submitHint")}
      </p>
    </div>
  );
}

/** Confirm or dispute, for the opposing captain. */
export function ScorecardDecision({ match }: { match: MatchDetail }) {
  const t = useTranslations("scorecardEditor");
  const router = useRouter();
  const api = useApiClient();

  const [busy, setBusy] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const path = { path: { match_id: match.id } };

  async function run(key: string, call: () => Promise<{ error?: unknown }>) {
    setBusy(key);
    setError(null);
    const { error: apiError } = await call();
    setBusy(null);
    if (apiError) {
      const messages = Object.values(fieldErrors(apiError));
      setError(messages[0] ?? t("failed"));
      return;
    }
    router.refresh();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{t("yourCall")}</CardTitle>
        <p className="text-muted-foreground text-xs">{t("yourCallHint")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {error && (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        )}

        <Button
          size="sm"
          className="self-start"
          disabled={busy !== null}
          onClick={() =>
            run("confirm", () =>
              api.POST("/api/v1/matches/{match_id}/scorecard/confirm", {
                params: path,
                body: {} as never,
              }),
            )
          }
        >
          {t("confirm")}
        </Button>

        <div className="flex flex-wrap items-end gap-2 border-t pt-3">
          <div className="flex min-w-48 flex-1 flex-col gap-1">
            <Label htmlFor="dispute-reason" className="text-xs">
              {t("disputeReason")}
            </Label>
            <Input
              id="dispute-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder={t("disputePlaceholder")}
              maxLength={300}
            />
          </div>
          <Button
            size="sm"
            variant="destructive"
            disabled={busy !== null || !reason.trim()}
            onClick={() =>
              run("dispute", () =>
                api.POST("/api/v1/matches/{match_id}/scorecard/dispute", {
                  params: path,
                  body: { reason } as never,
                }),
              )
            }
          >
            {t("dispute")}
          </Button>
        </div>
        <p className="text-muted-foreground text-xs">{t("disputeHint")}</p>
      </CardContent>
    </Card>
  );
}
