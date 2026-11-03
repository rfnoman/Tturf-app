import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { SquadManage } from "./squad-manage";

export default async function SquadPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;

  const api = await getServerApiClient();
  const [squad, matches] = await Promise.all([
    api.GET("/api/v1/squads/{slug}", { params: { path: { slug } } }),
    api.GET("/api/v1/matches/mine"),
  ]);

  if (!squad.data) notFound();
  const data = squad.data;
  const t = await getTranslations("squadPage");

  const squadMatches = (matches.data ?? []).filter((match) => match.squad?.slug === data.slug);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{data.name}</h1>
          <p className="text-muted-foreground text-sm">
            {data.area || t("noArea")} · {t("ledBy", { name: data.leader_name })}
          </p>
          {data.description && <p className="mt-2 text-sm">{data.description}</p>}
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge variant={data.accepts_public_requests ? "default" : "secondary"}>
              {t(data.accepts_public_requests ? "open" : "closed")}
            </Badge>
            {data.sports.map((sport) => (
              <Badge key={sport.slug} variant="outline">
                <span aria-hidden className="mr-1">
                  {sport.icon}
                </span>
                {sport.name}
              </Badge>
            ))}
          </div>
        </div>
        <Button variant="ghost" size="sm" asChild>
          <Link href="/squads">{t("allSquads")}</Link>
        </Button>
      </header>

      {squadMatches.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold">{t("upcomingMatches")}</h2>
          <ul className="flex flex-col gap-2">
            {squadMatches.map((match) => (
              <li key={match.id}>
                <Link
                  href={`/matches/${match.id}`}
                  className="bg-card hover:bg-muted/40 flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm transition-colors"
                >
                  <span className="min-w-0 truncate">
                    {match.turf_name} · {match.ground_name}
                  </span>
                  <span className="text-muted-foreground shrink-0 text-xs">
                    {t("needed", { count: match.needed })}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <SquadManage squad={data} />
    </div>
  );
}
