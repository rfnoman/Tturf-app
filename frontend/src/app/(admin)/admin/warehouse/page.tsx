import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { Warehouse } from "./warehouse";

export const metadata = { title: "Warehouse · TurfApp" };

/** The platform's own stock — what the Phase 08 store will sell and deliver. */
export default async function WarehousePage() {
  const api = await getServerApiClient();
  const [stock, categories] = await Promise.all([
    api.GET("/api/v1/admin/warehouse/stock"),
    api.GET("/api/v1/product-categories"),
  ]);

  const t = await getTranslations("warehouse");

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
        <p className="text-muted-foreground text-sm">{t("body")}</p>
      </header>

      <Warehouse stock={stock.data ?? []} categories={categories.data ?? []} />
    </div>
  );
}
