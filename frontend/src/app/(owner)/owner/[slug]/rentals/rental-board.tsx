"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";

import type { Booking, Rental, StockItem } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatWhen } from "@/i18n/formats";

/**
 * Gear going out and coming back.
 *
 * Handing gear over needs a player id, so this offers the players on today's bookings
 * rather than a free-text name — the deposit has to be given back to somebody.
 */
export function RentalBoard({
  slug,
  rentals,
  stock,
  bookings,
}: {
  slug: string;
  rentals: Rental[];
  stock: StockItem[];
  bookings: Booking[];
}) {
  const t = useTranslations("rentals");
  const locale = useLocale();
  const router = useRouter();
  const api = useApiClient();

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [productId, setProductId] = useState(stock[0] ? String(stock[0].product.id) : "");
  const [playerId, setPlayerId] = useState("");
  const [quantity, setQuantity] = useState("1");

  // Who is here today: the people a deposit can be handed back to.
  const players = bookings
    .map((booking) => ({
      id: String(booking.player_profile_id ?? ""),
      name: booking.player_name,
      when: booking.starts_at,
    }))
    .filter((player) => player.id);

  async function handOver() {
    if (!productId || !playerId) return;
    setBusy("out");
    setError(null);
    const { error: apiError, response } = await api.POST("/api/v1/me/turfs/{slug}/rentals", {
      params: { path: { slug } },
      body: {
        product_id: productId,
        player_id: playerId,
        quantity: Number(quantity) || 1,
      } as never,
    });
    setBusy(null);
    if (apiError) {
      setError(response?.status === 409 ? t("noneLeft") : t("failed"));
      return;
    }
    router.refresh();
  }

  async function settle(rentalId: string, lost: boolean) {
    setBusy(rentalId);
    setError(null);
    const path = lost
      ? "/api/v1/me/turfs/{slug}/rentals/{rental_id}/lost"
      : "/api/v1/me/turfs/{slug}/rentals/{rental_id}/return";
    const { error: apiError } = await api.POST(path, {
      params: { path: { slug, rental_id: rentalId } },
      body: {} as never,
    });
    setBusy(null);
    if (apiError) {
      setError(t("failed"));
      return;
    }
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-6">
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("handOver")}</CardTitle>
          <p className="text-muted-foreground text-xs">{t("handOverHint")}</p>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          {stock.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("noGear")}</p>
          ) : (
            <>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="rental-product">{t("gear")}</Label>
                <select
                  id="rental-product"
                  value={productId}
                  onChange={(event) => setProductId(event.target.value)}
                  className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
                >
                  {stock.map((item) => (
                    <option key={String(item.id)} value={String(item.product.id)}>
                      {item.product.name} ({item.available})
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="rental-player">{t("player")}</Label>
                <select
                  id="rental-player"
                  value={playerId}
                  onChange={(event) => setPlayerId(event.target.value)}
                  className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
                >
                  <option value="">{t("pickPlayer")}</option>
                  {players.map((player) => (
                    <option key={player.id} value={player.id}>
                      {player.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="rental-quantity">{t("quantity")}</Label>
                <Input
                  id="rental-quantity"
                  type="number"
                  min={1}
                  value={quantity}
                  onChange={(event) => setQuantity(event.target.value)}
                  className="w-20"
                />
              </div>
              <Button size="sm" disabled={busy !== null || !playerId} onClick={handOver}>
                {t("takeOut")}
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("out")}</CardTitle>
        </CardHeader>
        <CardContent>
          {rentals.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("nothingOut")}</p>
          ) : (
            <ul className="flex flex-col divide-y" data-testid="rental-list">
              {rentals.map((rental) => (
                <li
                  key={String(rental.id)}
                  className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
                >
                  <span className="min-w-0">
                    <span className="font-medium">
                      {rental.quantity} × {rental.product_name}
                    </span>
                    <span className="text-muted-foreground"> · {rental.player_name}</span>
                    {rental.out_at && (
                      <span className="text-muted-foreground text-xs">
                        {" · "}
                        {formatWhen(rental.out_at, locale, "time")}
                      </span>
                    )}
                  </span>
                  <span className="flex items-center gap-2">
                    <Badge variant="secondary">{t("deposit", { amount: rental.deposit })}</Badge>
                    <Button
                      size="xs"
                      disabled={busy !== null}
                      onClick={() => settle(String(rental.id), false)}
                    >
                      {t("returned")}
                    </Button>
                    <Button
                      size="xs"
                      variant="outline"
                      disabled={busy !== null}
                      onClick={() => settle(String(rental.id), true)}
                    >
                      {t("lost")}
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
