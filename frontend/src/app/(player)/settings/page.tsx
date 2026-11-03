import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { fetchClientConfig } from "@/lib/api/config-queries";
import { getServerApiClient } from "@/lib/api/server";

import { SettingsForm } from "./settings-form";

export const metadata = { title: "Settings · TurfApp" };

export default async function SettingsPage() {
  const api = await getServerApiClient();
  const [profile, attributes, sports, config] = await Promise.all([
    api.GET("/api/v1/me/profile"),
    api.GET("/api/v1/attributes"),
    api.GET("/api/v1/sports"),
    fetchClientConfig(),
  ]);

  if (!profile.data) notFound();

  const t = await getTranslations("settings");

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
        <p className="text-muted-foreground text-sm">{t("body")}</p>
      </div>
      <SettingsForm
        profile={profile.data}
        attributes={attributes.data ?? []}
        sports={sports.data ?? []}
        ratingCap={config.self_assessed_rating_cap}
        defaultRating={config.onboarding_default_rating}
        defaultWeightKg={config.default_player_weight_kg}
      />
    </div>
  );
}
