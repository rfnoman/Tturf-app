import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { Button } from "@/components/ui/button";

import { CounterPos } from "./counter-pos";

export const metadata = { title: "Counter · TurfApp" };

/** The till. Built for a tablet on a shelf, not a desk. */
export default async function CounterPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const api = await getServerApiClient();

  const [turf, stock, categories, sales] = await Promise.all([
    api.GET("/api/v1/me/turfs/{slug}", { params: { path: { slug } } }),
    api.GET("/api/v1/me/turfs/{slug}/stock", { params: { path: { slug } } }),
    api.GET("/api/v1/product-categories"),
    api.GET("/api/v1/me/turfs/{slug}/counter-sales", { params: { path: { slug } } }),
  ]);

  if (!turf.data) notFound();
  const t = await getTranslations("counter");

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
          <p className="text-muted-foreground text-sm">{turf.data.name}</p>
        </div>
        <Button size="sm" variant="ghost" asChild>
          <Link href={`/owner/${slug}/inventory`}>{t("backToInventory")}</Link>
        </Button>
      </header>

      <CounterPos
        slug={slug}
        stock={stock.data ?? []}
        categories={categories.data ?? []}
        sales={sales.data ?? []}
      />
    </div>
  );
}
