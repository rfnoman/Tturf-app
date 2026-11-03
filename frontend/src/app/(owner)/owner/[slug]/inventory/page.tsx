import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { Button } from "@/components/ui/button";

import { InventoryBoard } from "./inventory-board";

export const metadata = { title: "Inventory · TurfApp" };

/** The owner's shelf: what is on it, what is running out, and what moved. */
export default async function InventoryPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const api = await getServerApiClient();

  const [turf, stock, categories, log] = await Promise.all([
    api.GET("/api/v1/me/turfs/{slug}", { params: { path: { slug } } }),
    api.GET("/api/v1/me/turfs/{slug}/stock", { params: { path: { slug } } }),
    api.GET("/api/v1/product-categories"),
    api.GET("/api/v1/me/turfs/{slug}/stock-log", { params: { path: { slug } } }),
  ]);

  if (!turf.data) notFound();
  const t = await getTranslations("inventory");

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
          <p className="text-muted-foreground text-sm">{turf.data.name}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" asChild>
            <Link href={`/owner/${slug}/counter`}>{t("openCounter")}</Link>
          </Button>
          <Button size="sm" variant="outline" asChild>
            <Link href={`/owner/${slug}/rentals`}>{t("rentals")}</Link>
          </Button>
          <Button size="sm" variant="ghost" asChild>
            <Link href={`/owner/${slug}`}>{t("backToTurf")}</Link>
          </Button>
        </div>
      </header>

      <InventoryBoard
        slug={slug}
        stock={stock.data ?? []}
        categories={categories.data ?? []}
        log={log.data ?? []}
      />
    </div>
  );
}
