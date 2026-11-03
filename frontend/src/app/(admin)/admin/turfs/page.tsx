import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";

import { TurfReviewQueue } from "./review-queue";

export const metadata = { title: "Turfs · TurfApp admin" };

export default async function AdminTurfsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  // `searchParams` is a promise in Next 16.
  const { status } = await searchParams;

  const api = await getServerApiClient();
  const { data } = await api.GET("/api/v1/admin/turfs", {
    params: { query: status ? { status } : {} },
  });

  const t = await getTranslations("adminTurfs");

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
        <p className="text-muted-foreground text-sm">{t("body")}</p>
      </div>
      <nav className="flex flex-wrap gap-2 text-sm" aria-label={t("filter")}>
        {["pending_review", "approved", "rejected", "suspended", "draft"].map((option) => (
          <a
            key={option}
            href={`/admin/turfs?status=${option}`}
            className={
              (status ?? "pending_review") === option
                ? "bg-primary text-primary-foreground rounded-lg px-2.5 py-1 text-xs"
                : "hover:bg-muted rounded-lg px-2.5 py-1 text-xs"
            }
          >
            {t(`status.${option}`)}
          </a>
        ))}
      </nav>
      <TurfReviewQueue turfs={data?.results ?? []} />
    </div>
  );
}
