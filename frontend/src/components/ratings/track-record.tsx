import { getTranslations } from "next-intl/server";

import type { TrackRecord } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { FormGuide } from "./form-guide";

/**
 * Where somebody has played and what they did there (DOMAIN §8).
 *
 * Per ground rather than per turf: "3× MOTM at Mirpur" is a thing players say, and the
 * ground is the pitch they actually know.
 */
export async function TrackRecord({ record }: { record: TrackRecord }) {
  const t = await getTranslations("trackRecord");
  const totals = Object.entries(record.totals ?? {});

  if (totals.length === 0 && record.grounds.length === 0) return null;

  return (
    <Card className="w-full max-w-xl" data-testid="track-record">
      <CardHeader>
        <CardTitle className="text-sm">{t("heading")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {totals.map(([slug, sport]) => (
          <div key={slug} className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-medium">{sport.sport}</span>
              <FormGuide form={sport.form} label={t("formLabel", { sport: sport.sport })} />
            </div>
            <p className="text-muted-foreground text-xs">
              {t("record", {
                matches: sport.matches,
                wins: sport.wins,
                draws: sport.draws,
                losses: sport.losses,
              })}
              {sport.motm_awards > 0 && ` · ${t("motm", { count: sport.motm_awards })}`}
            </p>
            {Object.keys(sport.stat_totals ?? {}).length > 0 && (
              <ul className="flex flex-wrap gap-1.5">
                {Object.entries(sport.stat_totals).map(([key, value]) => (
                  <li key={key}>
                    <Badge variant="secondary">
                      {value} {key.replace(/_/g, " ")}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}

        {record.grounds.length > 0 && (
          <div className="flex flex-col gap-2 border-t pt-4">
            <h3 className="text-muted-foreground text-xs tracking-wide uppercase">
              {t("grounds")}
            </h3>
            <ul className="flex flex-col gap-1.5 text-sm">
              {record.grounds.map((ground) => (
                <li
                  key={`${ground.turf_slug}-${ground.ground_name}-${ground.sport}`}
                  className="flex flex-wrap items-baseline justify-between gap-2"
                >
                  <span className="truncate">
                    {ground.turf_name}
                    <span className="text-muted-foreground"> · {ground.ground_name}</span>
                  </span>
                  <span className="text-muted-foreground text-xs">
                    {t("groundRecord", { matches: ground.matches, wins: ground.wins })}
                    {ground.motm_awards > 0 && ` · ${t("motm", { count: ground.motm_awards })}`}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
