"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import type { RosterPlayer } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const REASONS = ["abusive", "left_early", "no_show", "unsafe_play", "other"] as const;

/**
 * Reporting what happened in a match (DOMAIN §8).
 *
 * Deliberately not a one-tap action: a report goes to a person to review, and the
 * details box is what makes that review possible. Nothing it says affects the reported
 * player until an admin upholds it, and the copy says so.
 */
export function ConductReportForm({
  matchId,
  players,
}: {
  matchId: string;
  /** Everyone on the roster except the reader — the API refuses a self-report. */
  players: RosterPlayer[];
}) {
  const t = useTranslations("conduct");
  const api = useApiClient();

  const [open, setOpen] = useState(false);
  const [playerId, setPlayerId] = useState(String(players[0]?.profile_id ?? ""));
  const [reason, setReason] = useState<(typeof REASONS)[number]>("abusive");
  const [details, setDetails] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (players.length === 0) return null;

  async function submit() {
    setBusy(true);
    setError(null);
    const { error: apiError } = await api.POST("/api/v1/matches/{match_id}/conduct-reports", {
      params: { path: { match_id: matchId } },
      body: { player_id: playerId, reason, details } as never,
    });
    setBusy(false);
    if (apiError) {
      setError(t("failed"));
      return;
    }
    setDone(true);
  }

  if (done) {
    return (
      <p role="status" className="text-muted-foreground text-sm">
        {t("sent")}
      </p>
    );
  }

  if (!open) {
    return (
      <Button
        size="sm"
        variant="ghost"
        className="self-start"
        onClick={() => setOpen(true)}
        data-testid="report-player"
      >
        {t("open")}
      </Button>
    );
  }

  return (
    <Card data-testid="conduct-form">
      <CardHeader>
        <CardTitle className="text-sm">{t("heading")}</CardTitle>
        <p className="text-muted-foreground text-xs">{t("hint")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {error && (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        )}

        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="report-player">{t("who")}</Label>
            <select
              id="report-player"
              value={playerId}
              onChange={(event) => setPlayerId(event.target.value)}
              className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
            >
              {players.map((entry) => (
                <option key={entry.id} value={String(entry.profile_id)}>
                  {entry.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="report-reason">{t("what")}</Label>
            <select
              id="report-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value as (typeof REASONS)[number])}
              className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
            >
              {REASONS.map((value) => (
                <option key={value} value={value}>
                  {t("reason", { reason: value })}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="report-details">{t("details")}</Label>
          <Input
            id="report-details"
            value={details}
            onChange={(event) => setDetails(event.target.value)}
            placeholder={t("detailsPlaceholder")}
            maxLength={1000}
          />
        </div>

        <div className="flex items-center gap-3">
          <Button size="sm" disabled={busy || !playerId} onClick={submit}>
            {busy ? t("sending") : t("send")}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
            {t("cancel")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
