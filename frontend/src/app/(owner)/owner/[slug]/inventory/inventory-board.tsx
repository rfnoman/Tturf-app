"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { cn } from "cn";

import type { ProductCategory, StockItem, StockMovement } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Money } from "@/components/ui/money";
import { formatWhen } from "@/i18n/formats";

/**
 * The shelf, the movement log, and the form for adding something new.
 *
 * Receiving and adjusting are inline on each row rather than behind a dialog: a turf
 * counts stock with the tablet in one hand, and a modal for "+12 waters" is a step too
 * many.
 */
export function InventoryBoard({
  slug,
  stock,
  categories,
  log,
}: {
  slug: string;
  stock: StockItem[];
  categories: ProductCategory[];
  log: StockMovement[];
}) {
  const t = useTranslations("inventory");
  const locale = useLocale();
  const router = useRouter();
  const api = useApiClient();

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  async function receive(itemId: string, quantity: number) {
    if (!quantity) return;
    setBusy(itemId);
    setError(null);
    const { error: apiError } = await api.POST("/api/v1/me/turfs/{slug}/stock/{item_id}/receive", {
      params: { path: { slug, item_id: itemId } },
      body: { quantity } as never,
    });
    setBusy(null);
    if (apiError) {
      setError(t("failed"));
      return;
    }
    router.refresh();
  }

  async function adjust(itemId: string, delta: number, reason: string) {
    if (!delta || !reason.trim()) {
      setError(t("needReason"));
      return;
    }
    setBusy(itemId);
    setError(null);
    const { error: apiError } = await api.POST("/api/v1/me/turfs/{slug}/stock/{item_id}/adjust", {
      params: { path: { slug, item_id: itemId } },
      body: { delta, reason } as never,
    });
    setBusy(null);
    if (apiError) {
      setError(t("adjustFailed"));
      return;
    }
    router.refresh();
  }

  const low = stock.filter((item) => item.is_low);

  return (
    <div className="flex flex-col gap-6">
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      {low.length > 0 && (
        <Card className="border-destructive/40">
          <CardHeader>
            <CardTitle className="text-sm">{t("lowHeading", { count: low.length })}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-1.5">
            {low.map((item) => (
              <Badge key={String(item.id)} variant="destructive">
                {item.product.name} · {item.available}
              </Badge>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex-row items-start justify-between gap-3">
          <CardTitle className="text-sm">{t("shelf")}</CardTitle>
          <Button size="sm" variant="outline" onClick={() => setAdding((value) => !value)}>
            {adding ? t("close") : t("addProduct")}
          </Button>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {adding && (
            <AddProduct
              slug={slug}
              categories={categories}
              onDone={() => {
                setAdding(false);
                router.refresh();
              }}
            />
          )}

          {stock.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("empty")}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="stock-table">
                <thead>
                  <tr className="border-b text-left">
                    <th className="px-2 py-2 font-medium">{t("product")}</th>
                    <th className="px-2 py-2 text-right font-medium">{t("onHand")}</th>
                    <th className="px-2 py-2 text-right font-medium">{t("reserved")}</th>
                    <th className="px-2 py-2 text-right font-medium">{t("available")}</th>
                    <th className="px-2 py-2 text-right font-medium">{t("price")}</th>
                    {/* The column has no visible heading — the buttons say what they
                        do — but a screen reader still needs one. */}
                    <th className="px-2 py-2 font-medium">
                      <span className="sr-only">{t("actions")}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {stock.map((item) => (
                    <StockRow
                      key={String(item.id)}
                      item={item}
                      busy={busy === String(item.id)}
                      onReceive={(quantity) => receive(String(item.id), quantity)}
                      onAdjust={(delta, reason) => adjust(String(item.id), delta, reason)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("log")}</CardTitle>
          <p className="text-muted-foreground text-xs">{t("logHint")}</p>
        </CardHeader>
        <CardContent>
          {log.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("noMovements")}</p>
          ) : (
            <ul className="flex flex-col divide-y text-sm" data-testid="movement-log">
              {log.slice(0, 30).map((movement) => (
                <li key={String(movement.id)} className="flex flex-wrap gap-x-2 py-1.5">
                  <span
                    className={cn(
                      "w-10 text-right font-mono tabular-nums",
                      movement.qty_delta > 0 && "text-emerald-600 dark:text-emerald-400",
                      movement.qty_delta < 0 && "text-destructive",
                    )}
                  >
                    {movement.qty_delta > 0 ? "+" : ""}
                    {movement.qty_delta}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{movement.product_name}</span>
                  <span className="text-muted-foreground text-xs">{movement.type_label}</span>
                  {movement.note && (
                    <span className="text-muted-foreground text-xs">— {movement.note}</span>
                  )}
                  <span className="text-muted-foreground text-xs">
                    {formatWhen(movement.created_at, locale, "dayMonthTime")}
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

function StockRow({
  item,
  busy,
  onReceive,
  onAdjust,
}: {
  item: StockItem;
  busy: boolean;
  onReceive: (quantity: number) => void;
  onAdjust: (delta: number, reason: string) => void;
}) {
  const t = useTranslations("inventory");
  const [quantity, setQuantity] = useState("");
  const [open, setOpen] = useState(false);
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("");

  return (
    <>
      <tr className="border-b last:border-b-0" data-product={item.product.name}>
        <td className="px-2 py-2">
          <span className="flex items-center gap-1.5">
            <span className="truncate">{item.product.name}</span>
            {item.product.kind === "rental" && (
              <Badge variant="outline" className="text-[10px]">
                {t("rental")}
              </Badge>
            )}
            {item.is_low && (
              <Badge variant="destructive" className="text-[10px]">
                {t("low")}
              </Badge>
            )}
          </span>
        </td>
        <td className="px-2 py-2 text-right font-mono tabular-nums" data-testid="on-hand">
          {item.on_hand}
        </td>
        <td className="text-muted-foreground px-2 py-2 text-right font-mono tabular-nums">
          {item.reserved}
        </td>
        <td className="px-2 py-2 text-right font-mono font-semibold tabular-nums">
          {item.available}
        </td>
        <td className="px-2 py-2 text-right">
          <Money amount={item.price} />
        </td>
        <td className="px-2 py-2">
          <span className="flex flex-wrap items-center gap-1.5">
            <Input
              aria-label={t("receiveFor", { product: item.product.name })}
              type="number"
              min={1}
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              className="h-7 w-16"
            />
            <Button
              size="xs"
              disabled={busy || !quantity}
              onClick={() => {
                onReceive(Number(quantity));
                setQuantity("");
              }}
            >
              {t("receive")}
            </Button>
            <Button size="xs" variant="ghost" onClick={() => setOpen((value) => !value)}>
              {t("adjust")}
            </Button>
          </span>
        </td>
      </tr>
      {open && (
        <tr className="bg-muted/30 border-b">
          <td colSpan={6} className="px-2 py-2">
            <span className="flex flex-wrap items-end gap-2">
              <span className="flex flex-col gap-1">
                <Label className="text-xs">{t("delta")}</Label>
                <Input
                  aria-label={t("deltaFor", { product: item.product.name })}
                  type="number"
                  value={delta}
                  onChange={(event) => setDelta(event.target.value)}
                  className="h-7 w-20"
                />
              </span>
              <span className="flex min-w-48 flex-1 flex-col gap-1">
                <Label className="text-xs">{t("reason")}</Label>
                <Input
                  aria-label={t("reasonFor", { product: item.product.name })}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder={t("reasonPlaceholder")}
                  className="h-7"
                />
              </span>
              <Button
                size="xs"
                disabled={busy}
                onClick={() => {
                  onAdjust(Number(delta), reason);
                  setDelta("");
                  setReason("");
                  setOpen(false);
                }}
              >
                {t("saveAdjustment")}
              </Button>
            </span>
          </td>
        </tr>
      )}
    </>
  );
}

/** Add something to the shelf. Nutrition appears only where it means anything. */
function AddProduct({
  slug,
  categories,
  onDone,
}: {
  slug: string;
  categories: ProductCategory[];
  onDone: () => void;
}) {
  const t = useTranslations("inventory");
  const api = useApiClient();

  const [categorySlug, setCategorySlug] = useState(categories[0]?.slug ?? "");
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [kind, setKind] = useState<"sale" | "rental">("sale");
  const [rentalPrice, setRentalPrice] = useState("");
  const [deposit, setDeposit] = useState("");
  const [calories, setCalories] = useState("");
  const [servingSize, setServingSize] = useState("");
  const [perishable, setPerishable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const category = categories.find((item) => item.slug === categorySlug);

  async function save() {
    setBusy(true);
    setError(null);
    const { error: apiError } = await api.POST("/api/v1/me/turfs/{slug}/products", {
      params: { path: { slug } },
      body: {
        category: categorySlug,
        name,
        base_price: price || "0.00",
        kind,
        perishable,
        ...(kind === "rental"
          ? { rental_price_per_match: rentalPrice || "0.00", deposit: deposit || "0.00" }
          : {}),
        ...(category?.is_consumable
          ? { calories: calories ? Number(calories) : null, serving_size: servingSize }
          : {}),
      } as never,
    });
    setBusy(false);
    if (apiError) {
      setError(t("addFailed"));
      return;
    }
    onDone();
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border p-3" data-testid="add-product">
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="product-name">{t("name")}</Label>
          <Input
            id="product-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="w-44"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="product-category">{t("category")}</Label>
          <select
            id="product-category"
            value={categorySlug}
            onChange={(event) => setCategorySlug(event.target.value)}
            className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
          >
            {categories.map((item) => (
              <option key={item.slug} value={item.slug}>
                {item.icon} {item.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="product-price">{t("priceBdt")}</Label>
          <Input
            id="product-price"
            type="number"
            min={0}
            step="0.01"
            value={price}
            onChange={(event) => setPrice(event.target.value)}
            className="w-24"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="product-kind">{t("kind")}</Label>
          <select
            id="product-kind"
            value={kind}
            onChange={(event) => setKind(event.target.value as "sale" | "rental")}
            className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
          >
            <option value="sale">{t("forSale")}</option>
            <option value="rental">{t("forRent")}</option>
          </select>
        </div>
      </div>

      {kind === "rental" && (
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rental-price">{t("rentalPrice")}</Label>
            <Input
              id="rental-price"
              type="number"
              min={0}
              value={rentalPrice}
              onChange={(event) => setRentalPrice(event.target.value)}
              className="w-28"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rental-deposit">{t("deposit")}</Label>
            <Input
              id="rental-deposit"
              type="number"
              min={0}
              value={deposit}
              onChange={(event) => setDeposit(event.target.value)}
              className="w-28"
            />
          </div>
        </div>
      )}

      {category?.is_consumable && (
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="serving-size">{t("servingSize")}</Label>
            <Input
              id="serving-size"
              value={servingSize}
              onChange={(event) => setServingSize(event.target.value)}
              placeholder="500 ml"
              className="w-28"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="calories">{t("calories")}</Label>
            <Input
              id="calories"
              type="number"
              min={0}
              value={calories}
              onChange={(event) => setCalories(event.target.value)}
              className="w-24"
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={perishable}
              onChange={(event) => setPerishable(event.target.checked)}
            />
            {t("perishable")}
          </label>
        </div>
      )}

      <Button size="sm" className="self-start" disabled={busy || !name} onClick={save}>
        {busy ? t("saving") : t("save")}
      </Button>
      {category?.is_consumable && (
        <p className="text-muted-foreground text-xs">{t("perishableHint")}</p>
      )}
    </div>
  );
}
