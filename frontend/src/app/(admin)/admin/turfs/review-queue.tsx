"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";

import type { OwnerTurf } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

/**
 * The admin turf review queue (DOMAIN §4).
 *
 * Rejection requires a reason — the backend enforces it, and the button is disabled
 * without one so an admin is not bounced by a 400 after writing nothing.
 */
export function TurfReviewQueue({ turfs }: { turfs: OwnerTurf[] }) {
  const t = useTranslations("adminTurfs");
  const router = useRouter();
  const api = useApiClient();

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reasons, setReasons] = useState<Record<string, string>>({});

  async function run(slug: string, call: () => Promise<{ error?: unknown }>) {
    setBusy(slug);
    setError(null);
    const { error: apiError } = await call();
    setBusy(null);
    if (apiError) {
      setError(t("actionFailed"));
      return;
    }
    router.refresh();
  }

  if (turfs.length === 0) {
    return <p className="text-muted-foreground text-sm">{t("empty")}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      {turfs.map((turf) => (
        <Card key={turf.id}>
          <CardHeader className="flex-row items-start justify-between gap-3">
            <div className="min-w-0">
              <CardTitle className="text-base">{turf.name}</CardTitle>
              <p className="text-muted-foreground mt-1 text-xs">
                {turf.area} · {turf.address}
              </p>
            </div>
            <Badge variant={turf.status === "approved" ? "default" : "secondary"}>
              {turf.status_label}
            </Badge>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {turf.description && <p className="text-sm">{turf.description}</p>}

            <ul className="flex flex-col gap-1 text-xs">
              {turf.grounds.map((ground) => (
                <li key={ground.id} className="flex items-center justify-between gap-2">
                  <span>
                    {ground.name} — {ground.sports.map((sport) => sport.name).join(", ")} ·{" "}
                    {t("slotLength", { minutes: ground.slot_minutes })}
                  </span>
                  <span className="text-muted-foreground">
                    {t("priceRules", { count: ground.price_rules.length })}
                  </span>
                </li>
              ))}
            </ul>

            <p className="text-muted-foreground text-xs">
              {t("summary", {
                grounds: turf.grounds.length,
                hours: turf.operating_hours.length,
              })}
            </p>

            <div className="flex flex-col gap-2 border-t pt-3">
              <Input
                aria-label={t("reason")}
                placeholder={t("reasonPlaceholder")}
                value={reasons[turf.slug] ?? ""}
                onChange={(event) =>
                  setReasons((current) => ({ ...current, [turf.slug]: event.target.value }))
                }
              />
              <div className="flex flex-wrap items-center gap-2">
                {turf.status !== "approved" && (
                  <Button
                    size="sm"
                    disabled={busy === turf.slug}
                    onClick={() =>
                      run(turf.slug, () =>
                        api.POST("/api/v1/admin/turfs/{slug}/approve", {
                          params: { path: { slug: turf.slug } },
                        }),
                      )
                    }
                  >
                    {t("approve")}
                  </Button>
                )}
                {turf.status === "pending_review" && (
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={busy === turf.slug || !reasons[turf.slug]}
                    onClick={() =>
                      run(turf.slug, () =>
                        api.POST("/api/v1/admin/turfs/{slug}/reject", {
                          params: { path: { slug: turf.slug } },
                          body: { reason: reasons[turf.slug] } as never,
                        }),
                      )
                    }
                  >
                    {t("reject")}
                  </Button>
                )}
                {turf.status === "approved" && (
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={busy === turf.slug}
                    onClick={() =>
                      run(turf.slug, () =>
                        api.POST("/api/v1/admin/turfs/{slug}/suspend", {
                          params: { path: { slug: turf.slug } },
                          body: { reason: reasons[turf.slug] ?? "" } as never,
                        }),
                      )
                    }
                  >
                    {t("suspend")}
                  </Button>
                )}
                {turf.status === "approved" && (
                  <Button size="sm" variant="outline" asChild>
                    <Link href={`/turfs/${turf.slug}`}>{t("viewPublic")}</Link>
                  </Button>
                )}
              </div>
              <p className="text-muted-foreground text-xs">{t("rejectHint")}</p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
