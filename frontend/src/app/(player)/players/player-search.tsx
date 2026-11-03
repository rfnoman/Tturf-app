"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import type { MatchSummary, PlayerSearchResult, Sport, SquadSummary } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Filters = {
  sport: string;
  area: string;
  rating_min: string;
  rating_max: string;
  reliability_min: string;
  q: string;
  free_only: boolean;
};

const EMPTY: Filters = {
  sport: "",
  area: "",
  rating_min: "",
  rating_max: "",
  reliability_min: "",
  q: "",
  free_only: false,
};

/** Search, then invite — through the Phase 04 chain, which is the only way in (D1). */
export function PlayerSearch({
  sports,
  matches,
  squads,
}: {
  sports: Sport[];
  matches: MatchSummary[];
  squads: SquadSummary[];
}) {
  const t = useTranslations("playerSearch");
  const api = useApiClient();

  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [results, setResults] = useState<PlayerSearchResult[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    // Debounced: typing a name should not fire a request per keystroke.
    const timer = setTimeout(async () => {
      const query: Record<string, string> = {};
      if (filters.sport) query.sport = filters.sport;
      if (filters.area) query.area = filters.area;
      if (filters.rating_min) query.rating_min = filters.rating_min;
      if (filters.rating_max) query.rating_max = filters.rating_max;
      if (filters.reliability_min) query.reliability_min = filters.reliability_min;
      if (filters.q) query.q = filters.q;
      if (filters.free_only) {
        query.available_from = new Date().toISOString();
        query.available_until = new Date(Date.now() + 7 * 86_400_000).toISOString();
      }

      const { data } = await api.GET("/api/v1/players/search", {
        params: { query: query as never },
      });
      if (!cancelled) {
        setResults(data?.results ?? []);
        setLoading(false);
      }
    }, 300);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [api, filters]);

  function set<K extends keyof Filters>(key: K, value: Filters[K]) {
    setLoading(true);
    setFilters((current) => ({ ...current, [key]: value }));
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="search-name">{t("name")}</Label>
          <Input
            id="search-name"
            value={filters.q}
            onChange={(event) => set("q", event.target.value)}
            placeholder={t("namePlaceholder")}
            className="w-44"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="search-sport">{t("sport")}</Label>
          <select
            id="search-sport"
            value={filters.sport}
            onChange={(event) => set("sport", event.target.value)}
            className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
          >
            <option value="">{t("anySport")}</option>
            {sports.map((sport) => (
              <option key={sport.slug} value={sport.slug}>
                {sport.icon} {sport.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="search-area">{t("area")}</Label>
          <Input
            id="search-area"
            value={filters.area}
            onChange={(event) => set("area", event.target.value)}
            placeholder={t("areaPlaceholder")}
            className="w-36"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="search-rating-min">{t("ratingMin")}</Label>
          <Input
            id="search-rating-min"
            type="number"
            min={1}
            max={99}
            value={filters.rating_min}
            onChange={(event) => set("rating_min", event.target.value)}
            className="w-24"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="search-reliability">{t("reliabilityMin")}</Label>
          <Input
            id="search-reliability"
            type="number"
            min={0}
            max={100}
            value={filters.reliability_min}
            onChange={(event) => set("reliability_min", event.target.value)}
            className="w-24"
          />
        </div>
        <Button
          type="button"
          size="sm"
          variant={filters.free_only ? "default" : "outline"}
          aria-pressed={filters.free_only}
          onClick={() => set("free_only", !filters.free_only)}
        >
          {t("freeThisWeek")}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => setFilters(EMPTY)}>
          {t("clear")}
        </Button>
      </div>

      {loading ? (
        <p className="text-muted-foreground text-sm">{t("searching")}</p>
      ) : results.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("nobody")}</p>
      ) : (
        <ul
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
          data-testid="player-search-results"
        >
          {results.map((player) => (
            <li key={String(player.id)} className="flex flex-col gap-2">
              <Link href={`/players/${player.id}`} className="rounded-xl">
                <ResultCard player={player} />
              </Link>
              {player.availability.length > 0 && (
                <p className="text-muted-foreground text-xs">
                  {t("free", {
                    when: new Intl.DateTimeFormat("en-GB", {
                      timeZone: "Asia/Dhaka",
                      weekday: "short",
                      hour: "2-digit",
                      minute: "2-digit",
                    }).format(new Date(player.availability[0].starts_at)),
                    area: player.availability[0].area || player.area || "",
                  })}
                </p>
              )}
              <InviteActions player={player} matches={matches} squads={squads} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * A compact result tile.
 *
 * Its own component rather than the Phase 01 card: that one is a server component with
 * per-sport bars, and this list is filtered in the browser.
 */
function ResultCard({ player }: { player: PlayerSearchResult }) {
  const t = useTranslations("playerSearch");
  const best = [...player.sport_cards].sort((a, b) => (b.overall ?? 0) - (a.overall ?? 0))[0];

  return (
    <div className="bg-card hover:border-primary/40 flex items-center gap-3 rounded-xl border p-3 shadow-sm transition-colors">
      {player.photo_url ? (
        // eslint-disable-next-line @next/next/no-img-element -- arbitrary Clerk/CDN hosts
        <img
          src={player.photo_url}
          alt=""
          className="bg-muted size-11 shrink-0 rounded-full object-cover"
        />
      ) : (
        <span
          aria-hidden
          className="bg-muted text-muted-foreground flex size-11 shrink-0 items-center justify-center rounded-full font-semibold"
        >
          {player.name.slice(0, 1).toUpperCase()}
        </span>
      )}

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{player.name}</p>
        <p className="text-muted-foreground truncate text-xs">{player.area || t("noArea")}</p>
      </div>

      <div className="flex shrink-0 flex-col items-end gap-1">
        {best?.overall != null && (
          <span className="font-mono text-lg font-bold tabular-nums">{best.overall}</span>
        )}
        <Badge variant="secondary" className="text-[10px]">
          {t("reliability", { score: player.reliability_score })}
        </Badge>
      </div>
    </div>
  );
}

/** Invite to one of my matches, or to a squad I lead. */
function InviteActions({
  player,
  matches,
  squads,
}: {
  player: PlayerSearchResult;
  matches: MatchSummary[];
  squads: SquadSummary[];
}) {
  const t = useTranslations("playerSearch");
  const api = useApiClient();

  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [matchId, setMatchId] = useState(matches[0] ? String(matches[0].id) : "");
  const [squadSlug, setSquadSlug] = useState(squads[0]?.slug ?? "");

  async function inviteToMatch() {
    if (!matchId) return;
    setBusy(true);
    setError(null);
    const { error: apiError } = await api.POST("/api/v1/matches/{id}/invite", {
      params: { path: { id: matchId } },
      body: { player_id: player.id } as never,
    });
    setBusy(false);
    if (apiError) {
      setError(t("inviteFailed"));
      return;
    }
    setDone(t("invitedToMatch"));
  }

  async function inviteToSquad() {
    if (!squadSlug) return;
    setBusy(true);
    setError(null);
    const { error: apiError } = await api.POST("/api/v1/squads/{slug}/invite", {
      params: { path: { slug: squadSlug } },
      body: { player_id: player.id } as never,
    });
    setBusy(false);
    if (apiError) {
      setError(t("inviteFailed"));
      return;
    }
    setDone(t("invitedToSquad"));
  }

  if (done) {
    return (
      <p role="status" className="text-muted-foreground text-xs">
        {done}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      {error && (
        <p role="alert" className="text-destructive text-xs">
          {error}
        </p>
      )}
      {matches.length > 0 && (
        <div className="flex items-center gap-1.5">
          <select
            aria-label={t("pickMatch")}
            value={matchId}
            onChange={(event) => setMatchId(event.target.value)}
            className="border-input bg-background h-7 min-w-0 flex-1 rounded-lg border px-1.5 text-xs"
          >
            {matches.map((match) => (
              <option key={String(match.id)} value={String(match.id)}>
                {match.sport.name} · {match.turf_name}
              </option>
            ))}
          </select>
          <Button size="xs" disabled={busy} onClick={inviteToMatch}>
            {t("inviteToMatch")}
          </Button>
        </div>
      )}
      {squads.length > 0 && (
        <div className="flex items-center gap-1.5">
          <select
            aria-label={t("pickSquad")}
            value={squadSlug}
            onChange={(event) => setSquadSlug(event.target.value)}
            className="border-input bg-background h-7 min-w-0 flex-1 rounded-lg border px-1.5 text-xs"
          >
            {squads.map((squad) => (
              <option key={squad.slug} value={squad.slug}>
                {squad.name}
              </option>
            ))}
          </select>
          <Button size="xs" variant="outline" disabled={busy} onClick={inviteToSquad}>
            {t("inviteToSquad")}
          </Button>
        </div>
      )}
    </div>
  );
}
