"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { cn } from "cn";

import type { Sport, Turf } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TurfMap, type MapMarker } from "@/components/turf/turf-map";

type View = "list" | "map";

/**
 * Turf discovery: filters, a list/map toggle, and "near me".
 *
 * Client-side because all three controls are interactive and the result set is small
 * enough to refetch on every change. Geolocation is strictly opt-in — the browser
 * prompt only appears when the player presses the button, and declining leaves them
 * with the alphabetical list rather than an error.
 */
export function TurfDiscovery({
  initialTurfs,
  sports,
  areas,
}: {
  initialTurfs: Turf[];
  sports: Sport[];
  areas: string[];
}) {
  const t = useTranslations("turfs");
  const api = useApiClient();

  const [view, setView] = useState<View>("list");
  const [query, setQuery] = useState("");
  const [sport, setSport] = useState("");
  const [area, setArea] = useState("");
  const [near, setNear] = useState<{ lat: number; lng: number } | null>(null);
  const [locating, setLocating] = useState(false);
  const [locationError, setLocationError] = useState<string | null>(null);
  // Results carry the filter they answer, so `loading` is derived rather than set and
  // the list never shows one filter's turfs under another filter's heading.
  const [loaded, setLoaded] = useState<{ key: string; turfs: Turf[] }>({
    key: "||",
    turfs: initialTurfs,
  });

  const key = `${query}|${sport}|${area}|${near ? `${near.lat},${near.lng}` : ""}`;
  const loading = loaded.key !== key;
  // The previous results stay on screen while the next request is in flight; the
  // "searching" line tells the reader they are about to change.
  const turfs = loaded.turfs;

  useEffect(() => {
    let cancelled = false;

    // Debounced, so typing does not fire a request per keystroke.
    const timer = setTimeout(async () => {
      const { data } = await api.GET("/api/v1/turfs", {
        params: {
          query: {
            ...(query ? { q: query } : {}),
            ...(sport ? { sport } : {}),
            ...(area ? { area } : {}),
            ...(near ? { near: `${near.lat},${near.lng}` } : {}),
          },
        },
      });
      if (!cancelled) {
        setLoaded({
          key: `${query}|${sport}|${area}|${near ? `${near.lat},${near.lng}` : ""}`,
          turfs: data?.results ?? [],
        });
      }
    }, 250);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [api, query, sport, area, near]);

  function locate() {
    if (!navigator.geolocation) {
      setLocationError(t("geolocationUnsupported"));
      return;
    }
    setLocating(true);
    setLocationError(null);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setNear({ lat: position.coords.latitude, lng: position.coords.longitude });
        setLocating(false);
        setView("map");
      },
      () => {
        // Declining is a normal outcome, not an error state to dwell on.
        setLocationError(t("geolocationDenied"));
        setLocating(false);
      },
      { timeout: 10_000 },
    );
  }

  const markers = useMemo<MapMarker[]>(
    () =>
      turfs
        .filter((turf) => turf.latitude != null && turf.longitude != null)
        .map((turf) => ({
          id: turf.id,
          latitude: turf.latitude!,
          longitude: turf.longitude!,
          label: turf.name,
          sublabel: turf.price_from ? t("priceFrom", { price: turf.price_from }) : turf.area,
          href: `/turfs/${turf.slug}`,
        })),
    [turfs, t],
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("searchPlaceholder")}
            aria-label={t("searchPlaceholder")}
            className="min-w-48 flex-1"
          />
          <Button
            type="button"
            variant={near ? "default" : "outline"}
            size="sm"
            onClick={near ? () => setNear(null) : locate}
            disabled={locating}
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
                {t(`view${option === "list" ? "List" : "Map"}`)}
              </Button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <select
            aria-label={t("filterSport")}
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
          <select
            aria-label={t("filterArea")}
            value={area}
            onChange={(event) => setArea(event.target.value)}
            className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
          >
            <option value="">{t("allAreas")}</option>
            {areas.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          {(query || sport || area || near) && (
            <Button
              type="button"
              size="xs"
              variant="ghost"
              onClick={() => {
                setQuery("");
                setSport("");
                setArea("");
                setNear(null);
              }}
            >
              {t("clearFilters")}
            </Button>
          )}
        </div>

        {locationError && (
          <p role="status" className="text-muted-foreground text-xs">
            {locationError}
          </p>
        )}
      </div>

      <p className="text-muted-foreground text-xs" aria-live="polite">
        {loading ? t("searching") : t("resultCount", { count: turfs.length })}
      </p>

      {view === "map" ? (
        <TurfMap
          markers={markers}
          center={near ? [near.lat, near.lng] : undefined}
          zoom={near ? 14 : 12}
          className="h-[28rem] w-full rounded-xl border"
        />
      ) : turfs.length === 0 ? (
        <p className="text-muted-foreground py-8 text-center text-sm">{t("noResults")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {turfs.map((turf) => (
            <li key={turf.id}>
              <Link
                href={`/turfs/${turf.slug}`}
                className={cn(
                  "bg-card hover:bg-muted/40 flex flex-col overflow-hidden rounded-xl border",
                  "shadow-sm transition-colors sm:flex-row",
                )}
              >
                <div
                  aria-hidden
                  className="bg-muted text-muted-foreground flex h-24 w-full shrink-0 items-center justify-center text-3xl sm:h-auto sm:w-32"
                >
                  {turf.sports?.[0]?.icon ?? "🏟️"}
                </div>
                <div className="flex min-w-0 flex-1 flex-col gap-1 p-4">
                  <div className="flex items-baseline justify-between gap-2">
                    <h2 className="truncate text-base font-semibold">{turf.name}</h2>
                    {turf.distance_km != null && (
                      <span className="text-muted-foreground shrink-0 text-xs">
                        {t("kmAway", { km: turf.distance_km })}
                      </span>
                    )}
                  </div>
                  <p className="text-muted-foreground truncate text-xs">{turf.area}</p>
                  <p className="text-xs">
                    {turf.sports?.map((s) => s.name).join(" · ")}
                    {turf.price_from && ` — ${t("priceFrom", { price: turf.price_from })}`}
                  </p>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
