import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { ActivityBoard } from "./activity-board";

export const metadata = { title: "Activity · TurfApp" };

/** Everything the player has done, and what they are aiming at. */
export default async function ActivityPage() {
  const api = await getServerApiClient();
  const [dashboard, logs, sports] = await Promise.all([
    api.GET("/api/v1/me/dashboard"),
    api.GET("/api/v1/me/activity", { params: { query: { days: 90 } } }),
    api.GET("/api/v1/sports"),
  ]);

  const t = await getTranslations("fitness");

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("activityHeading")}</h1>
        <p className="text-muted-foreground text-sm">{t("activityBody")}</p>
      </header>

      <ActivityBoard
        week={dashboard.data?.week}
        streak={dashboard.data?.streak}
        goals={dashboard.data?.goals ?? []}
        logs={logs.data ?? []}
        sports={sports.data ?? []}
      />
    </div>
  );
}
