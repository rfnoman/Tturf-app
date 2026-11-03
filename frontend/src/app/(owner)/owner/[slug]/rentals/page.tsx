import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { Button } from "@/components/ui/button";

import { RentalBoard } from "./rental-board";

export const metadata = { title: "Rentals · TurfApp" };

/** What is out, and who has it (DOMAIN §9). */
export default async function RentalsPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const api = await getServerApiClient();

  const [turf, rentals, stock, bookings] = await Promise.all([
    api.GET("/api/v1/me/turfs/{slug}", { params: { path: { slug } } }),
    api.GET("/api/v1/me/turfs/{slug}/rentals", { params: { path: { slug } } }),
    api.GET("/api/v1/me/turfs/{slug}/stock", { params: { path: { slug } } }),
    api.GET("/api/v1/me/turfs/{slug}/bookings", { params: { path: { slug } } }),
  ]);

  if (!turf.data) notFound();
  const t = await getTranslations("rentals");

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
          <p className="text-muted-foreground text-sm">{turf.data.name}</p>
        </div>
        <Button size="sm" variant="ghost" asChild>
          <Link href={`/owner/${slug}/inventory`}>{t("backToInventory")}</Link>
        </Button>
      </header>

      <RentalBoard
        slug={slug}
        rentals={rentals.data ?? []}
        stock={(stock.data ?? []).filter((item) => item.product.kind === "rental")}
        bookings={bookings.data ?? []}
      />
    </div>
  );
}
