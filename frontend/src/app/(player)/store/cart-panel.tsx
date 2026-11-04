"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import type { Cart, FulfilmentOption, MatchSummary, StoreAddress } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Money } from "@/components/ui/money";

type Choices = Record<string, string>;

/**
 * The cart, grouped by source, with a fulfilment choice per group.
 *
 * Unavailable options are shown rather than hidden, with the reason the API gave. A
 * shopper who cannot work out why delivery is missing assumes the app is broken; one
 * who reads "orders have to be in 16 hours before kick-off" knows what to do next time.
 */
export function CartPanel({
  cart,
  addresses,
  matches,
  onChanged,
  onPlaced,
}: {
  cart?: Cart;
  addresses: StoreAddress[];
  matches: MatchSummary[];
  onChanged: () => void | Promise<void>;
  onPlaced: (orderId: string) => void;
}) {
  const t = useTranslations("store");
  const api = useApiClient();

  const [choices, setChoices] = useState<Choices>({});
  const [addressId, setAddressId] = useState(
    String(addresses.find((address) => address.is_default)?.id ?? addresses[0]?.id ?? ""),
  );
  const [matchId, setMatchId] = useState(String(matches[0]?.id ?? ""));
  const [priced, setPriced] = useState<Cart | undefined>(cart);
  const [known, setKnown] = useState<StoreAddress[]>(addresses);
  const [addingAddress, setAddingAddress] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Re-price whenever the address or match changes: the fee and the cutoff depend on
  // both, and the server is the only thing that knows the rules.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const query: Record<string, string> = {};
      if (addressId) query.address = addressId;
      if (matchId) query.match = matchId;
      const { data } = await api.GET("/api/v1/store/cart", {
        params: { query: query as never },
      });
      if (!cancelled) setPriced(data);
    })();
    return () => {
      cancelled = true;
    };
  }, [api, addressId, matchId, cart]);

  const groups = priced?.groups ?? [];

  async function setQuantity(stockItemId: string, quantity: number) {
    setBusy(true);
    setError(null);
    const { error: apiError } = await api.PATCH("/api/v1/store/cart", {
      body: { stock_item_id: stockItemId, quantity } as never,
    });
    setBusy(false);
    if (apiError) {
      setError(t("failed"));
      return;
    }
    await onChanged();
  }

  async function placeOrder() {
    setBusy(true);
    setError(null);

    const payload = groups.map((group) => {
      const kind = choices[String(group.source_id)] ?? defaultChoice(group.options);
      return {
        source_id: group.source_id,
        fulfilment: kind,
        ...(kind === "deliver_to_address" ? { address_id: addressId } : {}),
        ...(kind === "deliver_to_turf" ? { match_id: matchId } : {}),
      };
    });

    const {
      data,
      error: apiError,
      response,
    } = await api.POST("/api/v1/store/checkout", {
      body: { choices: payload } as never,
    });
    setBusy(false);

    if (apiError || !data) {
      setError(
        response?.status === 409
          ? t("soldOutCheckout")
          : firstMessage(apiError) || t("checkoutFailed"),
      );
      await onChanged();
      return;
    }

    await onChanged();
    onPlaced(String(data[0].id));
  }

  const total = groups.reduce((sum, group) => {
    const kind = choices[String(group.source_id)] ?? defaultChoice(group.options);
    const option = group.options.find((item) => item.kind === kind);
    return sum + Number(group.subtotal) + Number(option?.fee ?? 0);
  }, 0);

  const ready =
    groups.length > 0 &&
    groups.every((group) => {
      const kind = choices[String(group.source_id)] ?? defaultChoice(group.options);
      const option = group.options.find((item) => item.kind === kind);
      return option?.available;
    });

  return (
    <Card className="h-fit lg:sticky lg:top-4" data-testid="cart">
      <CardHeader>
        <CardTitle className="text-sm">{t("cart")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {error && (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        )}

        {groups.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t("cartEmpty")}</p>
        ) : (
          groups.map((group) => {
            const chosen = choices[String(group.source_id)] ?? defaultChoice(group.options);
            return (
              <div
                key={String(group.source_id)}
                className="flex flex-col gap-2 border-b pb-4 last:border-b-0"
              >
                <p className="text-sm font-medium">
                  {group.is_platform ? t("platform") : group.source_name}
                </p>

                <ul className="flex flex-col gap-1 text-sm">
                  {group.items.map((line) => (
                    <li key={String(line.id)} className="flex items-center gap-2">
                      <span className="min-w-0 flex-1 truncate">{line.product.name}</span>
                      <span className="flex items-center gap-1">
                        <Button
                          size="xs"
                          variant="outline"
                          aria-label={t("oneFewer", { product: line.product.name })}
                          disabled={busy}
                          onClick={() => setQuantity(String(line.stock_item_id), line.quantity - 1)}
                        >
                          −
                        </Button>
                        <span className="w-5 text-center font-mono tabular-nums">
                          {line.quantity}
                        </span>
                        <Button
                          size="xs"
                          variant="outline"
                          aria-label={t("oneMore", { product: line.product.name })}
                          disabled={busy || line.quantity >= line.available}
                          onClick={() => setQuantity(String(line.stock_item_id), line.quantity + 1)}
                        >
                          +
                        </Button>
                      </span>
                      <span className="w-14 text-right font-mono tabular-nums">
                        <Money amount={line.line_total} />
                      </span>
                    </li>
                  ))}
                </ul>

                <div className="flex flex-col gap-1.5">
                  <Label className="text-xs">{t("howToGetIt")}</Label>
                  <div className="flex flex-col gap-1">
                    {group.options.map((option) => (
                      <label
                        key={option.kind}
                        className="flex items-start gap-2 text-xs"
                        title={option.reason}
                      >
                        <input
                          type="radio"
                          name={`fulfilment-${group.source_id}`}
                          value={option.kind}
                          checked={chosen === option.kind}
                          disabled={!option.available}
                          onChange={() =>
                            setChoices((current) => ({
                              ...current,
                              [String(group.source_id)]: option.kind,
                            }))
                          }
                          className="mt-0.5"
                        />
                        <span className={option.available ? "" : "text-muted-foreground"}>
                          {t("fulfilment", { kind: option.kind })}
                          {option.available && Number(option.fee) > 0 && (
                            <>
                              {" · "}
                              <Money amount={option.fee} />
                            </>
                          )}
                          {!option.available && option.reason && (
                            <span className="block">{option.reason}</span>
                          )}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            );
          })
        )}

        {groups.length > 0 && (
          <>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cart-address" className="text-xs">
                {t("address")}
              </Label>
              {known.length > 0 && (
                <select
                  id="cart-address"
                  value={addressId}
                  onChange={(event) => setAddressId(event.target.value)}
                  className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
                >
                  {known.map((address) => (
                    <option key={String(address.id)} value={String(address.id)}>
                      {address.label || address.area}: {address.line}
                    </option>
                  ))}
                </select>
              )}
              {addingAddress ? (
                <AddressForm
                  onSaved={(address) => {
                    setKnown((current) => [...current, address]);
                    setAddressId(String(address.id));
                    setAddingAddress(false);
                  }}
                  onCancel={() => setAddingAddress(false)}
                />
              ) : (
                <Button
                  size="xs"
                  variant="ghost"
                  className="self-start"
                  onClick={() => setAddingAddress(true)}
                >
                  {known.length > 0 ? t("addAnotherAddress") : t("addAddress")}
                </Button>
              )}
            </div>

            {matches.length > 0 && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="cart-match" className="text-xs">
                  {t("forMatch")}
                </Label>
                <select
                  id="cart-match"
                  value={matchId}
                  onChange={(event) => setMatchId(event.target.value)}
                  className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
                >
                  {matches.map((match) => (
                    <option key={String(match.id)} value={String(match.id)}>
                      {match.sport.name} · {match.turf_name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="flex items-baseline justify-between border-t pt-3">
              <span className="text-sm font-medium">{t("total")}</span>
              <span className="font-mono text-xl font-bold tabular-nums" data-testid="cart-total">
                <Money amount={total} />
              </span>
            </div>

            <Button size="lg" className="w-full" disabled={busy || !ready} onClick={placeOrder}>
              {busy ? t("placing") : t("placeOrder")}
            </Button>
            <p className="text-muted-foreground text-xs">{t("payOnArrival")}</p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

/** The first option a player can actually take. */
function defaultChoice(options: FulfilmentOption[]): string {
  return options.find((option) => option.available)?.kind ?? options[0]?.kind ?? "";
}

function firstMessage(error: unknown): string {
  if (!error || typeof error !== "object") return "";
  const values = Object.values(error as Record<string, unknown>);
  const first = values[0];
  return Array.isArray(first) ? String(first[0]) : String(first ?? "");
}

/** Somewhere to deliver to, added without leaving the cart. */
function AddressForm({
  onSaved,
  onCancel,
}: {
  onSaved: (address: StoreAddress) => void;
  onCancel: () => void;
}) {
  const t = useTranslations("store");
  const api = useApiClient();

  const [line, setLine] = useState("");
  const [area, setArea] = useState("");
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="flex flex-col gap-2 rounded-lg border p-2" data-testid="address-form">
      {error && (
        <p role="alert" className="text-destructive text-xs">
          {error}
        </p>
      )}
      <Input
        aria-label={t("addressLine")}
        value={line}
        onChange={(event) => setLine(event.target.value)}
        placeholder={t("addressLinePlaceholder")}
        className="h-8"
      />
      <Input
        aria-label={t("area")}
        value={area}
        onChange={(event) => setArea(event.target.value)}
        placeholder={t("areaPlaceholder")}
        className="h-8"
      />
      <Input
        aria-label={t("phone")}
        value={phone}
        onChange={(event) => setPhone(event.target.value)}
        placeholder="+8801…"
        className="h-8"
      />
      <div className="flex gap-2">
        <Button
          size="xs"
          disabled={busy || !line || !area}
          onClick={async () => {
            setBusy(true);
            setError(null);
            const { data, error: apiError } = await api.POST("/api/v1/me/addresses", {
              body: { label: t("home"), line, area, phone } as never,
            });
            setBusy(false);
            if (apiError || !data) {
              setError(t("addressFailed"));
              return;
            }
            onSaved(data);
          }}
        >
          {t("saveAddress")}
        </Button>
        <Button size="xs" variant="ghost" onClick={onCancel}>
          {t("cancel")}
        </Button>
      </div>
      <p className="text-muted-foreground text-xs">{t("areaHint")}</p>
    </div>
  );
}
