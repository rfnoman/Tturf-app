"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";

import type { PlayerAvailability, Sport } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** Dhaka-local `YYYY-MM-DDTHH:mm` for a datetime-local input. */
function dhakaLocal(offsetHours: number): string {
  const moment = new Date(Date.now() + offsetHours * 3_600_000);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Dhaka",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(moment);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "00";
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
}

/**
 * "I'm free on Friday evening in Mirpur" (DOMAIN §3).
 *
 * The window is entered in Dhaka time and sent as an instant: a player thinking "Friday
 * 7pm" means 7pm where they are standing, not UTC.
 */
export function AvailabilityForm({
  sports,
  windows,
}: {
  sports: Sport[];
  windows: PlayerAvailability[];
}) {
  const t = useTranslations("availability");
  const router = useRouter();
  const api = useApiClient();

  const [open, setOpen] = useState(windows.length === 0);
  const [sport, setSport] = useState("");
  const [from, setFrom] = useState(() => dhakaLocal(2));
  const [until, setUntil] = useState(() => dhakaLocal(5));
  const [area, setArea] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    // The input has no zone; Dhaka is UTC+6 all year, so the offset is a constant.
    const { error: apiError } = await api.POST("/api/v1/me/availability", {
      body: {
        sport: sport || null,
        starts_at: `${from}:00+06:00`,
        ends_at: `${until}:00+06:00`,
        area,
      } as never,
    });
    setBusy(false);
    if (apiError) {
      setError(t("failed"));
      return;
    }
    setOpen(false);
    router.refresh();
  }

  async function withdraw(id: string) {
    setBusy(true);
    await api.DELETE("/api/v1/me/availability/{availability_id}", {
      params: { path: { availability_id: id } },
    });
    setBusy(false);
    router.refresh();
  }

  return (
    <Card data-testid="availability">
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="text-sm">{t("heading")}</CardTitle>
          <p className="text-muted-foreground mt-1 text-xs">{t("body")}</p>
        </div>
        <Button size="sm" variant="outline" onClick={() => setOpen((value) => !value)}>
          {open ? t("close") : t("imFree")}
        </Button>
      </CardHeader>

      <CardContent className="flex flex-col gap-4">
        {windows.length > 0 && (
          <ul className="flex flex-col gap-1.5 text-sm">
            {windows.map((window) => (
              <li key={String(window.id)} className="flex items-center justify-between gap-2">
                <span className="truncate">
                  {new Intl.DateTimeFormat("en-GB", {
                    timeZone: "Asia/Dhaka",
                    weekday: "short",
                    day: "numeric",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                  }).format(new Date(window.starts_at))}
                  {window.area && <span className="text-muted-foreground"> · {window.area}</span>}
                  {window.sport_name && (
                    <span className="text-muted-foreground"> · {window.sport_name}</span>
                  )}
                </span>
                <Button
                  size="xs"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => withdraw(String(window.id))}
                >
                  {t("withdraw")}
                </Button>
              </li>
            ))}
          </ul>
        )}

        {open && (
          <div className="flex flex-col gap-3 border-t pt-4">
            {error && (
              <p role="alert" className="text-destructive text-sm">
                {error}
              </p>
            )}
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="free-from">{t("from")}</Label>
                <Input
                  id="free-from"
                  type="datetime-local"
                  value={from}
                  onChange={(event) => setFrom(event.target.value)}
                  className="w-52"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="free-until">{t("until")}</Label>
                <Input
                  id="free-until"
                  type="datetime-local"
                  value={until}
                  onChange={(event) => setUntil(event.target.value)}
                  className="w-52"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="free-area">{t("area")}</Label>
                <Input
                  id="free-area"
                  value={area}
                  onChange={(event) => setArea(event.target.value)}
                  placeholder={t("areaPlaceholder")}
                  className="w-36"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="free-sport">{t("sport")}</Label>
                <select
                  id="free-sport"
                  value={sport}
                  onChange={(event) => setSport(event.target.value)}
                  className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
                >
                  <option value="">{t("anySport")}</option>
                  {sports.map((option) => (
                    <option key={option.slug} value={option.slug}>
                      {option.name}
                    </option>
                  ))}
                </select>
              </div>
              <Button size="sm" disabled={busy} onClick={save}>
                {busy ? t("saving") : t("save")}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
