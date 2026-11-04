import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Money } from "@/components/ui/money";

/**
 * Where the gateway sends the player back to.
 *
 * The page does not believe the `result` in the query string — it is in the URL bar and
 * anybody can type it. Reading the payment is what settles it, because the API asks the
 * provider directly. The query string only chooses the wording while that happens.
 */
export default async function PaymentResultPage({
  params,
  searchParams,
}: {
  params: Promise<{ paymentId: string }>;
  searchParams: Promise<{ result?: string; val_id?: string }>;
}) {
  const { paymentId } = await params;
  const { val_id: valId } = await searchParams;

  const api = await getServerApiClient();
  const { data } = await api.GET("/api/v1/payments/{payment_id}", {
    params: { path: { payment_id: paymentId }, query: valId ? { val_id: valId } : {} },
  });

  if (!data) notFound();
  const t = await getTranslations("payments");

  const paid = data.status === "paid";
  const backTo = data.booking
    ? `/bookings/${data.booking}`
    : data.order
      ? `/orders/${data.order}`
      : "/home";

  return (
    <div className="mx-auto flex max-w-xl flex-col gap-6" data-testid="payment-result">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          {paid ? t("doneHeading") : t("notDoneHeading")}
        </h1>
        <p className="text-muted-foreground text-sm">{paid ? t("doneBody") : t("notDoneBody")}</p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{data.what_for}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <div className="flex items-baseline justify-between">
            <span className="text-muted-foreground">{t("amount")}</span>
            <Money amount={data.amount} className="text-lg font-semibold" />
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-muted-foreground">{t("kind")}</span>
            <span>{data.kind_label}</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span className="text-muted-foreground">{t("status")}</span>
            <Badge variant={paid ? "default" : "outline"} data-testid="payment-status">
              {data.status_label}
            </Badge>
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2">
        <Button size="sm" asChild>
          <Link href={backTo}>{t("backToIt")}</Link>
        </Button>
        <Button size="sm" variant="ghost" asChild>
          <Link href="/payments">{t("allPayments")}</Link>
        </Button>
      </div>
    </div>
  );
}
