"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";

import type { Booking } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/**
 * What can be done to a booking from its own page.
 *
 * Which buttons appear is decided by the booking's status *and* by whether the reader
 * is staff at the turf — the API enforces both regardless, so this only decides what to
 * render, never what is allowed.
 */
export function BookingActions({ booking, isStaff }: { booking: Booking; isStaff: boolean }) {
  const t = useTranslations("bookingDetail");
  const router = useRouter();
  const api = useApiClient();

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  async function run(key: string, call: () => Promise<{ error?: unknown }>) {
    setBusy(key);
    setError(null);
    const { error: apiError } = await call();
    setBusy(null);
    if (apiError) {
      setError(describe(apiError) ?? t("failed"));
      return;
    }
    router.refresh();
  }

  const path = { path: { id: booking.id } };
  const cancellable = ["reserved", "confirmed", "paid"].includes(booking.status);

  return (
    <div className="flex flex-col gap-3">
      {error && (
        <p role="alert" className="text-destructive text-sm whitespace-pre-line">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {isStaff && booking.status === "reserved" && (
          <Button
            size="sm"
            disabled={busy === "confirm"}
            onClick={() =>
              run("confirm", () =>
                api.POST("/api/v1/bookings/{id}/confirm", { params: path, body: {} as never }),
              )
            }
          >
            {t("confirm")}
          </Button>
        )}

        {isStaff && booking.status === "confirmed" && (
          <Button
            size="sm"
            disabled={busy === "paid"}
            onClick={() =>
              run("paid", () =>
                api.POST("/api/v1/bookings/{id}/mark-paid", {
                  params: path,
                  body: {} as never,
                }),
              )
            }
          >
            {t("markPaid", { price: booking.price })}
          </Button>
        )}

        {isStaff && ["confirmed", "paid"].includes(booking.status) && (
          <Button
            size="sm"
            variant="outline"
            disabled={busy === "no-show"}
            onClick={() =>
              run("no-show", () =>
                api.POST("/api/v1/bookings/{id}/no-show", { params: path, body: {} as never }),
              )
            }
          >
            {t("noShow")}
          </Button>
        )}
      </div>

      {cancellable && (
        <div className="flex flex-wrap items-end gap-2 border-t pt-3">
          <Input
            aria-label={t("cancelReason")}
            placeholder={t("cancelReasonPlaceholder")}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            className="min-w-48 flex-1"
          />
          <Button
            size="sm"
            variant="destructive"
            disabled={busy === "cancel"}
            onClick={() =>
              run("cancel", () =>
                api.POST("/api/v1/bookings/{id}/cancel", {
                  params: path,
                  body: { reason } as never,
                }),
              )
            }
          >
            {t("cancel")}
          </Button>
        </div>
      )}
    </div>
  );
}

/** Surface the API's own validation message — it is the useful part. */
function describe(error: unknown): string | null {
  if (!error || typeof error !== "object") return null;
  const parts: string[] = [];
  for (const [field, value] of Object.entries(error as Record<string, unknown>)) {
    const message = Array.isArray(value) ? value.join(" ") : String(value);
    parts.push(field === "detail" || field === "status" ? message : `${field}: ${message}`);
  }
  return parts.length > 0 ? parts.join("\n") : null;
}
