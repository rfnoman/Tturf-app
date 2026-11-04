import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { BookingStatusBadge } from "@/components/booking/booking-status";
import { BookingTime, DhakaMoment } from "@/components/booking/booking-time";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { PayButton } from "@/components/payments/pay-button";
import { Money } from "@/components/ui/money";

import { BookingActions } from "./booking-actions";

export default async function BookingPage({ params }: { params: Promise<{ bookingId: string }> }) {
  const { bookingId } = await params;

  const api = await getServerApiClient();
  const [booking, myTurfs] = await Promise.all([
    api.GET("/api/v1/bookings/{id}", { params: { path: { id: bookingId } } }),
    api.GET("/api/v1/me/turfs"),
  ]);

  if (!booking.data) notFound();
  const data = booking.data;
  const t = await getTranslations("bookingDetail");

  // The advance is a turf setting, so it comes from the public turf record rather than
  // from the booking itself.
  const turf = await api.GET("/api/v1/turfs/{slug}", {
    params: { path: { slug: data.turf_slug } },
  });
  const advancePercent = turf.data?.advance_percent ?? 0;
  const advanceAmount = ((Number(data.price) * advancePercent) / 100).toFixed(2);

  // The API decides what staff may do; this only decides which buttons to render.
  const isStaff = (myTurfs.data?.results ?? []).some((turf) => turf.slug === data.turf_slug);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{data.turf_name}</h1>
          <p className="text-muted-foreground text-sm">
            {data.ground_name} · {data.sport.name} {data.sport_format.name}
          </p>
          <p className="mt-1 text-sm">
            <BookingTime start={data.starts_at} end={data.ends_at} />
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <BookingStatusBadge status={data.status} label={data.status_label} />
          <Money amount={data.price} className="text-lg font-semibold" />
          {data.price_label && (
            <span className="text-muted-foreground text-xs">{data.price_label}</span>
          )}
        </div>
      </header>

      {data.status === "reserved" && data.expires_at && (
        <Card>
          <CardContent className="py-4 text-sm">{t("awaitingConfirmation")}</CardContent>
        </Card>
      )}

      {/* Paying up front is what confirms a slot at a turf that asks for an advance,
          whatever the player's record says (DECISIONS D8). */}
      {data.is_mine && ["reserved", "confirmed"].includes(data.status) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("payNow")}</CardTitle>
            <p className="text-muted-foreground text-xs">
              {advancePercent > 0 && data.status === "reserved"
                ? t("advanceHint", { percent: advancePercent })
                : t("payHint")}
            </p>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {advancePercent > 0 && data.status === "reserved" && (
              <PayButton
                bookingId={String(data.id)}
                kind="advance"
                amount={advanceAmount}
                label={t("payAdvance", { amount: advanceAmount })}
              />
            )}
            <PayButton
              bookingId={String(data.id)}
              kind="full"
              amount={data.price}
              variant={advancePercent > 0 && data.status === "reserved" ? "outline" : "default"}
            />
          </CardContent>
        </Card>
      )}

      {data.cancel_reason && (
        <Card>
          <CardContent className="text-destructive py-4 text-sm">{data.cancel_reason}</CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("actions")}</CardTitle>
        </CardHeader>
        <CardContent>
          <BookingActions booking={data} isStaff={isStaff} />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("timeline")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="flex flex-col gap-3">
              {data.events.map((event) => (
                <li key={event.id} className="flex items-start gap-3 text-sm">
                  <span aria-hidden className="bg-primary mt-1.5 size-1.5 shrink-0 rounded-full" />
                  <span className="min-w-0 flex-1">
                    <span className="font-medium">{event.to_status_label}</span>
                    {event.actor_name && (
                      <span className="text-muted-foreground"> · {event.actor_name}</span>
                    )}
                    {event.note && (
                      <span className="text-muted-foreground block text-xs">{event.note}</span>
                    )}
                  </span>
                  <span className="text-muted-foreground shrink-0 text-xs">
                    <DhakaMoment at={event.created_at} />
                  </span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("details")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-sm">
            <Row label={t("player")} value={data.player_name} />
            {data.booked_for_phone && <Row label={t("phone")} value={data.booked_for_phone} />}
            <Row label={t("visibility")} value={t(`visibility_${data.visibility}`)} />
            <Row
              label={t("payment")}
              value={
                data.payments.length > 0
                  ? t("paidAmount", { amount: data.payments[0].amount })
                  : t("payAtTurf")
              }
            />
            <Row
              label={t("cancellationPolicy")}
              value={t("freeUntil", { hours: data.cancellation_free_hours })}
            />
            {data.notes && <Row label={t("notes")} value={data.notes} />}
            {data.auto_confirmed && (
              <Badge variant="outline" className="self-start">
                {t("autoConfirmed")}
              </Badge>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="flex gap-2">
        <Button variant="outline" size="sm" asChild>
          <Link href="/bookings">{t("myBookings")}</Link>
        </Button>
        <Button variant="ghost" size="sm" asChild>
          <Link href={`/turfs/${data.turf_slug}`}>{t("viewTurf")}</Link>
        </Button>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-muted-foreground text-xs">{label}</span>
      <span className="text-right">{value}</span>
    </div>
  );
}
