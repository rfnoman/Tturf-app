"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";

import type { ConductReport } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatWhen } from "@/i18n/formats";

/** Uphold or dismiss, with a note. Upholding is what moves a fair-play score. */
export function ConductQueue({ reports }: { reports: ConductReport[] }) {
  const t = useTranslations("adminConduct");
  const locale = useLocale();
  const router = useRouter();
  const api = useApiClient();

  const [busy, setBusy] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  async function review(id: string, uphold: boolean) {
    setBusy(id);
    setError(null);
    const { error: apiError } = await api.POST("/api/v1/admin/conduct-reports/{report_id}/review", {
      params: { path: { report_id: id } },
      body: { uphold, note: notes[id] ?? "" } as never,
    });
    setBusy(null);
    if (apiError) {
      setError(t("failed"));
      return;
    }
    router.refresh();
  }

  if (reports.length === 0) {
    return <p className="text-muted-foreground text-sm">{t("empty")}</p>;
  }

  return (
    <div className="flex flex-col gap-4" data-testid="conduct-queue">
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      {reports.map((report) => {
        const id = String(report.id);
        return (
          <Card key={id}>
            <CardHeader className="flex-row items-start justify-between gap-3">
              <div className="min-w-0">
                <CardTitle className="text-sm">
                  {t("against", { name: report.reported_name })}
                </CardTitle>
                <p className="text-muted-foreground mt-1 text-xs">
                  {t("by", { name: report.reporter_name })} · {report.match_summary} ·{" "}
                  {formatWhen(report.created_at, locale, "dayMonthTime")}
                </p>
              </div>
              <Badge variant="outline">{report.reason_label}</Badge>
            </CardHeader>

            <CardContent className="flex flex-col gap-3">
              {report.details && <p className="text-sm leading-relaxed">{report.details}</p>}

              <div className="flex flex-wrap items-end gap-2">
                <Input
                  aria-label={t("note")}
                  placeholder={t("notePlaceholder")}
                  value={notes[id] ?? ""}
                  onChange={(event) =>
                    setNotes((current) => ({ ...current, [id]: event.target.value }))
                  }
                  maxLength={300}
                  className="min-w-48 flex-1"
                />
                <Button size="sm" disabled={busy !== null} onClick={() => review(id, true)}>
                  {t("uphold")}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy !== null}
                  onClick={() => review(id, false)}
                >
                  {t("dismiss")}
                </Button>
              </div>
              <p className="text-muted-foreground text-xs">{t("upholdHint")}</p>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
