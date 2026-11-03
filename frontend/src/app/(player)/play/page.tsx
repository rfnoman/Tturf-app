import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AvailabilityForm } from "@/components/ratings/availability-form";

import { MatchBoard } from "./board";

export const metadata = { title: "Match board · TurfApp" };

export default async function PlayPage() {
  const api = await getServerApiClient();
  const [board, sports, mine, invites, availability] = await Promise.all([
    api.GET("/api/v1/matches/board"),
    api.GET("/api/v1/sports"),
    api.GET("/api/v1/matches/mine"),
    api.GET("/api/v1/me/invites"),
    api.GET("/api/v1/me/availability"),
  ]);

  const t = await getTranslations("board");
  const myMatches = mine.data ?? [];
  const myInvites = invites.data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
          <p className="text-muted-foreground text-sm">{t("body")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" asChild>
            <Link href="/players">{t("findPlayers")}</Link>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <Link href="/turfs">{t("bookInstead")}</Link>
          </Button>
        </div>
      </div>

      {/* "Free on Friday evening" — what makes a player findable when no match of
          theirs is on the board (DOMAIN §3). */}
      <AvailabilityForm sports={sports.data ?? []} windows={availability.data ?? []} />

      {myInvites.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("invitations")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {myInvites.map((invite) => (
              <Link
                key={invite.id}
                href={`/matches/${invite.id}`}
                className="hover:bg-muted/60 rounded-lg border px-3 py-2 text-sm"
              >
                {t("invitedBy", { name: invite.invited_by_name || "A player" })}
              </Link>
            ))}
          </CardContent>
        </Card>
      )}

      {myMatches.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-semibold">{t("myMatches")}</h2>
          <ul className="flex flex-col gap-2">
            {myMatches.map((match) => (
              <li key={match.id}>
                <Link
                  href={`/matches/${match.id}`}
                  className="bg-card hover:bg-muted/40 flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm transition-colors"
                >
                  <span className="min-w-0 truncate">
                    <span aria-hidden className="mr-1.5">
                      {match.sport.icon}
                    </span>
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

      <MatchBoard initialMatches={board.data ?? []} sports={sports.data ?? []} />
    </div>
  );
}
