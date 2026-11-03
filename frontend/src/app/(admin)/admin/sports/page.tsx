import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";

import { ProposalQueue } from "./proposal-queue";

export const metadata = { title: "Sports · TurfApp admin" };

export default async function AdminSportsPage() {
  const api = await getServerApiClient();
  const [proposals, sports] = await Promise.all([
    api.GET("/api/v1/admin/sport-proposals"),
    api.GET("/api/v1/sports", { params: { query: { include_inactive: true } } }),
  ]);

  const t = await getTranslations("adminSports");

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
        <p className="text-muted-foreground text-sm">{t("body")}</p>
      </div>

      <ProposalQueue proposals={proposals.data?.results ?? []} sports={sports.data ?? []} />

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold">{t("catalogue")}</h2>
        <ul className="divide-y rounded-lg border text-sm">
          {(sports.data ?? []).map((sport) => (
            <li key={sport.id} className="flex items-center justify-between gap-3 px-3 py-2">
              <span className="flex items-center gap-2">
                <span aria-hidden>{sport.icon}</span>
                {sport.name}
              </span>
              <span className="text-muted-foreground text-xs">
                {t("catalogueMeta", {
                  formats: sport.formats.length,
                  skills: sport.skills.length,
                  stats: sport.stat_definitions.length,
                })}
                {sport.is_active ? "" : ` · ${t("inactive")}`}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
