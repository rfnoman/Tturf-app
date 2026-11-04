import { getTranslations } from "next-intl/server";
import { Flame } from "lucide-react";
import { cn } from "cn";

import type { Streak } from "@/lib/api/types";

/** Weeks in a row with a match (DOMAIN §10). */
export async function StreakBadge({ streak }: { streak: Streak }) {
  const t = await getTranslations("fitness");
  if (streak.current === 0) {
    return <p className="text-muted-foreground text-sm">{t("noStreak")}</p>;
  }

  return (
    <div className="flex items-center gap-2" data-testid="streak">
      <Flame
        aria-hidden
        className={cn(
          "size-5",
          streak.played_this_week ? "text-amber-500" : "text-muted-foreground",
        )}
      />
      <span className="text-sm">
        <span className="font-semibold">{t("streakWeeks", { count: streak.current })}</span>
        {!streak.played_this_week && (
          <span className="text-muted-foreground"> · {t("streakAtRisk")}</span>
        )}
        {streak.best > streak.current && (
          <span className="text-muted-foreground">
            {" "}
            · {t("streakBest", { count: streak.best })}
          </span>
        )}
      </span>
    </div>
  );
}
