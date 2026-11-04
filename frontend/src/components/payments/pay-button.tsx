"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import { useRouter } from "next/navigation";

import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";

type Kind = "full" | "advance" | "balance";

/**
 * Start a payment and hand the player to the gateway.
 *
 * `window.location.assign` rather than a router push: the gateway is another origin,
 * and the player is meant to leave. They come back to `/payments/{id}`, which settles
 * the payment itself rather than waiting for the IPN to arrive first.
 */
export function PayButton({
  bookingId,
  orderId,
  kind = "full",
  amount,
  label,
  variant = "default",
}: {
  bookingId?: string;
  orderId?: string;
  kind?: Kind;
  amount?: string | number;
  label?: string;
  variant?: "default" | "outline";
}) {
  const t = useTranslations("payments");
  const api = useApiClient();
  const router = useRouter();

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function pay() {
    setBusy(true);
    setError(null);

    const { data, error: apiError } = await api.POST("/api/v1/payments/start", {
      body: {
        ...(bookingId ? { booking_id: bookingId } : { order_id: orderId }),
        method: "sslcommerz",
        kind,
      } as never,
    });

    if (apiError || !data) {
      setBusy(false);
      setError(firstMessage(apiError) || t("startFailed"));
      return;
    }

    if (data.redirect_url) {
      // Another origin, and the player is meant to leave.
      window.location.assign(data.redirect_url);
      return;
    }

    // No redirect means the provider settled it there and then — unusual, but the
    // result page is still where the player should end up. An internal route, so it
    // goes through the router.
    router.push(`/payments/${data.id}`);
  }

  return (
    <span className="flex flex-col gap-1">
      <Button size="sm" variant={variant} disabled={busy} onClick={pay}>
        {busy ? t("starting") : (label ?? (amount ? t("payAmount", { amount }) : t("payOnline")))}
      </Button>
      {error && (
        <span role="alert" className="text-destructive text-xs">
          {error}
        </span>
      )}
    </span>
  );
}

function firstMessage(error: unknown): string {
  if (!error || typeof error !== "object") return "";
  const first = Object.values(error as Record<string, unknown>)[0];
  return Array.isArray(first) ? String(first[0]) : String(first ?? "");
}
