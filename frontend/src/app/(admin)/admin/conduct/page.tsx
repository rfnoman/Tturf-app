import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { ConductQueue } from "./conduct-queue";

export const metadata = { title: "Conduct reports · TurfApp" };

/** The review queue. Nothing a report says counts until it is upheld (DOMAIN §8). */
export default async function ConductPage() {
  const api = await getServerApiClient();
  const { data } = await api.GET("/api/v1/admin/conduct-reports");
  const t = await getTranslations("adminConduct");

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
        <p className="text-muted-foreground text-sm">{t("body")}</p>
      </header>

      <ConductQueue reports={data ?? []} />
    </div>
  );
}
