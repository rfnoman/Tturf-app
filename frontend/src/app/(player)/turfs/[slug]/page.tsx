import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { fetchClientConfig } from "@/lib/api/config-queries";
import { getServerApiClient } from "@/lib/api/server";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TurfMap } from "@/components/turf/turf-map";

import { BookingPanel } from "./booking-panel";

/** Monday-first, matching the backend's `date.weekday()` convention. */
const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6];

export default async function TurfDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;

  const api = await getServerApiClient();
  const [turf, config, squads] = await Promise.all([
    api.GET("/api/v1/turfs/{slug}", { params: { path: { slug } } }),
    fetchClientConfig(),
    api.GET("/api/v1/squads"),
  ]);

  if (!turf.data) notFound();
  const data = turf.data;
  const t = await getTranslations("turfs");

  const hoursByDay = new Map<number, typeof data.operating_hours>();
  for (const row of data.operating_hours) {
    hoursByDay.set(row.weekday, [...(hoursByDay.get(row.weekday) ?? []), row]);
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{data.name}</h1>
        <p className="text-muted-foreground text-sm">
          {data.area} · {data.address}
        </p>
        {data.description && <p className="text-sm leading-relaxed">{data.description}</p>}
        <div className="flex flex-wrap gap-1.5">
          {data.sports.map((sport) => (
            <Badge key={sport.slug} variant="secondary">
              <span aria-hidden className="mr-1">
                {sport.icon}
              </span>
              {sport.name}
            </Badge>
          ))}
        </div>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("availability")}</CardTitle>
          <p className="text-muted-foreground text-xs">{t("availabilityHint")}</p>
        </CardHeader>
        <CardContent>
          <BookingPanel
            grounds={data.grounds}
            horizonDays={config.booking_horizon_days}
            cancellationFreeHours={data.cancellation_free_hours}
            squads={squads.data?.results ?? []}
          />
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("openingHours")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-1 text-sm">
              {WEEKDAYS.map((day) => {
                const rows = hoursByDay.get(day) ?? [];
                return (
                  <li key={day} className="flex items-baseline justify-between gap-3">
                    <span className="text-muted-foreground text-xs">{t(`weekday.${day}`)}</span>
                    <span className="font-mono text-xs tabular-nums">
                      {rows.length === 0
                        ? t("closed")
                        : rows
                            .map(
                              (row) => `${row.open_time.slice(0, 5)}–${row.close_time.slice(0, 5)}`,
                            )
                            .join(", ")}
                    </span>
                  </li>
                );
              })}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("amenities")}</CardTitle>
          </CardHeader>
          <CardContent>
            {data.amenities.length === 0 ? (
              <p className="text-muted-foreground text-sm">{t("noAmenities")}</p>
            ) : (
              <ul className="flex flex-wrap gap-1.5">
                {data.amenities.map((amenity) => (
                  <li key={amenity.id}>
                    <Badge variant="outline">
                      <span aria-hidden className="mr-1">
                        {amenity.icon}
                      </span>
                      {amenity.label}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
            {data.phone && (
              <p className="text-muted-foreground mt-3 text-xs">
                {t("phone", { phone: data.phone })}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {data.latitude != null && data.longitude != null && (
        <TurfMap
          center={[data.latitude, data.longitude]}
          zoom={15}
          markers={[
            {
              id: data.id,
              latitude: data.latitude,
              longitude: data.longitude,
              label: data.name,
              sublabel: data.area,
            },
          ]}
        />
      )}
    </div>
  );
}
