import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { PayoutBoard } from "./payout-board";

export const metadata = { title: "Finance · TurfApp" };

/** The platform's position, the refunds, and the money it owes turfs. */
export default async function AdminFinancePage() {
  const api = await getServerApiClient();
  const [finance, payouts, refunds, turfs] = await Promise.all([
    api.GET("/api/v1/admin/finance"),
    api.GET("/api/v1/admin/payouts"),
    api.GET("/api/v1/admin/refunds"),
    // `status=approved`: the bare admin list is the *review queue*, which is pending
    // turfs — and a pending turf has earned nothing to pay out.
    api.GET("/api/v1/admin/turfs", { params: { query: { status: "approved" } } }),
  ]);

  const t = await getTranslations("finance");
  const data = finance.data;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("adminHeading")}</h1>
        <p className="text-muted-foreground text-sm">{t("adminBody")}</p>
      </header>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("platformEarned")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-mono text-2xl font-bold tabular-nums" data-testid="platform-total">
              ৳{data?.platform ?? 0}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("owedToTurfs")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-mono text-2xl font-bold tabular-nums">৳{data?.owed_to_turfs ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("deliveryFees")}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="font-mono text-2xl font-bold tabular-nums">৳{data?.delivery ?? 0}</p>
          </CardContent>
        </Card>
      </div>

      <PayoutBoard
        payouts={payouts.data ?? []}
        refunds={refunds.data ?? []}
        turfs={(turfs.data?.results ?? []).map((turf) => ({ slug: turf.slug, name: turf.name }))}
      />
    </div>
  );
}
