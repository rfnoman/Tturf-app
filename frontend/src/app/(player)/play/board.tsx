"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { cn } from "cn";

import type { MatchSummary, Sport } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TurfMap, type MapMarker } from "@/components/turf/turf-map";
import { ratingTone } from "@/components/player/rating";

type View = "list" | "map";

/** Dhaka-local YYYY-MM-DD. */
function dhakaDate(offsetDays = 0): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Dhaka" }).format(
    new Date(Date.now() + offsetDays * 86_400_000),
  );
}

/**
 * The match board (DOMAIN §6).
 *
 * Filters are the whole point of this screen — a player is looking for a game at a
 * level, in an area, at a time they can make — so they drive one debounced request and
 * the results carry the key they answer, the same pattern as turf discovery.
 */
export function MatchBoard({
  initialMatches,
  sports,
}: {
  initialMatches: MatchSummary[];
  sports: Sport[];
}) {
  const t = useTranslations("board");
  const api = useApiClient();

  const [view, setView] = useState<View>("list");
  const [sport, setSport] = useState("");
  const [date, setDate] = useState("");
  const [timeFrom, setTimeFrom] = useState("");
  const [timeTo, setTimeTo] = useState("");
  const [neededMin, setNeededMin] = useState("");
  const [ratingMin, setRatingMin] = useState("");
  const [ratingMax, setRatingMax] = useState("");
  const [near, setNear] = useState<{ lat: number; lng: number } | null>(null);
  const [locating, setLocating] = useState(false);
  const [loaded, setLoaded] = useState<{ key: string; matches: MatchSummary[] }>({
    key: "",
    matches: initialMatches,
  });

  const query = useMemo(
    () => ({
      ...(sport ? { sport } : {}),
      ...(date ? { date } : {}),
      ...(timeFrom ? { time_from: timeFrom } : {}),
      ...(timeTo ? { time_to: timeTo } : {}),
      ...(neededMin ? { needed_min: Number(neededMin) } : {}),
      ...(ratingMin ? { rating_min: Number(ratingMin) } : {}),
      ...(ratingMax ? { rating_max: Number(ratingMax) } : {}),
      ...(near ? { near: `${near.lat},${near.lng}` } : {}),
    }),
    [sport, date, timeFrom, timeTo, neededMin, ratingMin, ratingMax, near],
  );

  const key = JSON.stringify(query);
  const loading = loaded.key !== key;
  const matches = loaded.matches;

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      const { data } = await api.GET("/api/v1/matches/board", { params: { query } });
      if (!cancelled) setLoaded({ key: JSON.stringify(query), matches: data ?? [] });
    }, 250);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [api, query, key]);

  function locate() {
    if (!navigator.geolocation) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setNear({ lat: position.coords.latitude, lng: position.coords.longitude });
        setLocating(false);
      },
      () => setLocating(false),
      { timeout: 10_000 },
    );
  }

  const markers = useMemo<MapMarker[]>(() => [], []);
  const hasFilters = Boolean(
    sport || date || timeFrom || timeTo || neededMin || ratingMin || ratingMax || near,
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex flex-col gap-1">
            <Label htmlFor="board-sport" className="text-xs">
              {t("sport")}
            </Label>
            <select
              id="board-sport"
              value={sport}
              onChange={(event) => setSport(event.target.value)}
              className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
            >
              <option value="">{t("allSports")}</option>
              {sports.map((item) => (
                <option key={item.slug} value={item.slug}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="board-date" className="text-xs">
              {t("date")}
            </Label>
            <Input
              id="board-date"
              type="date"
              min={dhakaDate()}
              value={date}
              onChange={(event) => setDate(event.target.value)}
              className="w-36"
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="board-from" className="text-xs">
              {t("from")}
            </Label>
            <Input
              id="board-from"
              type="time"
              value={timeFrom}
              onChange={(event) => setTimeFrom(event.target.value)}
              className="w-28"
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="board-to" className="text-xs">
              {t("to")}
            </Label>
            <Input
              id="board-to"
              type="time"
              value={timeTo}
              onChange={(event) => setTimeTo(event.target.value)}
              className="w-28"
            />
          </div>
          <Button
            type="button"
            variant={near ? "default" : "outline"}
            size="sm"
            disabled={locating}
            onClick={near ? () => setNear(null) : locate}
          >
            {locating ? t("locating") : near ? t("nearMeOn") : t("nearMe")}
          </Button>
          <div className="flex rounded-lg border p-0.5" role="group" aria-label={t("view")}>
            {(["list", "map"] as const).map((option) => (
              <Button
                key={option}
                type="button"
                size="xs"
                variant={view === option ? "secondary" : "ghost"}
                onClick={() => setView(option)}
              >
                {t(option === "list" ? "viewList" : "viewMap")}
              </Button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-2">
          <div className="flex flex-col gap-1">
            <Label htmlFor="board-needed" className="text-xs">
              {t("neededMin")}
            </Label>
            <Input
              id="board-needed"
              type="number"
              min={1}
              max={22}
              value={neededMin}
              onChange={(event) => setNeededMin(event.target.value)}
              className="w-24"
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="board-rating-min" className="text-xs">
              {t("ratingMin")}
            </Label>
            <Input
              id="board-rating-min"
              type="number"
              min={1}
              max={99}
              value={ratingMin}
              onChange={(event) => setRatingMin(event.target.value)}
              className="w-24"
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="board-rating-max" className="text-xs">
              {t("ratingMax")}
            </Label>
            <Input
              id="board-rating-max"
              type="number"
              min={1}
              max={99}
              value={ratingMax}
              onChange={(event) => setRatingMax(event.target.value)}
              className="w-24"
            />
          </div>
          {hasFilters && (
            <Button
              type="button"
              size="xs"
              variant="ghost"
              onClick={() => {
                setSport("");
                setDate("");
                setTimeFrom("");
                setTimeTo("");
                setNeededMin("");
                setRatingMin("");
                setRatingMax("");
                setNear(null);
              }}
            >
              {t("clearFilters")}
            </Button>
          )}
        </div>
      </div>

      <p className="text-muted-foreground text-xs" aria-live="polite">
        {loading ? t("searching") : t("resultCount", { count: matches.length })}
      </p>

      {view === "map" ? (
        <BoardMap matches={matches} center={near} fallback={markers} />
      ) : matches.length === 0 ? (
        <p className="text-muted-foreground py-8 text-center text-sm">{t("empty")}</p>
      ) : (
        <ul data-testid="match-board" className="flex flex-col gap-3">
          {matches.map((match) => (
            <li key={match.id}>
              <BoardRow match={match} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** A board row. Kept in this file because it reads live, client-filtered data. */
function BoardRow({ match }: { match: MatchSummary }) {
  const t = useTranslations("board");
  const when = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Dhaka",
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(match.starts_at));

  return (
    <Link
      href={`/matches/${match.id}`}
      className="bg-card hover:bg-muted/40 flex flex-col gap-2 rounded-xl border p-4 shadow-sm transition-colors"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-base font-semibold">
            <span aria-hidden className="mr-1.5">
              {match.sport.icon}
            </span>
            {match.turf_name}
          </h2>
          <p className="text-muted-foreground truncate text-xs">
            {match.ground_name} · {match.area}
            {match.distance_km != null && ` · ${t("kmAway", { km: match.distance_km })}`}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-sm font-medium">{when}</p>
          <p className="text-muted-foreground text-xs">{match.sport_format.name}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex flex-wrap items-center gap-1.5">
          <span className="bg-primary text-primary-foreground rounded-full px-2 py-0.5 text-xs font-medium">
            {t("needed", { count: match.needed })}
          </span>
          {match.squad && (
            <span className="bg-secondary rounded-full px-2 py-0.5 text-xs">
              {match.squad.name}
            </span>
          )}
          <span className="text-muted-foreground text-xs">
            {t("rosterOf", { count: match.roster_count, capacity: match.capacity })}
          </span>
        </span>
        <span className="flex items-center gap-3 text-xs">
          {match.average_rating != null ? (
            <span className={cn("font-medium", ratingTone(match.average_rating))}>
              {t("avgRating", { rating: match.average_rating })}
            </span>
          ) : (
            <span className="text-muted-foreground">{t("unrated")}</span>
          )}
          <span className="font-mono tabular-nums">৳{match.price}</span>
        </span>
      </div>
    </Link>
  );
}

function BoardMap({
  matches,
  center,
}: {
  matches: MatchSummary[];
  center: { lat: number; lng: number } | null;
  fallback: MapMarker[];
}) {
  const t = useTranslations("board");
  // The board returns turf names but not coordinates, so the map centres on the player
  // and the rows carry the distance. A richer map arrives with Phase 06's search.
  return (
    <div className="flex flex-col gap-2">
      <TurfMap
        center={center ? [center.lat, center.lng] : undefined}
        zoom={center ? 13 : 11}
        className="h-80 w-full rounded-xl border"
      />
      <p className="text-muted-foreground text-xs">{t("mapHint", { count: matches.length })}</p>
    </div>
  );
}
