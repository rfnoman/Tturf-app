import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import type { SquadMember } from "@/lib/api/types";
import { getServerApiClient } from "@/lib/api/server";
import { Roster } from "@/components/match/roster";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { MatchActions } from "./match-actions";

export default async function MatchPage({ params }: { params: Promise<{ matchId: string }> }) {
  const { matchId } = await params;

  const api = await getServerApiClient();
  const { data } = await api.GET("/api/v1/matches/{id}", {
    params: { path: { id: matchId } },
  });
  if (!data) notFound();

  const t = await getTranslations("matchPage");

  // Who this reader could invite: their squad-mates who are not already playing.
  // Full player search arrives in Phase 06.
  let invitable: SquadMember[] = [];
  if (data.squad || data.is_organiser) {
    const squads = await api.GET("/api/v1/squads");
    const onRoster = new Set(data.roster.map((entry) => entry.profile_id));
    const seen = new Set<string>();
    for (const summary of squads.data?.results ?? []) {
      const detail = await api.GET("/api/v1/squads/{slug}", {
        params: { path: { slug: summary.slug } },
      });
      for (const member of detail.data?.members ?? []) {
        if (!member.profile_id || onRoster.has(member.profile_id)) continue;
        if (seen.has(member.profile_id)) continue;
        seen.add(member.profile_id);
        invitable.push(member);
      }
    }
    invitable = invitable.slice(0, 50);
  }

  const when = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Dhaka",
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(data.starts_at));

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">
            <span aria-hidden className="mr-2">
              {data.sport.icon}
            </span>
            {data.sport.name} at {data.turf_name}
          </h1>
          <p className="text-muted-foreground text-sm">
            {data.ground_name} · {when} · {data.sport_format.name}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge variant={data.needed > 0 ? "default" : "secondary"}>
              {data.needed > 0 ? t("needed", { count: data.needed }) : t("full")}
            </Badge>
            <Badge variant="outline">{t(`visibility.${data.visibility}`)}</Badge>
            {data.squad && (
              <Link href={`/squads/${data.squad.slug}`}>
                <Badge variant="secondary">{data.squad.name}</Badge>
              </Link>
            )}
          </div>
        </div>
        <div className="text-right">
          <p className="font-mono text-lg font-semibold tabular-nums">৳{data.price}</p>
          <p className="text-muted-foreground text-xs">
            {t("organisedBy", { name: data.organiser_name })}
          </p>
        </div>
      </header>

      <MatchActions match={data} invitable={invitable} />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">
            {t("roster", { count: data.roster_count, capacity: data.capacity })}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Roster players={data.roster} capacity={data.capacity} />
        </CardContent>
      </Card>

      {data.notes && (
        <Card>
          <CardContent className="py-4 text-sm">{data.notes}</CardContent>
        </Card>
      )}

      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" asChild>
          <Link href={`/turfs/${data.turf_slug}`}>{t("viewTurf")}</Link>
        </Button>
        <Button variant="ghost" size="sm" asChild>
          <Link href="/play">{t("backToBoard")}</Link>
        </Button>
      </div>
    </div>
  );
}
