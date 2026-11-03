"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";

import type { Attribute, PlayerProfile, Sport } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

type Status = "idle" | "saving" | "saved" | "error";

/**
 * Profile settings: the discoverable toggle, the weight used for calorie estimates,
 * a re-run of the shared self-assessment, and add/remove for sports.
 *
 * Saving attributes recomputes every sport overall on the server, so the page is
 * refreshed afterwards rather than patching local state.
 */
export function SettingsForm({
  profile,
  attributes,
  sports,
  ratingCap,
  defaultRating,
  defaultWeightKg,
}: {
  profile: PlayerProfile;
  attributes: Attribute[];
  sports: Sport[];
  ratingCap: number;
  defaultRating: number;
  defaultWeightKg: number;
}) {
  const t = useTranslations("settings");
  const router = useRouter();
  const api = useApiClient();

  const [status, setStatus] = useState<Status>("idle");
  const [displayName, setDisplayName] = useState(profile.display_name ?? "");
  const [area, setArea] = useState(profile.area ?? "");
  const [bio, setBio] = useState(profile.bio ?? "");
  const [weightKg, setWeightKg] = useState(profile.weight_kg ?? "");
  const [discoverable, setDiscoverable] = useState(profile.discoverable ?? true);
  const [attributeValues, setAttributeValues] = useState<Record<string, number>>(() =>
    Object.fromEntries(
      attributes.map((attribute) => [
        attribute.key,
        profile.attributes.find((value) => value.key === attribute.key)?.value ?? defaultRating,
      ]),
    ),
  );

  const playing = new Set(profile.sport_cards.map((card) => card.sport.slug));

  async function save() {
    setStatus("saving");
    const { error } = await api.PATCH("/api/v1/me/profile", {
      body: {
        display_name: displayName,
        area,
        bio,
        weight_kg: weightKg === "" ? null : weightKg,
        discoverable,
        attributes: attributeValues,
      } as never,
    });
    setStatus(error ? "error" : "saved");
    if (!error) router.refresh();
  }

  async function addSport(slug: string) {
    setStatus("saving");
    const { error } = await api.POST("/api/v1/me/sports", {
      body: { sport: slug, positions: [], skills: {} } as never,
    });
    setStatus(error ? "error" : "saved");
    if (!error) router.refresh();
  }

  async function removeSport(slug: string) {
    setStatus("saving");
    const { error } = await api.DELETE("/api/v1/me/sports/{slug}", {
      params: { path: { slug } },
    });
    setStatus(error ? "error" : "saved");
    if (!error) router.refresh();
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("basics")}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor="displayName">{t("displayName")}</Label>
            <Input
              id="displayName"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              maxLength={80}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="area">{t("area")}</Label>
            <Input id="area" value={area} onChange={(event) => setArea(event.target.value)} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="weightKg">{t("weight")}</Label>
            <Input
              id="weightKg"
              type="number"
              min={20}
              max={300}
              step="0.1"
              value={weightKg ?? ""}
              placeholder={String(defaultWeightKg)}
              onChange={(event) => setWeightKg(event.target.value)}
            />
            <p className="text-muted-foreground text-xs">
              {t("weightHint", { fallback: defaultWeightKg })}
            </p>
          </div>
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor="bio">{t("bio")}</Label>
            <Textarea
              id="bio"
              value={bio}
              onChange={(event) => setBio(event.target.value)}
              maxLength={500}
              rows={3}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("privacy")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-start justify-between gap-4">
            <div>
              <Label htmlFor="discoverable">{t("discoverable")}</Label>
              <p className="text-muted-foreground mt-1 text-xs">{t("discoverableHint")}</p>
            </div>
            <Switch id="discoverable" checked={discoverable} onCheckedChange={setDiscoverable} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("attributes")}</CardTitle>
          <p className="text-muted-foreground text-xs">{t("attributesHint", { cap: ratingCap })}</p>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {attributes.map((attribute) => (
            <div key={attribute.key} className="flex items-center gap-3">
              <Label
                htmlFor={`attr-${attribute.key}`}
                className="w-24 shrink-0 text-xs font-normal"
              >
                {attribute.label}
              </Label>
              <Slider
                id={`attr-${attribute.key}`}
                className="flex-1"
                min={1}
                max={ratingCap}
                step={1}
                value={[attributeValues[attribute.key] ?? defaultRating]}
                onValueChange={([value]) =>
                  setAttributeValues((current) => ({ ...current, [attribute.key]: value }))
                }
              />
              <span className="w-7 shrink-0 text-right font-mono text-xs tabular-nums">
                {attributeValues[attribute.key] ?? defaultRating}
              </span>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("sports")}</CardTitle>
          <p className="text-muted-foreground text-xs">{t("sportsHint")}</p>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {sports.map((sport) => {
            const selected = playing.has(sport.slug);
            return (
              <div
                key={sport.slug}
                className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2"
              >
                <span className="flex items-center gap-2 text-sm">
                  <span aria-hidden>{sport.icon}</span>
                  {sport.name}
                </span>
                <Button
                  type="button"
                  size="xs"
                  variant={selected ? "destructive" : "outline"}
                  disabled={status === "saving"}
                  onClick={() => (selected ? removeSport(sport.slug) : addSport(sport.slug))}
                >
                  {selected ? t("remove") : t("add")}
                </Button>
              </div>
            );
          })}
        </CardContent>
      </Card>

      <div className="flex items-center gap-3 border-t pt-4">
        <Button type="button" onClick={save} disabled={status === "saving"}>
          {status === "saving" ? t("saving") : t("save")}
        </Button>
        {status === "saved" && (
          <span role="status" className="text-muted-foreground text-sm">
            {t("saved")}
          </span>
        )}
        {status === "error" && (
          <span role="alert" className="text-destructive text-sm">
            {t("saveFailed")}
          </span>
        )}
      </div>
    </div>
  );
}
