"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";

import type { Payout, Refund } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** Draft what a turf is owed, then record the transfer once it has actually happened. */
export function PayoutBoard({
  payouts,
  refunds,
  turfs,
}: {
  payouts: Payout[];
  refunds: Refund[];
  turfs: { slug: string; name: string }[];
}) {
  const t = useTranslations("finance");
  const router = useRouter();
  const api = useApiClient();

  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Dhaka" }).format(new Date());
  const firstOfMonth = `${today.slice(0, 8)}01`;

  const [turf, setTurf] = useState(turfs[0]?.slug ?? "");
  const [from, setFrom] = useState(firstOfMonth);
  const [to, setTo] = useState(today);
  const [reference, setReference] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function draft() {
    setBusy(true);
    setError(null);
    const { error: apiError } = await api.POST("/api/v1/admin/payouts", {
      body: { turf, period_start: from, period_end: to } as never,
    });
    setBusy(false);
    if (apiError) {
      setError(firstMessage(apiError) || t("failed"));
      return;
    }
    router.refresh();
  }

  async function send(payoutId: string) {
    setBusy(true);
    setError(null);
    const { error: apiError } = await api.POST("/api/v1/admin/payouts/{payout_id}/send", {
      params: { path: { payout_id: payoutId } },
      body: { reference: reference[payoutId] ?? "" } as never,
    });
    setBusy(false);
    if (apiError) {
      setError(t("failed"));
      return;
    }
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("draftPayout")}</CardTitle>
          <p className="text-muted-foreground text-xs">{t("draftHint")}</p>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="payout-turf">{t("turf")}</Label>
            <select
              id="payout-turf"
              value={turf}
              onChange={(event) => setTurf(event.target.value)}
              className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
            >
              {turfs.map((option) => (
                <option key={option.slug} value={option.slug}>
                  {option.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="payout-from">{t("from")}</Label>
            <Input
              id="payout-from"
              type="date"
              value={from}
              onChange={(event) => setFrom(event.target.value)}
              className="w-40"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="payout-to">{t("to")}</Label>
            <Input
              id="payout-to"
              type="date"
              value={to}
              onChange={(event) => setTo(event.target.value)}
              className="w-40"
            />
          </div>
          <Button size="sm" disabled={busy || !turf} onClick={draft}>
            {t("draft")}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("payouts")}</CardTitle>
        </CardHeader>
        <CardContent>
          {payouts.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("noPayouts")}</p>
          ) : (
            <ul className="flex flex-col divide-y" data-testid="payout-list">
              {payouts.map((payout) => {
                const id = String(payout.id);
                return (
                  <li
                    key={id}
                    className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm"
                  >
                    <span className="min-w-0">
                      <span className="font-medium">{payout.turf_name}</span>
                      <span className="text-muted-foreground text-xs">
                        {" · "}
                        {payout.period_start} – {payout.period_end}
                      </span>
                    </span>
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="font-mono tabular-nums">৳{payout.amount}</span>
                      {payout.status === "sent" ? (
                        <Badge>{payout.status_label}</Badge>
                      ) : (
                        <>
                          <Input
                            aria-label={t("reference")}
                            placeholder={t("referencePlaceholder")}
                            value={reference[id] ?? ""}
                            onChange={(event) =>
                              setReference((current) => ({ ...current, [id]: event.target.value }))
                            }
                            className="h-8 w-36"
                          />
                          <Button size="xs" disabled={busy} onClick={() => send(id)}>
                            {t("markSent")}
                          </Button>
                        </>
                      )}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("refunds")}</CardTitle>
        </CardHeader>
        <CardContent>
          {refunds.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("noRefunds")}</p>
          ) : (
            <ul className="flex flex-col divide-y text-sm" data-testid="refund-list">
              {refunds.map((refund) => (
                <li key={String(refund.id)} className="flex flex-wrap items-baseline gap-2 py-2">
                  <span className="font-mono tabular-nums">৳{refund.amount}</span>
                  <span className="text-muted-foreground min-w-0 flex-1 truncate">
                    {refund.reason}
                  </span>
                  <Badge variant={refund.status === "done" ? "default" : "outline"}>
                    {refund.status_label}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function firstMessage(error: unknown): string {
  if (!error || typeof error !== "object") return "";
  const first = Object.values(error as Record<string, unknown>)[0];
  return Array.isArray(first) ? String(first[0]) : String(first ?? "");
}
