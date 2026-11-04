import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { Badge } from "@/components/ui/badge";

export const metadata = { title: "Payments · TurfApp" };

/** What the player has paid, and what came back. */
export default async function PaymentsPage() {
  const api = await getServerApiClient();
  const { data } = await api.GET("/api/v1/me/payments");
  const t = await getTranslations("payments");
  const payments = data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
        <p className="text-muted-foreground text-sm">{t("body")}</p>
      </header>

      {payments.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("empty")}</p>
      ) : (
        <ul className="flex flex-col divide-y" data-testid="payment-history">
          {payments.map((payment) => (
            <li key={String(payment.id)}>
              <Link
                href={`/payments/${payment.id}`}
                className="hover:bg-muted/50 -mx-2 flex flex-wrap items-center justify-between gap-2 rounded px-2 py-3 text-sm"
              >
                <span className="min-w-0">
                  <span className="font-medium">{payment.what_for}</span>
                  <span className="text-muted-foreground block text-xs">
                    {payment.method_label} · {payment.kind_label} ·{" "}
                    {new Intl.DateTimeFormat("en-GB", {
                      timeZone: "Asia/Dhaka",
                      day: "numeric",
                      month: "short",
                      year: "numeric",
                    }).format(new Date(payment.created_at))}
                  </span>
                </span>
                <span className="flex items-center gap-2">
                  {Number(payment.refunded) > 0 && (
                    <Badge variant="outline">{t("refunded", { amount: payment.refunded })}</Badge>
                  )}
                  <Badge variant={payment.status === "paid" ? "default" : "outline"}>
                    {payment.status_label}
                  </Badge>
                  <span className="font-mono tabular-nums">৳{payment.amount}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
