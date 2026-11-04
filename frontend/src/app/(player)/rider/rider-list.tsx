"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";

import type { Order } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * One card per drop, with the two things a rider on a bike needs: where it goes and a
 * number to ring. Buttons are full-width because this is used one-handed.
 */
export function RiderList({ orders }: { orders: Order[] }) {
  const t = useTranslations("rider");
  const router = useRouter();
  const api = useApiClient();

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function act(
    orderId: string,
    path: "/api/v1/orders/{order_id}/out" | "/api/v1/orders/{order_id}/settle",
  ) {
    setBusy(orderId);
    setError(null);
    const { error: apiError } = await api.POST(path, {
      params: { path: { order_id: orderId } },
      body: {} as never,
    });
    setBusy(null);
    if (apiError) {
      setError(t("failed"));
      return;
    }
    router.refresh();
  }

  if (orders.length === 0) {
    return <p className="text-muted-foreground text-sm">{t("empty")}</p>;
  }

  return (
    <div className="flex flex-col gap-3" data-testid="rider-list">
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      {orders.map((order) => {
        const id = String(order.id);
        const where = order.address
          ? `${order.address.line}, ${order.address.area}`
          : order.match_summary || order.source_name;
        return (
          <Card key={id}>
            <CardHeader className="flex-row items-start justify-between gap-3">
              <div className="min-w-0">
                <CardTitle className="text-sm">{where}</CardTitle>
                <p className="text-muted-foreground mt-1 text-xs">
                  {order.player_name} · ৳{order.total} · {t("collectCash")}
                </p>
              </div>
              <Badge>{order.status_label}</Badge>
            </CardHeader>

            <CardContent className="flex flex-col gap-2">
              <p className="text-muted-foreground text-xs">
                {order.items.map((item) => `${item.quantity}× ${item.name}`).join(", ")}
              </p>

              <div className="flex flex-wrap gap-2">
                {order.address?.phone && (
                  <Button size="sm" variant="outline" asChild>
                    <a href={`tel:${order.address.phone}`}>{t("call")}</a>
                  </Button>
                )}
                {order.address && (
                  <Button size="sm" variant="outline" asChild>
                    <a
                      href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(
                        `${order.address.line}, ${order.address.area}, Dhaka`,
                      )}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {t("map")}
                    </a>
                  </Button>
                )}
              </div>

              {order.status !== "out_for_delivery" && (
                <Button
                  size="lg"
                  className="w-full"
                  disabled={busy !== null}
                  onClick={() => act(id, "/api/v1/orders/{order_id}/out")}
                >
                  {t("onMyWay")}
                </Button>
              )}
              <Button
                size="lg"
                variant={order.status === "out_for_delivery" ? "default" : "outline"}
                className="w-full"
                disabled={busy !== null}
                onClick={() => act(id, "/api/v1/orders/{order_id}/settle")}
              >
                {t("delivered")}
              </Button>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
