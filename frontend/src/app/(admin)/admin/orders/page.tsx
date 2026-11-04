import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { OrderQueue } from "@/components/store/order-queue";

export const metadata = { title: "Orders · TurfApp" };

/** The platform's own queue, with riders to hand deliveries to. */
export default async function AdminOrdersPage() {
  const api = await getServerApiClient();
  const [orders, riders] = await Promise.all([
    api.GET("/api/v1/admin/orders"),
    api.GET("/api/v1/admin/riders"),
  ]);

  const t = await getTranslations("orderQueue");

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("platformHeading")}</h1>
        <p className="text-muted-foreground text-sm">{t("platformBody")}</p>
      </header>

      <OrderQueue orders={orders.data ?? []} riders={riders.data ?? []} />
    </div>
  );
}
