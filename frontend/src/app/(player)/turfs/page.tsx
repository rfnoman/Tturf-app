import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";

import { TurfDiscovery } from "./discovery";

export const metadata = { title: "Find a turf · TurfApp" };

export default async function TurfsPage() {
  const api = await getServerApiClient();
  const [turfs, sports] = await Promise.all([api.GET("/api/v1/turfs"), api.GET("/api/v1/sports")]);

  const t = await getTranslations("turfs");
  const results = turfs.data?.results ?? [];
  // Areas come from the turfs themselves rather than a fixed list, so a new
  // neighbourhood appears in the filter the moment a turf there is approved.
  const areas = [...new Set(results.map((turf) => turf.area))].sort();

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
        <p className="text-muted-foreground text-sm">{t("body")}</p>
      </div>
      <TurfDiscovery initialTurfs={results} sports={sports.data ?? []} areas={areas} />
    </div>
  );
}
