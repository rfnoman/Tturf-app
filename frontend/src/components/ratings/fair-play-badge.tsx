import { getTranslations } from "next-intl/server";

import type { FairPlay } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";

/** Fair play at a glance. Only upheld reports and real cards count (DOMAIN §8). */
export async function FairPlayBadge({ fairPlay }: { fairPlay: FairPlay }) {
  const t = await getTranslations("fairPlay");

  return (
    <Badge
      variant={fairPlay.band === "good" ? "secondary" : "destructive"}
      title={t("tooltip", {
        yellow: fairPlay.yellow_cards,
        red: fairPlay.red_cards,
        reports: fairPlay.upheld_reports,
      })}
      data-testid="fair-play"
    >
      {t("band", { band: fairPlay.band })} · {fairPlay.score}
    </Badge>
  );
}
