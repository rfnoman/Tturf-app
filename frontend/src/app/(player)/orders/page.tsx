import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export const metadata = { title: "My orders · TurfApp" };

export default async function OrdersPage() {
  const api = await getServerApiClient();
  const { data } = await api.GET("/api/v1/me/orders");
  const t = await getTranslations("orders");
  const orders = data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
          <p className="text-muted-foreground text-sm">{t("body")}</p>
        </div>
        <Button size="sm" variant="outline" asChild>
          <Link href="/store">{t("shop")}</Link>
        </Button>
      </header>

      {orders.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col gap-2" data-testid="order-list">
          {orders.map((order) => (
            <li key={String(order.id)}>
              <Link
                href={`/orders/${order.id}`}
                className="hover:border-primary/40 flex flex-wrap items-center justify-between gap-2 rounded-xl border p-3 text-sm transition-colors"
              >
                <span className="min-w-0">
                  <span className="font-medium">{order.source_name}</span>
                  <span className="text-muted-foreground">
                    {" · "}
                    {order.items.map((item) => `${item.quantity}× ${item.name}`).join(", ")}
                  </span>
                </span>
                <span className="flex items-center gap-2">
                  <Badge variant={order.status === "cancelled" ? "outline" : "secondary"}>
                    {order.status_label}
                  </Badge>
                  <span className="font-mono tabular-nums">৳{order.total}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
