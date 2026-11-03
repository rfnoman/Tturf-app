import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { BookingStatusBadge } from "@/components/booking/booking-status";
import { BookingTime } from "@/components/booking/booking-time";
import { Card, CardContent } from "@/components/ui/card";

export const metadata = { title: "My bookings · TurfApp" };

export default async function MyBookingsPage({
  searchParams,
}: {
  searchParams: Promise<{ filter?: string }>;
}) {
  // `searchParams` is a promise in Next 16.
  const { filter } = await searchParams;
  const which = filter === "past" ? "past" : "upcoming";

  const api = await getServerApiClient();
  const { data } = await api.GET("/api/v1/me/bookings", {
    params: { query: { filter: which } },
  });

  const t = await getTranslations("myBookings");
  const bookings = data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
        <p className="text-muted-foreground text-sm">{t("body")}</p>
      </div>

      <nav className="flex gap-2 text-sm" aria-label={t("filter")}>
        {(["upcoming", "past"] as const).map((option) => (
          <Link
            key={option}
            href={`/bookings?filter=${option}`}
            aria-current={which === option ? "page" : undefined}
            className={
              which === option
                ? "bg-primary text-primary-foreground rounded-lg px-2.5 py-1 text-xs"
                : "hover:bg-muted rounded-lg px-2.5 py-1 text-xs"
            }
          >
            {t(option)}
          </Link>
        ))}
      </nav>

      {bookings.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
            <p className="text-muted-foreground text-sm">{t(`empty_${which}`)}</p>
            <Link href="/turfs" className="text-sm underline">
              {t("findTurf")}
            </Link>
          </CardContent>
        </Card>
      ) : (
        <ul className="flex flex-col gap-3">
          {bookings.map((booking) => (
            <li key={booking.id}>
              <Link
                href={`/bookings/${booking.id}`}
                className="bg-card hover:bg-muted/40 block rounded-xl border p-4 shadow-sm transition-colors"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h2 className="truncate text-base font-semibold">{booking.turf_name}</h2>
                    <p className="text-muted-foreground text-xs">
                      {booking.ground_name} · {booking.sport.name} · {booking.turf_area}
                    </p>
                    <p className="mt-1 text-sm">
                      <BookingTime start={booking.starts_at} end={booking.ends_at} />
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <BookingStatusBadge status={booking.status} label={booking.status_label} />
                    <span className="font-mono text-sm tabular-nums">৳{booking.price}</span>
                  </div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
