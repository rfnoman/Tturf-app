import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { getServerApiClient } from "@/lib/api/server";
import type { OwnerTurf } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata = { title: "Turf dashboard · TurfApp" };

/** Review state drives the badge colour: a rejection should not look like an approval. */
function statusTone(status: OwnerTurf["status"]) {
  switch (status) {
    case "approved":
      return "default" as const;
    case "rejected":
    case "suspended":
      return "destructive" as const;
    default:
      return "secondary" as const;
  }
}

export default async function OwnerDashboardPage() {
  const api = await getServerApiClient();
  const [turfs, memberships] = await Promise.all([
    api.GET("/api/v1/me/turfs"),
    api.GET("/api/v1/me/memberships"),
  ]);

  const t = await getTranslations("owner");
  const mine = turfs.data?.results ?? [];
  const invitations = (memberships.data?.results ?? []).filter(
    (membership) => membership.status === "invited",
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
          <p className="text-muted-foreground text-sm">{t("body")}</p>
        </div>
        <Button asChild size="sm">
          <Link href="/owner/new">{t("register")}</Link>
        </Button>
      </div>

      {invitations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("invitations")}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {invitations.map((invitation) => (
              <div
                key={invitation.id}
                className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm"
              >
                <span>
                  {t("invitedAs", {
                    turf: invitation.turf_name,
                    role: invitation.role_label,
                  })}
                </span>
                <Button size="xs" asChild>
                  <Link href={`/owner/invitations/${invitation.id}`}>{t("viewInvite")}</Link>
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {mine.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
            <p className="text-muted-foreground text-sm">{t("empty")}</p>
            <Button asChild size="sm">
              <Link href="/owner/new">{t("register")}</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <ul className="flex flex-col gap-3">
          {mine.map((turf) => (
            <li key={turf.id}>
              <Link
                href={`/owner/${turf.slug}`}
                className="bg-card hover:bg-muted/40 block rounded-xl border p-4 shadow-sm transition-colors"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h2 className="truncate text-base font-semibold">{turf.name}</h2>
                    <p className="text-muted-foreground text-xs">
                      {turf.area} · {t("groundCount", { count: turf.ground_count })}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {turf.my_role && <Badge variant="outline">{turf.my_role}</Badge>}
                    <Badge variant={statusTone(turf.status)}>{turf.status_label}</Badge>
                  </div>
                </div>
                {turf.status === "rejected" && turf.rejection_reason && (
                  <p className="text-destructive mt-2 text-xs">{turf.rejection_reason}</p>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
