import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { RiderList } from "./rider-list";

export const metadata = { title: "My deliveries · TurfApp" };

/**
 * A rider's round, on a phone.
 *
 * Deliberately inside the player area: a rider is a player with a rider profile, not a
 * separate kind of account (CLAUDE.md — roles are permissions on one account).
 */
export default async function RiderPage() {
  const api = await getServerApiClient();
  const { data } = await api.GET("/api/v1/me/deliveries");
  const t = await getTranslations("rider");

  return (
    <div className="flex flex-col gap-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
        <p className="text-muted-foreground text-sm">{t("body")}</p>
      </header>

      <RiderList orders={data ?? []} />
    </div>
  );
}
