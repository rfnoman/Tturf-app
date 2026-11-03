"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { cn } from "cn";

import type { MatchDetail, MatchTeam } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Side = "A" | "B";

/**
 * Split the roster into two sides and name the captains.
 *
 * Tap-to-move rather than drag-and-drop: this is used on a phone, where dragging across
 * two columns is fiddly and inaccessible, and a tap says the same thing.
 */
export function TeamBuilder({ match, teams }: { match: MatchDetail; teams: MatchTeam[] }) {
  const t = useTranslations("teamBuilder");
  const router = useRouter();
  const api = useApiClient();

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Where the server has people, and the moves made since. Kept apart deliberately:
  // seeding one state object from props would freeze the first render's teams, so
  // auto-balance would change the database and nothing on screen.
  const saved = useMemo(() => {
    const sides: Record<string, Side> = {};
    for (const team of teams) {
      for (const player of team.players) {
        sides[String(player.match_player_id)] = team.side as Side;
      }
    }
    return sides;
  }, [teams]);

  const [pending, setPending] = useState<Record<string, Side | null>>({});
  const assignments: Record<string, Side | null> = { ...saved, ...pending };

  const path = { path: { match_id: match.id } };
  const unassigned = match.roster.filter((entry) => !assignments[entry.id]);

  async function run(key: string, call: () => Promise<{ error?: unknown }>) {
    setBusy(key);
    setError(null);
    const { error: apiError } = await call();
    setBusy(null);
    if (apiError) {
      setError(t("failed"));
      return false;
    }
    // Server state is the truth again, so local moves are dropped rather than
    // replayed over whatever came back.
    setPending({});
    router.refresh();
    return true;
  }

  function move(entryId: string, side: Side | null) {
    setPending((current) => ({ ...current, [entryId]: side }));
  }

  async function save() {
    const payload = Object.fromEntries(
      Object.entries(assignments).filter(([, side]) => side !== null),
    );
    await run("save", () =>
      api.POST("/api/v1/matches/{match_id}/teams", {
        params: path,
        body: { assignments: payload } as never,
      }),
    );
  }

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="text-sm">{t("heading")}</CardTitle>
          <p className="text-muted-foreground mt-1 text-xs">{t("body")}</p>
        </div>
        <Button
          size="sm"
          variant="outline"
          disabled={busy !== null}
          onClick={() =>
            run("balance", () =>
              api.POST("/api/v1/matches/{match_id}/teams/auto-balance", {
                params: path,
                body: {} as never,
              }),
            )
          }
        >
          {t("autoBalance")}
        </Button>
      </CardHeader>

      <CardContent className="flex flex-col gap-4">
        {error && (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        )}

        {unassigned.length > 0 && (
          <div className="flex flex-col gap-2">
            <h3 className="text-muted-foreground text-xs tracking-wide uppercase">
              {t("unassigned")}
            </h3>
            <ul className="flex flex-wrap gap-2">
              {unassigned.map((entry) => (
                <li
                  key={entry.id}
                  className="flex items-center gap-1.5 rounded-lg border px-2 py-1 text-sm"
                >
                  <span className="truncate">{entry.name}</span>
                  <Button size="xs" variant="ghost" onClick={() => move(entry.id, "A")}>
                    → A
                  </Button>
                  <Button size="xs" variant="ghost" onClick={() => move(entry.id, "B")}>
                    → B
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          {(["A", "B"] as const).map((side) => {
            const team = teams.find((item) => item.side === side);
            const members = match.roster.filter((entry) => assignments[entry.id] === side);

            return (
              <div key={side} className="flex flex-col gap-2 rounded-lg border p-3">
                <h3 className="text-sm font-semibold">
                  {team?.display_name ?? `Team ${side}`}
                  <span className="text-muted-foreground ml-1.5 text-xs font-normal">
                    {t("count", { count: members.length })}
                  </span>
                </h3>

                {members.length === 0 ? (
                  <p className="text-muted-foreground text-xs">{t("emptyTeam")}</p>
                ) : (
                  <ul className="flex flex-col gap-1">
                    {members.map((entry) => {
                      const isCaptain =
                        team?.players.some(
                          (player) =>
                            String(player.match_player_id) === entry.id && player.is_captain,
                        ) ?? false;
                      return (
                        <li
                          key={entry.id}
                          className={cn(
                            "flex items-center justify-between gap-2 rounded px-2 py-1 text-sm",
                            isCaptain && "bg-muted/60",
                          )}
                        >
                          <span className="truncate">
                            {entry.name}
                            {isCaptain && <span className="text-muted-foreground"> (C)</span>}
                          </span>
                          <span className="flex shrink-0 gap-1">
                            {!isCaptain && entry.profile_id && (
                              <Button
                                size="xs"
                                variant="ghost"
                                disabled={busy !== null}
                                onClick={() =>
                                  run(entry.id, () =>
                                    api.POST("/api/v1/matches/{match_id}/teams/captain", {
                                      params: path,
                                      body: {
                                        side,
                                        player_id: entry.profile_id,
                                      } as never,
                                    }),
                                  )
                                }
                              >
                                {t("makeCaptain")}
                              </Button>
                            )}
                            <Button
                              size="xs"
                              variant="ghost"
                              onClick={() => move(entry.id, side === "A" ? "B" : "A")}
                            >
                              {t("swap")}
                            </Button>
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            );
          })}
        </div>

        <Button size="sm" className="self-start" disabled={busy !== null} onClick={save}>
          {busy === "save" ? t("saving") : t("saveTeams")}
        </Button>
        <p className="text-muted-foreground text-xs">{t("captainHint")}</p>
      </CardContent>
    </Card>
  );
}
