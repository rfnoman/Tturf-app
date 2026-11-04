"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { cn } from "cn";

import type { Cart, MatchSummary, ProductCategory, StoreAddress, StoreItem } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { CartPanel } from "./cart-panel";

type Home = {
  match: {
    id: string;
    sport: string;
    turf_name: string;
    turf_slug: string;
    starts_at: string;
    source_id: string | null;
  } | null;
  platform_source_id: string;
  sources: { id: string; name: string; turf_slug: string; is_platform: boolean }[];
};

/** Hours until a moment, or a negative number once it has passed. */
function hoursUntil(when: string): number {
  return (new Date(when).getTime() - Date.now()) / 3_600_000;
}

export function StoreBrowser({
  home,
  categories,
  initialCart,
  addresses,
  matches,
}: {
  home?: Home;
  categories: ProductCategory[];
  initialCart?: Cart;
  addresses: StoreAddress[];
  matches: MatchSummary[];
}) {
  const t = useTranslations("store");
  const api = useApiClient();
  const router = useRouter();

  const match = home?.match ?? null;
  // The match's turf first: that is the section the page is built around.
  const [source, setSource] = useState(match?.source_id ?? home?.platform_source_id ?? "platform");
  const [category, setCategory] = useState("");
  const [tag, setTag] = useState("");
  const [search, setSearch] = useState("");
  // Results are stored with the query that produced them, so `loading` is derived
  // rather than set — which keeps setState out of the effect body and means one
  // source's products never appear under another's heading.
  const [loaded, setLoaded] = useState<{ key: string; items: StoreItem[] }>();
  const [cart, setCart] = useState<Cart | undefined>(initialCart);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sources = home?.sources ?? [];

  const queryKey = `${source}|${category}|${tag}|${search}`;
  const loading = loaded?.key !== queryKey;
  const items = loaded?.key === queryKey ? loaded.items : [];

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const query: Record<string, string> = { source };
      if (category) query.category = category;
      if (tag) query.tag = tag;
      if (search) query.q = search;

      const { data } = await api.GET("/api/v1/store/items", {
        params: { query: query as never },
      });
      if (!cancelled) {
        setLoaded({ key: `${source}|${category}|${tag}|${search}`, items: data ?? [] });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [api, source, category, tag, search]);

  const refreshCart = useCallback(async () => {
    const { data } = await api.GET("/api/v1/store/cart");
    setCart(data);
  }, [api]);

  async function add(item: StoreItem) {
    setBusy(String(item.stock_item_id));
    setError(null);
    const {
      data,
      error: apiError,
      response,
    } = await api.POST("/api/v1/store/cart", {
      body: { stock_item_id: item.stock_item_id, quantity: 1 } as never,
    });
    setBusy(null);
    if (apiError || !data) {
      setError(response?.status === 409 ? t("soldOut") : t("failed"));
      return;
    }
    setCart(data);
  }

  const inCart = useMemo(() => {
    const counts = new Map<string, number>();
    for (const group of cart?.groups ?? []) {
      for (const line of group.items) {
        counts.set(String(line.stock_item_id), line.quantity);
      }
    }
    return counts;
  }, [cart]);

  const cutoffHours = match ? hoursUntil(match.starts_at) : null;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
      <div className="flex flex-col gap-5">
        {match && (
          <Card className="border-primary/40" data-testid="match-hero">
            <CardHeader>
              <CardTitle className="text-sm">
                {t("forYourMatch", { turf: match.turf_name })}
              </CardTitle>
              <p className="text-muted-foreground text-xs">
                {match.sport} ·{" "}
                {new Intl.DateTimeFormat("en-GB", {
                  timeZone: "Asia/Dhaka",
                  weekday: "short",
                  day: "numeric",
                  month: "short",
                  hour: "2-digit",
                  minute: "2-digit",
                }).format(new Date(match.starts_at))}
              </p>
            </CardHeader>
            <CardContent className="flex flex-wrap items-center gap-2">
              {match.source_id && (
                <Button
                  size="sm"
                  variant={source === match.source_id ? "default" : "outline"}
                  onClick={() => setSource(match.source_id!)}
                >
                  {t("shopAtTurf", { turf: match.turf_name })}
                </Button>
              )}
              <Button
                size="sm"
                variant={source === home?.platform_source_id ? "default" : "outline"}
                onClick={() => setSource(home!.platform_source_id)}
              >
                {t("shopPlatform")}
              </Button>
              {cutoffHours !== null && (
                <span className="text-muted-foreground text-xs" data-testid="cutoff">
                  {cutoffHours > 16
                    ? t("cutoffOpen", { hours: Math.floor(cutoffHours - 16) })
                    : t("cutoffPassed")}
                </span>
              )}
            </CardContent>
          </Card>
        )}

        <div className="flex flex-wrap items-end gap-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="store-source">{t("source")}</Label>
            <select
              id="store-source"
              value={source}
              onChange={(event) => setSource(event.target.value)}
              className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
            >
              {sources.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.is_platform ? t("platform") : option.name}
                </option>
              ))}
            </select>
          </div>

          <Input
            aria-label={t("search")}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t("searchPlaceholder")}
            className="w-40"
          />

          <Button
            size="sm"
            variant={category === "" ? "default" : "outline"}
            onClick={() => setCategory("")}
          >
            {t("all")}
          </Button>
          {categories.map((item) => (
            <Button
              key={item.slug}
              size="sm"
              variant={category === item.slug ? "default" : "outline"}
              onClick={() => setCategory(item.slug)}
            >
              {item.icon} {item.label}
            </Button>
          ))}

          <select
            aria-label={t("tag")}
            value={tag}
            onChange={(event) => setTag(event.target.value)}
            className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
          >
            <option value="">{t("anyTag")}</option>
            {["hydration", "recovery", "pre_match", "protein", "low_sugar", "vegan"].map(
              (value) => (
                <option key={value} value={value}>
                  {t("tagName", { tag: value })}
                </option>
              ),
            )}
          </select>
        </div>

        {error && (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        )}

        {loading ? (
          <p className="text-muted-foreground text-sm">{t("loading")}</p>
        ) : items.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t("nothing")}</p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="store-items">
            {items.map((item) => {
              const id = String(item.stock_item_id);
              const count = inCart.get(id) ?? 0;
              const nutrition = item.product.nutrition;
              return (
                <li key={id}>
                  <Card className="h-full">
                    <CardContent className="flex h-full flex-col gap-2 py-4">
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-sm font-medium">{item.product.name}</span>
                        <span className="font-mono text-base font-semibold tabular-nums">
                          ৳{item.price}
                        </span>
                      </div>

                      {(item.product.tags ?? []).length > 0 && (
                        <span className="flex flex-wrap gap-1">
                          {item.product.tags.map((value) => (
                            <Badge key={value} variant="secondary" className="text-[10px]">
                              {t("tagName", { tag: value })}
                            </Badge>
                          ))}
                        </span>
                      )}

                      {nutrition?.calories != null && (
                        <p className="text-muted-foreground text-xs">
                          {t("nutrition", {
                            calories: nutrition.calories,
                            serving: nutrition.serving_size || "",
                          })}
                          {nutrition.protein_g != null && ` · ${nutrition.protein_g}g protein`}
                        </p>
                      )}

                      <div className="mt-auto flex items-center justify-between gap-2 pt-2">
                        <span className="text-muted-foreground text-xs">
                          {t("left", { count: item.available })}
                        </span>
                        <Button
                          size="sm"
                          disabled={busy !== null || item.available <= 0}
                          onClick={() => add(item)}
                          className={cn(count > 0 && "ring-primary/30 ring-2")}
                        >
                          {count > 0 ? t("addedCount", { count }) : t("add")}
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <CartPanel
        cart={cart}
        addresses={addresses}
        matches={matches}
        onChanged={refreshCart}
        onPlaced={(orderId) => router.push(`/orders/${orderId}`)}
      />
    </div>
  );
}
