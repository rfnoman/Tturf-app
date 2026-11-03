import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { Button } from "@/components/ui/button";

import { ManageTurf } from "./manage";

export default async function ManageTurfPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;

  const api = await getServerApiClient();
  const [turf, sports, staff] = await Promise.all([
    api.GET("/api/v1/me/turfs/{slug}", { params: { path: { slug } } }),
    api.GET("/api/v1/sports"),
    api.GET("/api/v1/me/turfs/{slug}/staff", { params: { path: { slug } } }),
  ]);

  if (!turf.data) notFound();

  const t = await getTranslations("ownerManage");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-tight">{turf.data.name}</h1>
          <p className="text-muted-foreground text-sm">
            {turf.data.area} · {turf.data.address}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link href={`/owner/${turf.data.slug}/bookings`}>{t("viewBookings")}</Link>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link href={`/owner/${turf.data.slug}/inventory`}>{t("viewInventory")}</Link>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link href={`/owner/${turf.data.slug}/counter`}>{t("openCounter")}</Link>
          </Button>
          {turf.data.status === "approved" && (
            <Button variant="outline" size="sm" asChild>
              <Link href={`/turfs/${turf.data.slug}`}>{t("viewPublic")}</Link>
            </Button>
          )}
          <Button variant="ghost" size="sm" asChild>
            <Link href="/owner">{t("backToDashboard")}</Link>
          </Button>
        </div>
      </div>

      <ManageTurf turf={turf.data} sports={sports.data ?? []} staff={staff.data ?? []} />
    </div>
  );
}
