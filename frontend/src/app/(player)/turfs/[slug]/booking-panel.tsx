"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import type { Ground, Slot, SquadSummary } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SlotGrid } from "@/components/turf/slot-grid";

/** Dhaka-local YYYY-MM-DD, which is what the availability endpoint expects. */
function dhakaDate(offsetDays = 0): string {
  const now = new Date(Date.now() + offsetDays * 86_400_000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Dhaka" }).format(now);
}

/**
 * Ground picker, date picker, slot grid, and the booking review step.
 *
 * Selecting a slot opens a review panel rather than booking straight away: the player
 * needs to see the price, the cancellation policy and that payment is cash at the turf
 * before they commit. A **409** from the API is the expected outcome of two players
 * pressing Book at the same moment, so it is handled as "pick another slot" rather than
 * as an error.
 */
export function BookingPanel({
  grounds,
  horizonDays,
  cancellationFreeHours,
  squads,
}: {
  grounds: Ground[];
  horizonDays: number;
  cancellationFreeHours: number;
  squads: SquadSummary[];
}) {
  const t = useTranslations("turfs");
  const api = useApiClient();
  const router = useRouter();

  const [groundId, setGroundId] = useState(grounds[0]?.id ?? "");
  const [date, setDate] = useState(dhakaDate());
  const [selected, setSelected] = useState<string>();
  // Slots are stored with the query they answer. `loading` is then derived rather than
  // set — which keeps setState out of the effect body and, more usefully, means the
  // previous ground's slots are never shown under the new ground's heading.
  const [loaded, setLoaded] = useState<{ key: string; slots: Slot[] }>();
  const [formatId, setFormatId] = useState<string>();
  const [mode, setMode] = useState<"individual" | "group">("individual");
  const [squadId, setSquadId] = useState(squads[0]?.id ?? "");
  const [visibility, setVisibility] = useState<"public" | "private">("public");
  const [notes, setNotes] = useState("");
  const [booking, setBooking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const key = `${groundId}|${date}`;
  const loading = loaded?.key !== key;
  const slots = loaded?.key === key ? loaded.slots : [];

  useEffect(() => {
    if (!groundId) return;
    let cancelled = false;

    (async () => {
      const { data } = await api.GET("/api/v1/grounds/{ground_id}/availability", {
        params: { path: { ground_id: groundId }, query: { date } },
      });
      if (!cancelled) {
        setLoaded({ key: `${groundId}|${date}`, slots: data?.slots ?? [] });
        setSelected(undefined);
        setFormatId(undefined);
        setError(null);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [api, groundId, date]);

  if (grounds.length === 0) {
    return <p className="text-muted-foreground text-sm">{t("noGrounds")}</p>;
  }

  const chosen = slots.find((slot) => slot.start === selected);
  const ground = grounds.find((item) => item.id === groundId);
  // A ground can host several formats (5v5 and 7v7 on the same pitch); the player picks
  // when there is a choice, and the first is assumed when there is not.
  const formats = ground?.sport_formats ?? [];
  const format = formats.find((item) => item.id === formatId) ?? formats[0];

  async function confirmBooking() {
    if (!chosen || !format) return;
    setBooking(true);
    setError(null);

    const {
      data,
      response,
      error: apiError,
    } = await api.POST("/api/v1/bookings", {
      body: {
        ground_id: groundId,
        sport_format_id: format.id,
        start: chosen.start,
        mode,
        // A group booking's visibility comes from the squad's open/closed flag
        // (DOMAIN §6), so sending one here would be ignored.
        ...(mode === "group" ? { squad_id: squadId } : { visibility }),
        notes,
      } as never,
    });

    setBooking(false);

    if (apiError || !data) {
      // 409 means somebody was simply faster — the slot grid is reloaded so the player
      // can see what is still open rather than being told to try again blindly.
      setError(response?.status === 409 ? t("slotJustTaken") : t("bookingFailed"));
      setLoaded(undefined);
      return;
    }

    router.push(`/bookings/${data.id}`);
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="ground">{t("ground")}</Label>
          <select
            id="ground"
            value={groundId}
            onChange={(event) => setGroundId(event.target.value)}
            className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
          >
            {grounds.map((ground) => (
              <option key={ground.id} value={ground.id}>
                {ground.name} — {ground.sports.map((sport) => sport.name).join(", ")}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="date">{t("date")}</Label>
          <Input
            id="date"
            type="date"
            value={date}
            min={dhakaDate()}
            max={dhakaDate(horizonDays)}
            onChange={(event) => setDate(event.target.value)}
            className="w-40"
          />
        </div>
      </div>

      {loading ? (
        <p className="text-muted-foreground text-sm">{t("loadingSlots")}</p>
      ) : (
        <SlotGrid slots={slots} selected={selected} onSelect={(slot) => setSelected(slot.start)} />
      )}

      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      {chosen && format && (
        <div className="bg-muted/40 flex flex-col gap-3 rounded-lg border p-4 text-sm">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-medium">
              {t("selectedSlot", {
                time: new Intl.DateTimeFormat("en-GB", {
                  timeZone: "Asia/Dhaka",
                  hour: "2-digit",
                  minute: "2-digit",
                }).format(new Date(chosen.start)),
                price: chosen.price ?? "—",
              })}
            </span>
            <span className="text-muted-foreground text-xs">
              {ground?.name} · {format.name}
            </span>
          </div>

          {formats.length > 1 && (
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs">{t("format")}</Label>
              <div className="flex flex-wrap gap-2">
                {formats.map((option) => (
                  <Button
                    key={option.id}
                    type="button"
                    size="xs"
                    variant={format?.id === option.id ? "default" : "outline"}
                    aria-pressed={format?.id === option.id}
                    onClick={() => setFormatId(option.id)}
                  >
                    {option.name}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {squads.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs">{t("mode")}</Label>
              <div className="flex flex-wrap gap-2">
                {(["individual", "group"] as const).map((option) => (
                  <Button
                    key={option}
                    type="button"
                    size="xs"
                    variant={mode === option ? "default" : "outline"}
                    aria-pressed={mode === option}
                    onClick={() => setMode(option)}
                  >
                    {t(`mode_${option}`)}
                  </Button>
                ))}
              </div>
            </div>
          )}

          {mode === "group" && squads.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="squad" className="text-xs">
                {t("squad")}
              </Label>
              <select
                id="squad"
                value={squadId}
                onChange={(event) => setSquadId(event.target.value)}
                className="border-input bg-background h-8 w-fit rounded-lg border px-2 text-sm"
              >
                {squads.map((squad) => (
                  <option key={squad.id} value={squad.id}>
                    {squad.name}
                  </option>
                ))}
              </select>
              <p className="text-muted-foreground text-xs">
                {t(
                  squads.find((s) => s.id === squadId)?.accepts_public_requests
                    ? "squadOpenHint"
                    : "squadClosedHint",
                )}
              </p>
            </div>
          )}

          {mode === "individual" && (
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs">{t("visibility")}</Label>
              <div className="flex flex-wrap gap-2">
                {(["public", "private"] as const).map((option) => (
                  <Button
                    key={option}
                    type="button"
                    size="xs"
                    variant={visibility === option ? "default" : "outline"}
                    aria-pressed={visibility === option}
                    onClick={() => setVisibility(option)}
                  >
                    {t(`visibility_${option}`)}
                  </Button>
                ))}
              </div>
              <p className="text-muted-foreground text-xs">{t(`visibilityHint_${visibility}`)}</p>
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="booking-notes" className="text-xs">
              {t("notes")}
            </Label>
            <Input
              id="booking-notes"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              maxLength={500}
              placeholder={t("notesPlaceholder")}
            />
          </div>

          <p className="text-muted-foreground text-xs">
            {t("payCash")} {t("cancellationPolicy", { hours: cancellationFreeHours })}
          </p>

          <Button size="sm" className="self-start" disabled={booking} onClick={confirmBooking}>
            {booking ? t("booking") : t("confirmBooking", { price: chosen.price ?? "—" })}
          </Button>
        </div>
      )}
    </div>
  );
}
