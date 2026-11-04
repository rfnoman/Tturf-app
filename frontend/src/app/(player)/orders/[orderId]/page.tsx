import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Money } from "@/components/ui/money";

import { CancelOrder } from "./cancel-order";
import { When } from "@/components/ui/when";

/** One order, and where it has got to. */
export default async function OrderPage({ params }: { params: Promise<{ orderId: string }> }) {
  const { orderId } = await params;
  const api = await getServerApiClient();
  const { data } = await api.GET("/api/v1/orders/{order_id}", {
    params: { path: { order_id: orderId } },
  });

  if (!data) notFound();
  const t = await getTranslations("orders");

  return (
    <div className="flex flex-col gap-6" data-testid="order-detail">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {t("orderFrom", { source: data.source_name })}
          </h1>
          <p className="text-muted-foreground text-sm">
            {data.fulfilment_label}
            {data.match_summary && ` · ${data.match_summary}`}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge data-testid="order-status">{data.status_label}</Badge>
            <Money amount={data.total} className="text-sm" />
          </div>
        </div>
        <Button size="sm" variant="ghost" asChild>
          <Link href="/orders">{t("allOrders")}</Link>
        </Button>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("items")}</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="flex flex-col divide-y text-sm">
            {data.items.map((item) => (
              <li key={String(item.id)} className="flex items-baseline justify-between gap-2 py-2">
                <span className="min-w-0">
                  <span className="truncate">
                    {item.quantity} × {item.name}
                  </span>
                  {item.nutrition?.calories != null && (
                    <span className="text-muted-foreground block text-xs">
                      {t("nutritionLine", {
                        calories: item.nutrition.calories,
                        serving: item.nutrition.serving_size || "",
                      })}
                    </span>
                  )}
                </span>
                <Money amount={item.line_total} />
              </li>
            ))}
          </ul>

          <dl className="mt-3 flex flex-col gap-1 border-t pt-3 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">{t("subtotal")}</dt>
              <dd>
                <Money amount={data.subtotal} />
              </dd>
            </div>
            {Number(data.delivery_fee) > 0 && (
              <div className="flex justify-between">
                <dt className="text-muted-foreground">{t("deliveryFee")}</dt>
                <dd>
                  <Money amount={data.delivery_fee} />
                </dd>
              </div>
            )}
            <div className="flex justify-between font-semibold">
              <dt>{t("total")}</dt>
              <dd>
                <Money amount={data.total} />
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {data.address && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("deliveringTo")}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            {data.address.line}, {data.address.area}
            {data.rider_name && (
              <p className="text-muted-foreground mt-1 text-xs">
                {t("rider", { name: data.rider_name })}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("progress")}</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="flex flex-col gap-1.5 text-sm">
            {data.events.map((event) => (
              <li key={String(event.id)} className="flex flex-wrap gap-x-2">
                <span className="font-medium">{event.to_status_label}</span>
                {event.actor_name && (
                  <span className="text-muted-foreground">{event.actor_name}</span>
                )}
                <span className="text-muted-foreground">
                  <When at={event.created_at} style="dayMonthTime" />
                </span>
                {event.note && <span className="text-muted-foreground">— {event.note}</span>}
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      {(data.status === "placed" || data.status === "accepted") && (
        <CancelOrder orderId={String(data.id)} />
      )}
    </div>
  );
}
