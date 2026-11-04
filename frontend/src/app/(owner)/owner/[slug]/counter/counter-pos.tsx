"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { cn } from "cn";

import type { CounterSale, ProductCategory, StockItem } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Money } from "@/components/ui/money";

type Cart = Record<string, number>;

/**
 * A till: tap a product, tap again for two, take the cash, hand back the change.
 *
 * Everything is one tap deep and the buttons are big, because this is used standing up
 * with a queue waiting. The running total and the change due are the two numbers that
 * matter, so they are the two largest things on the screen.
 */
export function CounterPos({
  slug,
  stock,
  categories,
  sales,
}: {
  slug: string;
  stock: StockItem[];
  categories: ProductCategory[];
  sales: CounterSale[];
}) {
  const t = useTranslations("counter");
  const router = useRouter();
  const api = useApiClient();

  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [cart, setCart] = useState<Cart>({});
  const [cash, setCash] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastSale, setLastSale] = useState<CounterSale | null>(null);

  // Only what can actually be sold: rental gear goes out through the rentals board.
  const sellable = useMemo(
    () => stock.filter((item) => item.product.kind === "sale" && item.product.is_active),
    [stock],
  );

  const shown = sellable.filter((item) => {
    if (category && item.product.category.slug !== category) return false;
    if (search && !item.product.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const byId = new Map(sellable.map((item) => [String(item.product.id), item]));
  const lines = Object.entries(cart).filter(([, quantity]) => quantity > 0);
  const total = lines.reduce(
    (sum, [productId, quantity]) => sum + Number(byId.get(productId)?.price ?? 0) * quantity,
    0,
  );
  const changeDue = Math.max(Number(cash || 0) - total, 0);

  function add(productId: string, step = 1) {
    setCart((current) => {
      const item = byId.get(productId);
      const next = (current[productId] ?? 0) + step;
      // Never ring up more than is on the shelf: the API would refuse it anyway, and
      // finding out at "Take payment" is the wrong moment.
      const capped = Math.max(0, Math.min(next, item?.available ?? 0));
      return { ...current, [productId]: capped };
    });
  }

  async function takePayment() {
    setBusy(true);
    setError(null);
    const {
      data,
      error: apiError,
      response,
    } = await api.POST("/api/v1/me/turfs/{slug}/counter-sales", {
      params: { path: { slug } },
      body: {
        lines: lines.map(([product_id, quantity]) => ({ product_id, quantity })),
        cash_received: cash || "0",
      } as never,
    });
    setBusy(false);

    if (apiError || !data) {
      setError(response?.status === 409 ? t("soldOut") : t("failed"));
      router.refresh();
      return;
    }

    setLastSale(data);
    setCart({});
    setCash("");
    router.refresh();
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_20rem]">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end gap-2">
          <Input
            aria-label={t("search")}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t("searchPlaceholder")}
            className="w-44"
          />
          <Button
            size="sm"
            variant={category === "" ? "default" : "outline"}
            onClick={() => setCategory("")}
          >
            {t("all")}
          </Button>
          {categories
            .filter((item) => sellable.some((row) => row.product.category.slug === item.slug))
            .map((item) => (
              <Button
                key={item.slug}
                size="sm"
                variant={category === item.slug ? "default" : "outline"}
                onClick={() => setCategory(item.slug)}
              >
                {item.icon} {item.label}
              </Button>
            ))}
        </div>

        {shown.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t("nothingHere")}</p>
        ) : (
          <ul
            className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4"
            data-testid="pos-grid"
          >
            {shown.map((item) => {
              const productId = String(item.product.id);
              const inCart = cart[productId] ?? 0;
              const soldOut = item.available <= 0;
              return (
                <li key={productId}>
                  <button
                    type="button"
                    disabled={soldOut}
                    onClick={() => add(productId)}
                    data-product={item.product.name}
                    className={cn(
                      "bg-card relative flex h-24 w-full flex-col items-start justify-between rounded-xl border p-3 text-left transition-colors",
                      !soldOut && "hover:border-primary active:scale-[0.98]",
                      soldOut && "opacity-50",
                      inCart > 0 && "border-primary ring-primary/30 ring-2",
                    )}
                  >
                    <span className="line-clamp-2 text-sm font-medium">{item.product.name}</span>
                    <span className="flex w-full items-baseline justify-between">
                      <span className="font-mono text-base font-semibold tabular-nums">
                        <Money amount={item.price} />
                      </span>
                      <span className="text-muted-foreground text-xs">
                        {soldOut ? t("soldOutShort") : t("left", { count: item.available })}
                      </span>
                    </span>
                    {inCart > 0 && (
                      <span className="bg-primary text-primary-foreground absolute -top-2 -right-2 flex size-6 items-center justify-center rounded-full text-xs font-bold">
                        {inCart}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}

        {sales.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">{t("today")}</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="flex flex-col divide-y text-sm" data-testid="todays-sales">
                {sales.slice(0, 8).map((sale) => (
                  <li key={String(sale.id)} className="flex items-baseline gap-2 py-1.5">
                    <Money amount={sale.total} />
                    <span className="text-muted-foreground min-w-0 flex-1 truncate text-xs">
                      {sale.lines
                        .map((line) => `${line.quantity}× ${line.product_name}`)
                        .join(", ")}
                    </span>
                    {sale.status === "voided" ? (
                      <Badge variant="outline">{t("voided")}</Badge>
                    ) : (
                      <VoidButton slug={slug} saleId={String(sale.id)} />
                    )}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
      </div>

      <Card className="h-fit lg:sticky lg:top-4">
        <CardHeader>
          <CardTitle className="text-sm">{t("cart")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {error && (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          )}

          {lines.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("cartEmpty")}</p>
          ) : (
            <ul className="flex flex-col gap-1.5 text-sm">
              {lines.map(([productId, quantity]) => {
                const item = byId.get(productId);
                if (!item) return null;
                return (
                  <li key={productId} className="flex items-center gap-2">
                    <span className="min-w-0 flex-1 truncate">{item.product.name}</span>
                    <span className="flex items-center gap-1">
                      <Button
                        size="xs"
                        variant="outline"
                        aria-label={t("oneFewer", { product: item.product.name })}
                        onClick={() => add(productId, -1)}
                      >
                        −
                      </Button>
                      <span className="w-6 text-center font-mono tabular-nums">{quantity}</span>
                      <Button
                        size="xs"
                        variant="outline"
                        aria-label={t("oneMore", { product: item.product.name })}
                        onClick={() => add(productId, 1)}
                      >
                        +
                      </Button>
                    </span>
                    <span className="w-16 text-right font-mono tabular-nums">
                      <Money amount={Number(item.price) * quantity} />
                    </span>
                  </li>
                );
              })}
            </ul>
          )}

          <div className="flex items-baseline justify-between border-t pt-3">
            <span className="text-sm font-medium">{t("total")}</span>
            <span className="font-mono text-2xl font-bold tabular-nums" data-testid="pos-total">
              <Money amount={total} />
            </span>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cash-received">{t("cashReceived")}</Label>
            <Input
              id="cash-received"
              type="number"
              min={0}
              value={cash}
              onChange={(event) => setCash(event.target.value)}
              className="h-10 font-mono text-lg"
            />
          </div>

          {Number(cash) > 0 && (
            <div className="flex items-baseline justify-between">
              <span className="text-sm font-medium">{t("changeDue")}</span>
              <span className="font-mono text-2xl font-bold tabular-nums" data-testid="change-due">
                <Money amount={changeDue} />
              </span>
            </div>
          )}

          <Button
            size="lg"
            className="w-full"
            disabled={busy || lines.length === 0}
            onClick={takePayment}
          >
            {busy ? t("saving") : t("takePayment")}
          </Button>

          {lastSale && (
            <p role="status" className="text-muted-foreground text-sm">
              {t("sold", { total: lastSale.total, change: lastSale.change_due })}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function VoidButton({ slug, saleId }: { slug: string; saleId: string }) {
  const t = useTranslations("counter");
  const router = useRouter();
  const api = useApiClient();
  const [busy, setBusy] = useState(false);

  return (
    <Button
      size="xs"
      variant="ghost"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        await api.POST("/api/v1/me/turfs/{slug}/counter-sales/{sale_id}/void", {
          params: { path: { slug, sale_id: saleId } },
          body: { reason: "Rung up by mistake" } as never,
        });
        setBusy(false);
        router.refresh();
      }}
    >
      {t("void")}
    </Button>
  );
}
