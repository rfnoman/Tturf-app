"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";

import type { Sport, SportProposal } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

/**
 * The sport-proposal review queue (DOMAIN §2).
 *
 * Approving creates the sport but leaves it inactive — it has no formats, skills or
 * stat definitions yet, so an admin finishes the setup in the Django admin before
 * players can pick it. The note under each approve button says so.
 */
export function ProposalQueue({
  proposals,
  sports,
}: {
  proposals: SportProposal[];
  sports: Sport[];
}) {
  const t = useTranslations("adminSports");
  const router = useRouter();
  const api = useApiClient();

  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [mergeTarget, setMergeTarget] = useState<Record<string, string>>({});

  async function run(id: string, call: () => Promise<{ error?: unknown }>) {
    setBusy(id);
    setError(null);
    const { error: apiError } = await call();
    setBusy(null);
    if (apiError) {
      setError(t("actionFailed"));
      return;
    }
    router.refresh();
  }

  if (proposals.length === 0) {
    return <p className="text-muted-foreground text-sm">{t("empty")}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      {proposals.map((proposal) => {
        const pending = proposal.status === "pending";
        return (
          <Card key={proposal.id}>
            <CardHeader className="flex-row items-start justify-between gap-3">
              <div className="min-w-0">
                <CardTitle className="text-base">{proposal.name}</CardTitle>
                <p className="text-muted-foreground mt-1 text-xs">
                  {t("proposedBy", { name: proposal.proposed_by_name || "—" })}
                </p>
              </div>
              <Badge variant={pending ? "default" : "secondary"}>
                {t(`status.${proposal.status}`)}
              </Badge>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {proposal.description && <p className="text-sm">{proposal.description}</p>}

              {proposal.merged_into && (
                // `merged_into` carries the new sport after an approval and the
                // existing one after a merge, so the copy has to follow the status.
                <p className="text-muted-foreground text-xs">
                  {proposal.status === "approved"
                    ? t("createdSport", { sport: proposal.merged_into.name })
                    : t("mergedInto", { sport: proposal.merged_into.name })}
                </p>
              )}
              {proposal.review_note && (
                <p className="text-muted-foreground text-xs italic">{proposal.review_note}</p>
              )}

              {pending && (
                <div className="flex flex-col gap-3 border-t pt-3">
                  <Input
                    aria-label={t("note")}
                    placeholder={t("notePlaceholder")}
                    value={notes[proposal.id] ?? ""}
                    onChange={(event) =>
                      setNotes((current) => ({ ...current, [proposal.id]: event.target.value }))
                    }
                  />

                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      size="sm"
                      disabled={busy === proposal.id}
                      onClick={() =>
                        run(proposal.id, () =>
                          api.POST("/api/v1/admin/sport-proposals/{id}/approve", {
                            params: { path: { id: proposal.id } },
                            body: { note: notes[proposal.id] ?? "" } as never,
                          }),
                        )
                      }
                    >
                      {t("approve")}
                    </Button>

                    <select
                      aria-label={t("mergeTarget")}
                      className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
                      value={mergeTarget[proposal.id] ?? ""}
                      onChange={(event) =>
                        setMergeTarget((current) => ({
                          ...current,
                          [proposal.id]: event.target.value,
                        }))
                      }
                    >
                      <option value="">{t("mergeTarget")}</option>
                      {sports.map((sport) => (
                        <option key={sport.id} value={sport.id}>
                          {sport.name}
                        </option>
                      ))}
                    </select>

                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy === proposal.id || !mergeTarget[proposal.id]}
                      onClick={() =>
                        run(proposal.id, () =>
                          api.POST("/api/v1/admin/sport-proposals/{id}/merge", {
                            params: { path: { id: proposal.id } },
                            body: {
                              sport_id: mergeTarget[proposal.id],
                              note: notes[proposal.id] ?? "",
                            } as never,
                          }),
                        )
                      }
                    >
                      {t("merge")}
                    </Button>

                    <Button
                      size="sm"
                      variant="destructive"
                      disabled={busy === proposal.id || !notes[proposal.id]}
                      onClick={() =>
                        run(proposal.id, () =>
                          api.POST("/api/v1/admin/sport-proposals/{id}/reject", {
                            params: { path: { id: proposal.id } },
                            body: { note: notes[proposal.id] ?? "" } as never,
                          }),
                        )
                      }
                    >
                      {t("reject")}
                    </Button>
                  </div>
                  <p className="text-muted-foreground text-xs">{t("approveHint")}</p>
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
