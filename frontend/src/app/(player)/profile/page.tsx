import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { PlayerProfileView } from "@/components/player/player-profile-view";
import { Button } from "@/components/ui/button";

export const metadata = { title: "My profile · TurfApp" };

export default async function MyProfilePage() {
  const api = await getServerApiClient();
  const { data } = await api.GET("/api/v1/me/profile");

  if (!data) notFound();

  const t = await getTranslations("profile");

  return (
    <PlayerProfileView
      player={data}
      action={
        <Button variant="outline" size="sm" asChild>
          <Link href="/settings">{t("edit")}</Link>
        </Button>
      }
    />
  );
}
