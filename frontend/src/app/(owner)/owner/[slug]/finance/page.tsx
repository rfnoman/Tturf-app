import Link from "next/link";
import { notFound } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API_BASE_URL } from "@/lib/api/config";
import { Money } from "@/components/ui/money";
import { formatWhen } from "@/i18n/formats";

export const metadata = { title: "Finance · TurfApp" };

/** What a turf has earned, what the platform took, and what is owed. */
export default async function FinancePage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ from?: string; to?: string }>;
}) {
  const { slug } = await params;
  const { from, to } = await searchParams;

  const api = await getServerApiClient();
  const query = { ...(from ? { from } : {}), ...(to ? { to } : {}) };
  const [turf, statement, payouts] = await Promise.all([
    api.GET("/api/v1/me/turfs/{slug}", { params: { path: { slug } } }),
    api.GET("/api/v1/me/turfs/{slug}/finance", {
      params: { path: { slug }, query: query as never },
    }),
    api.GET("/api/v1/me/turfs/{slug}/payouts", { params: { path: { slug } } }),
  ]);

  if (!turf.data || !statement.data) notFound();
  const t = await getTranslations("finance");
  const locale = await getLocale();
  const data = statement.data;

  const csv = new URL(`${API_BASE_URL}/api/v1/me/turfs/${slug}/finance.csv`);
  if (from) csv.searchParams.set("from", from);
  if (to) csv.searchParams.set("to", to);

  const when = (value: string) => formatWhen(`${value}T12:00:00+06:00`, locale, "dayMonth");

  return (
    <div className="flex flex-col gap-6" data-testid="finance">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
          <p className="text-muted-foreground text-sm">
            {turf.data.name} · {when(data.period_start)} – {when(data.period_end)}
          </p>
        </div>
        <Button size="sm" variant="ghost" asChild>
          <Link href={`/owner/${slug}`}>{t("backToTurf")}</Link>
        </Button>
      </header>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("earned")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            <p className="font-mono text-3xl font-bold tabular-nums" data-testid="finance-total">
              <Money amount={data.total} />
            </p>
            <ul className="flex flex-col gap-1 text-sm">
              {Object.entries(data.by_type ?? {}).map(([type, amount]) => (
                <li key={type} className="flex items-baseline justify-between">
                  <span className="text-muted-foreground">{t("entryType", { type })}</span>
                  <Money amount={amount} />
                </li>
              ))}
            </ul>
            <p className="text-muted-foreground text-xs">{t("afterCommission")}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("payouts")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {(payouts.data ?? []).length === 0 ? (
              <p className="text-muted-foreground text-sm">{t("noPayouts")}</p>
            ) : (
              <ul className="flex flex-col gap-1.5 text-sm">
                {(payouts.data ?? []).map((payout) => (
                  <li key={String(payout.id)} className="flex items-center justify-between gap-2">
                    <span className="text-muted-foreground text-xs">
                      {when(payout.period_start)} – {when(payout.period_end)}
                    </span>
                    <span className="flex items-center gap-2">
                      <Badge variant={payout.status === "sent" ? "default" : "outline"}>
                        {payout.status_label}
                      </Badge>
                      <Money amount={payout.amount} />
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <Button size="sm" variant="outline" className="mt-2 self-start" asChild>
              <a href={csv.toString()}>{t("download")}</a>
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("lines")}</CardTitle>
        </CardHeader>
        <CardContent>
          {data.entries.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("noLines")}</p>
          ) : (
            <ul className="flex flex-col divide-y text-sm" data-testid="finance-lines">
              {data.entries.map((entry) => (
                <li key={String(entry.id)} className="flex flex-wrap items-baseline gap-2 py-2">
                  <span className="text-muted-foreground font-mono text-xs tabular-nums">
                    {when(entry.occurred_on)}
                  </span>
                  <span className="min-w-0 flex-1 truncate">
                    {entry.type_label}
                    {entry.note && <span className="text-muted-foreground"> · {entry.note}</span>}
                  </span>
                  <Money amount={entry.amount} />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
