"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";
import { cn } from "cn";

import type { Booking, Ground, OwnerTurf, SportFormat } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { BookingStatusBadge } from "@/components/booking/booking-status";
import { BookingTime, ExpiresIn } from "@/components/booking/booking-time";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Money } from "@/components/ui/money";

/**
 * The turf's day view: the confirmation queue, the day's bookings with their actions,
 * and a walk-in form.
 *
 * Actions live here rather than on a separate page because a cashier works a counter —
 * confirm, take cash, next — and a round trip per action would make that unusable.
 */
export function TurfCalendar({
  turf,
  date,
  bookings,
  pending,
}: {
  turf: OwnerTurf;
  date: string;
  bookings: Booking[];
  pending: Booking[];
}) {
  const t = useTranslations("turfCalendar");
  const router = useRouter();
  const api = useApiClient();

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(key: string, call: () => Promise<{ error?: unknown }>) {
    setBusy(key);
    setError(null);
    const { error: apiError } = await call();
    setBusy(null);
    if (apiError) {
      setError(describe(apiError) ?? t("failed"));
      return false;
    }
    router.refresh();
    return true;
  }

  return (
    <div className="flex flex-col gap-6">
      {error && (
        <p role="alert" className="text-destructive text-sm whitespace-pre-line">
          {error}
        </p>
      )}

      {pending.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("pending", { count: pending.length })}</CardTitle>
            <p className="text-muted-foreground text-xs">{t("pendingHint")}</p>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {pending.map((booking) => (
              <div
                key={booking.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm"
              >
                <span className="min-w-0">
                  <Link href={`/bookings/${booking.id}`} className="font-medium underline">
                    {booking.player_name}
                  </Link>
                  <span className="text-muted-foreground block text-xs">
                    {booking.ground_name} ·{" "}
                    <BookingTime start={booking.starts_at} end={booking.ends_at} />
                    {" · "}
                    <Money amount={booking.price} />
                  </span>
                </span>
                <span className="flex items-center gap-2">
                  {booking.expires_at && (
                    <span className="text-muted-foreground text-xs">
                      {t("expires")} <ExpiresIn at={booking.expires_at} />
                    </span>
                  )}
                  <Button
                    size="xs"
                    disabled={busy === booking.id}
                    onClick={() =>
                      run(booking.id, () =>
                        api.POST("/api/v1/bookings/{id}/confirm", {
                          params: { path: { id: booking.id } },
                          body: {} as never,
                        }),
                      )
                    }
                  >
                    {t("confirm")}
                  </Button>
                  <Button
                    size="xs"
                    variant="destructive"
                    disabled={busy === booking.id}
                    onClick={() =>
                      run(booking.id, () =>
                        api.POST("/api/v1/bookings/{id}/cancel", {
                          params: { path: { id: booking.id } },
                          body: { reason: t("declinedByTurf") } as never,
                        }),
                      )
                    }
                  >
                    {t("decline")}
                  </Button>
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-3">
          <CardTitle className="text-sm">{t("day")}</CardTitle>
          <Input
            type="date"
            aria-label={t("date")}
            value={date}
            onChange={(event) =>
              router.push(`/owner/${turf.slug}/bookings?date=${event.target.value}`)
            }
            className="w-40"
          />
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {bookings.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("noBookings")}</p>
          ) : (
            bookings.map((booking) => (
              <div
                key={booking.id}
                className={cn(
                  "flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm",
                  booking.status === "cancelled" && "opacity-60",
                )}
              >
                <span className="min-w-0">
                  <Link href={`/bookings/${booking.id}`} className="font-medium underline">
                    {booking.player_name}
                  </Link>
                  <span className="text-muted-foreground block text-xs">
                    {booking.ground_name} ·{" "}
                    <BookingTime start={booking.starts_at} end={booking.ends_at} withDate={false} />{" "}
                    · <Money amount={booking.price} />
                  </span>
                </span>
                <span className="flex items-center gap-2">
                  <BookingStatusBadge status={booking.status} label={booking.status_label} />
                  {booking.status === "reserved" && (
                    <Button
                      size="xs"
                      disabled={busy === booking.id}
                      onClick={() =>
                        run(booking.id, () =>
                          api.POST("/api/v1/bookings/{id}/confirm", {
                            params: { path: { id: booking.id } },
                            body: {} as never,
                          }),
                        )
                      }
                    >
                      {t("confirm")}
                    </Button>
                  )}
                  {booking.status === "confirmed" && (
                    <Button
                      size="xs"
                      disabled={busy === booking.id}
                      onClick={() =>
                        run(booking.id, () =>
                          api.POST("/api/v1/bookings/{id}/mark-paid", {
                            params: { path: { id: booking.id } },
                            body: {} as never,
                          }),
                        )
                      }
                    >
                      {t("markPaid")}
                    </Button>
                  )}
                  {["confirmed", "paid"].includes(booking.status) && (
                    <Button
                      size="xs"
                      variant="outline"
                      disabled={busy === booking.id}
                      onClick={() =>
                        run(booking.id, () =>
                          api.POST("/api/v1/bookings/{id}/no-show", {
                            params: { path: { id: booking.id } },
                            body: {} as never,
                          }),
                        )
                      }
                    >
                      {t("noShow")}
                    </Button>
                  )}
                </span>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <WalkInForm turf={turf} date={date} busy={busy} run={run} />
    </div>
  );
}

function WalkInForm({
  turf,
  date,
  busy,
  run,
}: {
  turf: OwnerTurf;
  date: string;
  busy: string | null;
  run: (key: string, call: () => Promise<{ error?: unknown }>) => Promise<boolean>;
}) {
  const t = useTranslations("turfCalendar");
  const api = useApiClient();

  const grounds = turf.grounds.filter((ground) => ground.is_active);
  const [groundId, setGroundId] = useState(grounds[0]?.id ?? "");
  const [time, setTime] = useState("19:00");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");

  const ground: Ground | undefined = grounds.find((item) => item.id === groundId);
  const format: SportFormat | undefined = ground?.sport_formats[0];

  if (grounds.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{t("walkIn")}</CardTitle>
        <p className="text-muted-foreground text-xs">{t("walkInHint")}</p>
      </CardHeader>
      <CardContent className="flex flex-wrap items-end gap-2">
        <div className="flex flex-col gap-1">
          <Label htmlFor="walkin-ground" className="text-xs">
            {t("ground")}
          </Label>
          <select
            id="walkin-ground"
            value={groundId}
            onChange={(event) => setGroundId(event.target.value)}
            className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
          >
            {grounds.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="walkin-time" className="text-xs">
            {t("time")}
          </Label>
          <Input
            id="walkin-time"
            type="time"
            step={1800}
            value={time}
            onChange={(event) => setTime(event.target.value)}
            className="w-28"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="walkin-name" className="text-xs">
            {t("customerName")}
          </Label>
          <Input
            id="walkin-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="w-40"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="walkin-phone" className="text-xs">
            {t("customerPhone")}
          </Label>
          <Input
            id="walkin-phone"
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
            className="w-40"
          />
        </div>
        <Button
          size="sm"
          disabled={!name.trim() || !format || busy === "walk-in"}
          onClick={async () => {
            if (!format) return;
            // The API takes an exact slot start; Dhaka local time is what staff type.
            const start = new Date(`${date}T${time}:00+06:00`).toISOString();
            const ok = await run("walk-in", () =>
              api.POST("/api/v1/me/turfs/{slug}/bookings/walk-in", {
                params: { path: { slug: turf.slug } },
                body: {
                  ground_id: groundId,
                  sport_format_id: format.id,
                  start,
                  booked_for_name: name,
                  booked_for_phone: phone,
                } as never,
              }),
            );
            if (ok) {
              setName("");
              setPhone("");
            }
          }}
        >
          {t("book")}
        </Button>
      </CardContent>
    </Card>
  );
}

function describe(error: unknown): string | null {
  if (!error || typeof error !== "object") return null;
  const parts: string[] = [];
  for (const [field, value] of Object.entries(error as Record<string, unknown>)) {
    const message = Array.isArray(value) ? value.join(" ") : String(value);
    parts.push(field === "detail" || field === "status" ? message : `${field}: ${message}`);
  }
  return parts.length > 0 ? parts.join("\n") : null;
}
