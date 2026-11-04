"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";

import type { Order, Rider } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Money } from "@/components/ui/money";
import { formatWhen } from "@/i18n/formats";

type ActionPath =
  | "/api/v1/orders/{order_id}/accept"
  | "/api/v1/orders/{order_id}/pack"
  | "/api/v1/orders/{order_id}/ready"
  | "/api/v1/orders/{order_id}/out"
  | "/api/v1/orders/{order_id}/settle"
  | "/api/v1/orders/{order_id}/cancel"
  | "/api/v1/orders/{order_id}/rider";

/**
 * The queue a turf or the platform works through.
 *
 * One component for both: the job is the same — accept it, pack it, hand it over — and
 * the only difference is whether a rider carries it.
 */
export function OrderQueue({ orders, riders = [] }: { orders: Order[]; riders?: Rider[] }) {
  const t = useTranslations("orderQueue");
  const locale = useLocale();
  const router = useRouter();
  const api = useApiClient();

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [riderFor, setRiderFor] = useState<Record<string, string>>({});

  async function act(orderId: string, path: ActionPath, body: Record<string, unknown> = {}) {
    setBusy(orderId);
    setError(null);
    const { error: apiError } = await api.POST(path, {
      params: { path: { order_id: orderId } },
      body: body as never,
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
    <div className="flex flex-col gap-3" data-testid="order-queue">
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      {orders.map((order) => {
        const id = String(order.id);
        const isDelivery = order.fulfilment !== "pickup_at_turf";
        return (
          <Card key={id}>
            <CardHeader className="flex-row items-start justify-between gap-3">
              <div className="min-w-0">
                <CardTitle className="text-sm">
                  {order.player_name} · <Money amount={order.total} />
                </CardTitle>
                <p className="text-muted-foreground mt-1 text-xs">
                  {order.items.map((item) => `${item.quantity}× ${item.name}`).join(", ")}
                </p>
                <p className="text-muted-foreground text-xs">
                  {order.fulfilment_label}
                  {order.match_summary && ` · ${order.match_summary}`}
                  {order.address && ` · ${order.address.area}`}
                  {order.scheduled_for &&
                    ` · ${t("neededBy", {
                      when: formatWhen(order.scheduled_for, locale, "weekdayTime"),
                    })}`}
                </p>
              </div>
              <Badge>{order.status_label}</Badge>
            </CardHeader>

            <CardContent className="flex flex-wrap items-center gap-2">
              {order.status === "placed" && (
                <Button
                  size="sm"
                  disabled={busy !== null}
                  onClick={() => act(id, "/api/v1/orders/{order_id}/accept")}
                >
                  {t("accept")}
                </Button>
              )}
              {["placed", "accepted"].includes(order.status) && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy !== null}
                  onClick={() => act(id, "/api/v1/orders/{order_id}/pack")}
                >
                  {t("pack")}
                </Button>
              )}
              {!isDelivery && ["accepted", "packed"].includes(order.status) && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy !== null}
                  onClick={() => act(id, "/api/v1/orders/{order_id}/ready")}
                >
                  {t("ready")}
                </Button>
              )}

              {isDelivery && riders.length > 0 && (
                <span className="flex items-center gap-1.5">
                  <select
                    aria-label={t("pickRider")}
                    value={riderFor[id] ?? String(riders[0].id)}
                    onChange={(event) =>
                      setRiderFor((current) => ({ ...current, [id]: event.target.value }))
                    }
                    className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
                  >
                    {riders.map((rider) => (
                      <option key={String(rider.id)} value={String(rider.id)}>
                        {rider.name}
                      </option>
                    ))}
                  </select>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy !== null}
                    onClick={() =>
                      act(id, "/api/v1/orders/{order_id}/rider", {
                        rider_id: riderFor[id] ?? String(riders[0].id),
                      })
                    }
                  >
                    {order.rider_name ? t("reassign") : t("assign")}
                  </Button>
                </span>
              )}

              {isDelivery && ["accepted", "packed"].includes(order.status) && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy !== null}
                  onClick={() => act(id, "/api/v1/orders/{order_id}/out")}
                >
                  {t("out")}
                </Button>
              )}

              <Button
                size="sm"
                disabled={busy !== null}
                onClick={() => act(id, "/api/v1/orders/{order_id}/settle")}
              >
                {isDelivery ? t("delivered") : t("pickedUp")}
              </Button>

              <Button
                size="sm"
                variant="ghost"
                disabled={busy !== null}
                onClick={() =>
                  act(id, "/api/v1/orders/{order_id}/cancel", { reason: t("cancelledByStaff") })
                }
              >
                {t("cancel")}
              </Button>

              {order.rider_name && (
                <span className="text-muted-foreground text-xs">
                  {t("riderIs", { name: order.rider_name })}
                </span>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
