import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { SquadInviteActions } from "./invite-actions";

export const metadata = { title: "My squads · TurfApp" };

export default async function SquadsPage() {
  const api = await getServerApiClient();
  const [squads, invites] = await Promise.all([
    api.GET("/api/v1/squads"),
    api.GET("/api/v1/me/squad-invites"),
  ]);

  const t = await getTranslations("squads");
  const mine = squads.data?.results ?? [];
  const pending = invites.data ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
          <p className="text-muted-foreground text-sm">{t("body")}</p>
        </div>
        <Button size="sm" asChild>
          <Link href="/squads/new">{t("create")}</Link>
        </Button>
      </div>

      {pending.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("invitations")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {pending.map((invite) => (
              <div
                key={invite.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm"
              >
                <span className="min-w-0">
                  <span className="block font-medium">{invite.squad.name}</span>
                  <span className="text-muted-foreground block text-xs">
                    {t("invitedBy", { name: invite.invited_by_name || "A member" })}
                  </span>
                </span>
                <SquadInviteActions inviteId={invite.id} />
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {mine.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
            <p className="text-muted-foreground text-sm">{t("empty")}</p>
            <Button size="sm" asChild>
              <Link href="/squads/new">{t("create")}</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <ul className="flex flex-col gap-3">
          {mine.map((squad) => (
            <li key={squad.id}>
              <Link
                href={`/squads/${squad.slug}`}
                className="bg-card hover:bg-muted/40 flex items-start justify-between gap-3 rounded-xl border p-4 shadow-sm transition-colors"
              >
                <span className="min-w-0">
                  <span className="block truncate text-base font-semibold">{squad.name}</span>
                  <span className="text-muted-foreground block text-xs">
                    {squad.area || t("noArea")} · {t("memberCount", { count: squad.member_count })}
                  </span>
                </span>
                <Badge variant={squad.accepts_public_requests ? "default" : "secondary"}>
                  {t(squad.accepts_public_requests ? "open" : "closed")}
                </Badge>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
