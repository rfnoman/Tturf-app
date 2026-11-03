"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";

import type { Sport } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

/**
 * Create a squad.
 *
 * The open/closed switch is the important field: it decides whether the squad's matches
 * reach the board and take requests, or stay squad-only with the propose → approve →
 * accept chain (DOMAIN §6, DECISIONS D1). So it is explained, not just labelled.
 */
export function CreateSquadForm({ sports }: { sports: Sport[] }) {
  const t = useTranslations("squadForm");
  const router = useRouter();
  const api = useApiClient();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [area, setArea] = useState("");
  const [open, setOpen] = useState(false);
  const [sportIds, setSportIds] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setSaving(true);
    setError(null);
    const { data, error: apiError } = await api.POST("/api/v1/squads", {
      body: {
        name,
        description,
        area,
        accepts_public_requests: open,
        sport_ids: sportIds,
      } as never,
    });
    setSaving(false);
    if (apiError || !data) {
      setError(t("failed"));
      return;
    }
    router.refresh();
    router.push(`/squads/${data.slug}`);
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("heading")}</h1>
        <p className="text-muted-foreground text-sm">{t("body")}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <Label htmlFor="squad-name">{t("name")}</Label>
          <Input
            id="squad-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={80}
            required
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="squad-area">{t("area")}</Label>
          <Input
            id="squad-area"
            value={area}
            onChange={(event) => setArea(event.target.value)}
            placeholder={t("areaPlaceholder")}
          />
        </div>
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <Label htmlFor="squad-description">{t("description")}</Label>
          <Textarea
            id="squad-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={3}
            maxLength={500}
          />
        </div>
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <Label>{t("sports")}</Label>
          <div className="flex flex-wrap gap-2">
            {sports.map((sport) => {
              const selected = sportIds.includes(sport.id);
              return (
                <Button
                  key={sport.id}
                  type="button"
                  size="xs"
                  variant={selected ? "default" : "outline"}
                  aria-pressed={selected}
                  onClick={() =>
                    setSportIds((current) =>
                      selected ? current.filter((id) => id !== sport.id) : [...current, sport.id],
                    )
                  }
                >
                  <span aria-hidden className="mr-1">
                    {sport.icon}
                  </span>
                  {sport.name}
                </Button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="flex items-start justify-between gap-4 rounded-lg border p-4">
        <div>
          <Label htmlFor="squad-open">{t("openSquad")}</Label>
          <p className="text-muted-foreground mt-1 text-xs">
            {t(open ? "openHint" : "closedHint")}
          </p>
        </div>
        <Switch id="squad-open" checked={open} onCheckedChange={setOpen} />
      </div>

      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      <Button className="self-start" disabled={!name.trim() || saving} onClick={submit}>
        {saving ? t("saving") : t("create")}
      </Button>
    </div>
  );
}
