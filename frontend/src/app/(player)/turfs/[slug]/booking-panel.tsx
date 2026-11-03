"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import type { Ground, Slot } from "@/lib/api/types";
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
 * Ground picker + date picker + slot grid.
 *
 * Phase 03 turns a selected slot into a booking; until then selecting one just
 * highlights it, so the plumbing (which ground, which slot, what price) is already in
 * place and tested by the time bookings land.
 */
export function BookingPanel({ grounds, horizonDays }: { grounds: Ground[]; horizonDays: number }) {
  const t = useTranslations("turfs");
  const api = useApiClient();

  const [groundId, setGroundId] = useState(grounds[0]?.id ?? "");
  const [date, setDate] = useState(dhakaDate());
  const [selected, setSelected] = useState<string>();
  // Slots are stored with the query they answer. `loading` is then derived rather than
  // set — which keeps setState out of the effect body and, more usefully, means the
  // previous ground's slots are never shown under the new ground's heading.
  const [loaded, setLoaded] = useState<{ key: string; slots: Slot[] }>();

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

      {chosen && (
        <div className="bg-muted/40 flex flex-wrap items-center justify-between gap-2 rounded-lg border p-3 text-sm">
          <span>
            {t("selectedSlot", {
              time: new Intl.DateTimeFormat("en-GB", {
                timeZone: "Asia/Dhaka",
                hour: "2-digit",
                minute: "2-digit",
              }).format(new Date(chosen.start)),
              price: chosen.price ?? "—",
            })}
          </span>
          {/* Phase 03 replaces this with the real booking action. */}
          <Button size="sm" disabled>
            {t("bookingSoon")}
          </Button>
        </div>
      )}
    </div>
  );
}
