import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { Button } from "@/components/ui/button";

import { TurfCalendar } from "./calendar";

/** Dhaka-local YYYY-MM-DD: a turf's day is a local day, not a UTC one. */
function dhakaToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Dhaka" }).format(new Date());
}

export default async function TurfBookingsPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ date?: string }>;
}) {
  const [{ slug }, { date }] = await Promise.all([params, searchParams]);
  const day = date ?? dhakaToday();

  const api = await getServerApiClient();
  const [turf, bookings, pending] = await Promise.all([
    api.GET("/api/v1/me/turfs/{slug}", { params: { path: { slug } } }),
    api.GET("/api/v1/me/turfs/{slug}/bookings", {
      params: { path: { slug }, query: { date: day } },
    }),
    api.GET("/api/v1/me/turfs/{slug}/bookings/pending", { params: { path: { slug } } }),
  ]);

  if (!turf.data) notFound();
  const t = await getTranslations("turfCalendar");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-tight">{turf.data.name}</h1>
          <p className="text-muted-foreground text-sm">{t("body")}</p>
        </div>
        <Button variant="ghost" size="sm" asChild>
          <Link href={`/owner/${slug}`}>{t("manageTurf")}</Link>
        </Button>
      </div>

      <TurfCalendar
        turf={turf.data}
        date={day}
        bookings={bookings.data ?? []}
        pending={pending.data ?? []}
      />
    </div>
  );
}
