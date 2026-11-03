"use client";

import { useMemo } from "react";
import { useFormatter, useTranslations } from "next-intl";
import { cn } from "cn";

import type { Slot } from "@/lib/api/types";

/**
 * A day's slots for one ground.
 *
 * Unavailable slots are rendered, not hidden: a greyed-out 7pm tells a player the turf
 * is busy, where a gap would read as "closed". `onSelect` is what Phase 03 hangs the
 * booking flow on; without it the grid is a read-only price board.
 */
export function SlotGrid({
  slots,
  selected,
  onSelect,
  className,
}: {
  slots: Slot[];
  selected?: string;
  onSelect?: (slot: Slot) => void;
  className?: string;
}) {
  const t = useTranslations("turfs");
  const format = useFormatter();

  const grouped = useMemo(() => {
    // Slots that run past midnight belong to the evening they started in, so grouping
    // is by the label the player reads rather than by calendar date.
    return slots.map((slot) => ({
      slot,
      time: format.dateTime(new Date(slot.start), {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
        timeZone: "Asia/Dhaka",
      }),
    }));
  }, [slots, format]);

  if (slots.length === 0) {
    return <p className="text-muted-foreground text-sm">{t("noSlots")}</p>;
  }

  return (
    <div className={cn("grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4", className)}>
      {grouped.map(({ slot, time }) => {
        const isSelected = selected === slot.start;
        const interactive = Boolean(onSelect) && slot.available;

        return (
          <button
            key={slot.start}
            type="button"
            disabled={!interactive}
            aria-pressed={interactive ? isSelected : undefined}
            onClick={() => onSelect?.(slot)}
            title={slot.available ? undefined : t(`slotReason.${slot.reason || "closed"}`)}
            className={cn(
              "flex flex-col items-start gap-0.5 rounded-lg border px-3 py-2 text-left transition-colors",
              isSelected && "border-primary bg-primary/10",
              !isSelected && slot.available && "hover:bg-muted/60",
              !slot.available && "bg-muted/40 text-muted-foreground cursor-not-allowed opacity-60",
              !interactive && slot.available && "cursor-default",
            )}
          >
            <span className="font-mono text-sm tabular-nums">{time}</span>
            <span className="flex w-full items-center justify-between gap-1 text-xs">
              <span>{slot.price ? t("taka", { price: slot.price }) : "—"}</span>
              {slot.label && <span className="text-muted-foreground">{slot.label}</span>}
            </span>
            {!slot.available && (
              <span className="text-[0.625rem] uppercase">
                {t(`slotReason.${slot.reason || "closed"}`)}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
