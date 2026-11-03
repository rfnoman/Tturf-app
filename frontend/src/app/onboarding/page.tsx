import { redirect } from "next/navigation";
import { auth } from "@clerk/nextjs/server";
import { getTranslations } from "next-intl/server";

import { fetchClientConfig } from "@/lib/api/config-queries";
import { getServerApiClient } from "@/lib/api/server";

import { OnboardingWizard } from "./onboarding-wizard";

export const metadata = { title: "Set up your profile · TurfApp" };

/**
 * The onboarding wizard lives outside the `(player)` route group on purpose: that
 * group's layout redirects unfinished profiles *here*, so a page inside it would loop.
 */
export default async function OnboardingPage() {
  await auth.protect();

  const api = await getServerApiClient();
  const [profile, sports, attributes, config] = await Promise.all([
    api.GET("/api/v1/me/profile"),
    api.GET("/api/v1/sports"),
    api.GET("/api/v1/attributes"),
    fetchClientConfig(),
  ]);

  if (profile.data?.onboarding_completed) {
    redirect("/profile");
  }

  const t = await getTranslations("onboarding");

  if (!sports.data?.length) {
    return <p className="text-muted-foreground text-sm">{t("noSports")}</p>;
  }

  return (
    <OnboardingWizard
      sports={sports.data}
      attributes={attributes.data ?? []}
      defaultName={profile.data?.display_name || profile.data?.name || ""}
      ratingCap={config.self_assessed_rating_cap}
      defaultRating={config.onboarding_default_rating}
    />
  );
}
