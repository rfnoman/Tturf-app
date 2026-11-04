import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { OrderQueue } from "@/components/store/order-queue";
import { Button } from "@/components/ui/button";

export const metadata = { title: "Orders · TurfApp" };

/** Orders waiting at this turf's counter, beside its bookings. */
export default async function TurfOrdersPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const api = await getServerApiClient();

  const [turf, orders] = await Promise.all([
    api.GET("/api/v1/me/turfs/{slug}", { params: { path: { slug } } }),
    api.GET("/api/v1/me/turfs/{slug}/orders", { params: { path: { slug } } }),
  ]);

  if (!turf.data) notFound();
  const t = await getTranslations("orderQueue");

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
          <p className="text-muted-foreground text-sm">{turf.data.name}</p>
        </div>
        <Button size="sm" variant="ghost" asChild>
          <Link href={`/owner/${slug}/inventory`}>{t("inventory")}</Link>
        </Button>
      </header>

      <OrderQueue orders={orders.data ?? []} />
    </div>
  );
}
