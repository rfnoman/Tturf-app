"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";

import type { ProductCategory, StockItem } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** Add a product to the platform catalogue, and receive stock against it. */
export function Warehouse({
  stock,
  categories,
}: {
  stock: StockItem[];
  categories: ProductCategory[];
}) {
  const t = useTranslations("warehouse");
  const router = useRouter();
  const api = useApiClient();

  const [name, setName] = useState("");
  const [categorySlug, setCategorySlug] = useState(categories[0]?.slug ?? "");
  const [price, setPrice] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [quantities, setQuantities] = useState<Record<string, string>>({});

  async function addProduct() {
    setBusy("add");
    setError(null);
    const { error: apiError } = await api.POST("/api/v1/admin/warehouse/products", {
      body: { category: categorySlug, name, base_price: price || "0.00" } as never,
    });
    setBusy(null);
    if (apiError) {
      setError(t("failed"));
      return;
    }
    setName("");
    setPrice("");
    router.refresh();
  }

  async function receive(itemId: string) {
    const quantity = Number(quantities[itemId] ?? 0);
    if (!quantity) return;
    setBusy(itemId);
    setError(null);
    const { error: apiError } = await api.POST("/api/v1/admin/warehouse/stock/{item_id}/receive", {
      params: { path: { item_id: itemId } },
      body: { quantity } as never,
    });
    setBusy(null);
    if (apiError) {
      setError(t("failed"));
      return;
    }
    setQuantities((current) => ({ ...current, [itemId]: "" }));
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
          <CardTitle className="text-sm">{t("addHeading")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="warehouse-name">{t("name")}</Label>
            <Input
              id="warehouse-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="w-48"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="warehouse-category">{t("category")}</Label>
            <select
              id="warehouse-category"
              value={categorySlug}
              onChange={(event) => setCategorySlug(event.target.value)}
              className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
            >
              {categories.map((category) => (
                <option key={category.slug} value={category.slug}>
                  {category.icon} {category.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="warehouse-price">{t("price")}</Label>
            <Input
              id="warehouse-price"
              type="number"
              min={0}
              step="0.01"
              value={price}
              onChange={(event) => setPrice(event.target.value)}
              className="w-28"
            />
          </div>
          <Button size="sm" disabled={busy !== null || !name} onClick={addProduct}>
            {t("add")}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("stock")}</CardTitle>
        </CardHeader>
        <CardContent>
          {stock.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("empty")}</p>
          ) : (
            <ul className="flex flex-col divide-y" data-testid="warehouse-stock">
              {stock.map((item) => (
                <li
                  key={String(item.id)}
                  className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
                >
                  <span className="min-w-0 flex-1 truncate">
                    {item.product.name}
                    <span className="text-muted-foreground"> · ৳{item.price}</span>
                    {item.is_low && (
                      <Badge variant="destructive" className="ml-2 text-[10px]">
                        {t("low")}
                      </Badge>
                    )}
                  </span>
                  <span className="font-mono tabular-nums">{item.available}</span>
                  <span className="flex items-center gap-1.5">
                    <Input
                      aria-label={t("receiveFor", { product: item.product.name })}
                      type="number"
                      min={1}
                      value={quantities[String(item.id)] ?? ""}
                      onChange={(event) =>
                        setQuantities((current) => ({
                          ...current,
                          [String(item.id)]: event.target.value,
                        }))
                      }
                      className="h-7 w-20"
                    />
                    <Button
                      size="xs"
                      disabled={busy !== null}
                      onClick={() => receive(String(item.id))}
                    >
                      {t("receive")}
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
