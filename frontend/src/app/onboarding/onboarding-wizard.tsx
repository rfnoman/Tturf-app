"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { cn } from "cn";

import type { Attribute, Sport } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";

/**
 * Self-assessment slider range.
 *
 * The ceiling mirrors the backend's `SELF_ASSESSED_RATING_CAP`: the service clamps
 * anyway, so this is purely so the control cannot promise a value it will not get.
 * Sent to the component as a prop rather than hard-coded, from `/sports`' own cap.
 */
const SLIDER_MIN = 1;

type Step = "basics" | "sports" | "skills" | "attributes";

const STEPS: Step[] = ["basics", "sports", "skills", "attributes"];

type SportEntry = {
  positions: string[];
  skills: Record<string, number>;
};

/**
 * The onboarding wizard (phase 01 step 3).
 *
 * Four steps: basic info, choose sports, per-sport position and skill sliders, then the
 * shared attributes. Everything is held in local state and submitted once, so a player
 * can move back and forth without writing half a profile.
 */
export function OnboardingWizard({
  sports,
  attributes,
  defaultName,
  ratingCap,
  defaultRating,
}: {
  sports: Sport[];
  attributes: Attribute[];
  defaultName: string;
  ratingCap: number;
  defaultRating: number;
}) {
  const t = useTranslations("onboarding");
  const router = useRouter();
  const api = useApiClient();

  const [step, setStep] = useState<Step>("basics");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [displayName, setDisplayName] = useState(defaultName);
  const [area, setArea] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [heightCm, setHeightCm] = useState("");
  const [weightKg, setWeightKg] = useState("");
  const [preferredSide, setPreferredSide] = useState("");
  const [bio, setBio] = useState("");

  const [chosen, setChosen] = useState<Record<string, SportEntry>>({});
  const [attributeValues, setAttributeValues] = useState<Record<string, number>>(() =>
    Object.fromEntries(attributes.map((a) => [a.key, defaultRating])),
  );

  const chosenSports = useMemo(
    () => sports.filter((sport) => chosen[sport.slug]),
    [sports, chosen],
  );

  function toggleSport(sport: Sport) {
    setChosen((current) => {
      if (current[sport.slug]) {
        const rest = { ...current };
        delete rest[sport.slug];
        return rest;
      }
      return {
        ...current,
        [sport.slug]: {
          positions: [],
          skills: Object.fromEntries(sport.skills.map((skill) => [skill.key, defaultRating])),
        },
      };
    });
  }

  function togglePosition(slug: string, position: string) {
    setChosen((current) => {
      const entry = current[slug];
      if (!entry) return current;
      const positions = entry.positions.includes(position)
        ? entry.positions.filter((p) => p !== position)
        : [...entry.positions, position];
      return { ...current, [slug]: { ...entry, positions } };
    });
  }

  function setSkill(slug: string, key: string, value: number) {
    setChosen((current) => {
      const entry = current[slug];
      if (!entry) return current;
      return { ...current, [slug]: { ...entry, skills: { ...entry.skills, [key]: value } } };
    });
  }

  const stepIndex = STEPS.indexOf(step);
  const canAdvance = step !== "sports" || chosenSports.length > 0;

  async function submit() {
    setSubmitting(true);
    setError(null);

    const { data, error: apiError } = await api.POST("/api/v1/me/onboarding", {
      body: {
        display_name: displayName || undefined,
        area: area || undefined,
        date_of_birth: dateOfBirth || undefined,
        height_cm: heightCm ? Number(heightCm) : undefined,
        weight_kg: weightKg || undefined,
        preferred_side: preferredSide || undefined,
        bio: bio || undefined,
        attributes: attributeValues,
        sports: Object.entries(chosen).map(([slug, entry]) => ({
          sport: slug,
          positions: entry.positions,
          skills: entry.skills,
        })),
        // The generated request type is wider than the wizard needs; the backend
        // validates every field regardless.
      } as never,
    });

    setSubmitting(false);

    if (apiError || !data) {
      setError(t("submitFailed"));
      return;
    }

    // The player layout reads `onboarding_completed` server-side, so the cache has to
    // be dropped before navigating or the gate would bounce them straight back here.
    router.refresh();
    router.push("/profile");
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <p className="text-muted-foreground text-xs tracking-widest uppercase">
          {t("stepCounter", { current: stepIndex + 1, total: STEPS.length })}
        </p>
        <h1 className="text-2xl font-semibold tracking-tight">{t(`${step}.heading`)}</h1>
        <p className="text-muted-foreground text-sm">{t(`${step}.body`)}</p>
        <div className="bg-muted mt-2 h-1 overflow-hidden rounded-full">
          <div
            className="bg-primary h-full rounded-full transition-all"
            style={{ width: `${((stepIndex + 1) / STEPS.length) * 100}%` }}
          />
        </div>
      </header>

      {step === "basics" && (
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor="displayName">{t("fields.displayName")}</Label>
            <Input
              id="displayName"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              maxLength={80}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="area">{t("fields.area")}</Label>
            <Input
              id="area"
              value={area}
              onChange={(event) => setArea(event.target.value)}
              placeholder={t("fields.areaPlaceholder")}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dateOfBirth">{t("fields.dateOfBirth")}</Label>
            <Input
              id="dateOfBirth"
              type="date"
              value={dateOfBirth}
              onChange={(event) => setDateOfBirth(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="heightCm">{t("fields.heightCm")}</Label>
            <Input
              id="heightCm"
              type="number"
              min={80}
              max={260}
              value={heightCm}
              onChange={(event) => setHeightCm(event.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="weightKg">{t("fields.weightKg")}</Label>
            <Input
              id="weightKg"
              type="number"
              min={20}
              max={300}
              step="0.1"
              value={weightKg}
              onChange={(event) => setWeightKg(event.target.value)}
            />
            <p className="text-muted-foreground text-xs">{t("fields.weightHint")}</p>
          </div>
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label>{t("fields.preferredSide")}</Label>
            <div className="flex flex-wrap gap-2">
              {(["left", "right", "both"] as const).map((side) => (
                <Button
                  key={side}
                  type="button"
                  size="sm"
                  variant={preferredSide === side ? "default" : "outline"}
                  onClick={() => setPreferredSide(preferredSide === side ? "" : side)}
                >
                  {t(`sides.${side}`)}
                </Button>
              ))}
            </div>
          </div>
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor="bio">{t("fields.bio")}</Label>
            <Textarea
              id="bio"
              value={bio}
              onChange={(event) => setBio(event.target.value)}
              maxLength={500}
              rows={3}
            />
          </div>
        </div>
      )}

      {step === "sports" && (
        <div className="grid gap-3 sm:grid-cols-2">
          {sports.map((sport) => {
            const selected = Boolean(chosen[sport.slug]);
            return (
              <button
                key={sport.slug}
                type="button"
                aria-pressed={selected}
                onClick={() => toggleSport(sport)}
                className={cn(
                  "flex items-start gap-3 rounded-xl border p-4 text-left transition-colors",
                  selected ? "border-primary bg-primary/5" : "border-border hover:bg-muted/60",
                )}
              >
                <span aria-hidden className="text-2xl leading-none">
                  {sport.icon}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold">{sport.name}</span>
                  <span className="text-muted-foreground mt-0.5 block text-xs">
                    {sport.formats.map((format) => format.name).join(" · ")}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      )}

      {step === "skills" && (
        <div className="flex flex-col gap-4">
          {chosenSports.map((sport) => {
            const entry = chosen[sport.slug];
            return (
              <Card key={sport.slug}>
                <CardContent className="flex flex-col gap-4 pt-6">
                  <div className="flex items-center gap-2">
                    <span aria-hidden className="text-lg">
                      {sport.icon}
                    </span>
                    <h2 className="text-sm font-semibold">{sport.name}</h2>
                  </div>

                  {sport.positions.length > 0 && (
                    <div className="flex flex-col gap-2">
                      <Label>{t("fields.positions")}</Label>
                      <div className="flex flex-wrap gap-2">
                        {sport.positions.map((position) => (
                          <Button
                            key={position}
                            type="button"
                            size="xs"
                            variant={entry.positions.includes(position) ? "default" : "outline"}
                            onClick={() => togglePosition(sport.slug, position)}
                          >
                            {position}
                          </Button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="flex flex-col gap-3">
                    {sport.skills.map((skill) => (
                      <div key={skill.key} className="flex items-center gap-3">
                        <Label
                          htmlFor={`${sport.slug}-${skill.key}`}
                          className="w-28 shrink-0 text-xs font-normal"
                        >
                          {skill.label}
                        </Label>
                        <Slider
                          id={`${sport.slug}-${skill.key}`}
                          className="flex-1"
                          min={SLIDER_MIN}
                          max={ratingCap}
                          step={1}
                          value={[entry.skills[skill.key] ?? defaultRating]}
                          onValueChange={([value]) => setSkill(sport.slug, skill.key, value)}
                        />
                        <span className="w-7 shrink-0 text-right font-mono text-xs tabular-nums">
                          {entry.skills[skill.key] ?? defaultRating}
                        </span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            );
          })}
          <p className="text-muted-foreground text-xs">{t("capNote", { cap: ratingCap })}</p>
        </div>
      )}

      {step === "attributes" && (
        <div className="flex flex-col gap-4">
          <Card>
            <CardContent className="flex flex-col gap-4 pt-6">
              {attributes.map((attribute) => (
                <div key={attribute.key} className="flex flex-col gap-1.5">
                  <div className="flex items-center gap-3">
                    <Label
                      htmlFor={`attr-${attribute.key}`}
                      className="w-24 shrink-0 text-xs font-normal"
                    >
                      {attribute.label}
                    </Label>
                    <Slider
                      id={`attr-${attribute.key}`}
                      className="flex-1"
                      min={SLIDER_MIN}
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
                  {attribute.description && (
                    <p className="text-muted-foreground pl-27 text-xs">{attribute.description}</p>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground text-xs">{t("summary")}</span>
            {chosenSports.map((sport) => (
              <Badge key={sport.slug} variant="secondary">
                <span aria-hidden className="mr-1">
                  {sport.icon}
                </span>
                {sport.name}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      <footer className="flex items-center justify-between gap-3 border-t pt-4">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={stepIndex === 0 || submitting}
          onClick={() => setStep(STEPS[stepIndex - 1])}
        >
          {t("back")}
        </Button>

        {stepIndex < STEPS.length - 1 ? (
          <Button
            type="button"
            size="sm"
            disabled={!canAdvance}
            onClick={() => setStep(STEPS[stepIndex + 1])}
          >
            {t("next")}
          </Button>
        ) : (
          <Button type="button" size="sm" disabled={submitting} onClick={submit}>
            {submitting ? t("submitting") : t("finish")}
          </Button>
        )}
      </footer>
    </div>
  );
}
