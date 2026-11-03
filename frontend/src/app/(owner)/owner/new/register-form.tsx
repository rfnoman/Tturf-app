"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";

import type { Amenity } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { TurfMap } from "@/components/turf/turf-map";

/** Dhaka city centre: where the picker starts before the owner drops a pin. */
const DHAKA: [number, number] = [23.8103, 90.4125];

type Step = "details" | "location" | "amenities";
const STEPS: Step[] = ["details", "location", "amenities"];

/**
 * Step one of turf registration: details, a map pin, and amenities.
 *
 * The turf is created as a **draft** here and the owner continues on its own page to
 * add grounds, hours and prices. Splitting it that way means a half-finished
 * registration is a saved draft rather than lost work, and it is also the only shape
 * that can enforce "price rules must cover opening hours" — that check needs the turf
 * to exist first.
 */
export function RegisterTurfForm({ amenities }: { amenities: Amenity[] }) {
  const t = useTranslations("ownerRegister");
  const router = useRouter();
  const api = useApiClient();

  const [step, setStep] = useState<Step>("details");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [address, setAddress] = useState("");
  const [area, setArea] = useState("");
  const [phone, setPhone] = useState("");
  const [position, setPosition] = useState<[number, number]>(DHAKA);
  const [chosen, setChosen] = useState<string[]>([]);

  const index = STEPS.indexOf(step);
  const canAdvance = step !== "details" || (name.trim() && address.trim() && area.trim());

  async function submit() {
    setSubmitting(true);
    setError(null);

    const { data, error: apiError } = await api.POST("/api/v1/me/turfs", {
      body: {
        name,
        description,
        address,
        area,
        phone,
        latitude: position[0],
        longitude: position[1],
        amenity_ids: chosen,
      } as never,
    });

    setSubmitting(false);
    if (apiError || !data) {
      setError(t("failed"));
      return;
    }

    router.refresh();
    router.push(`/owner/${data.slug}`);
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <p className="text-muted-foreground text-xs tracking-widest uppercase">
          {t("stepCounter", { current: index + 1, total: STEPS.length })}
        </p>
        <h1 className="text-2xl font-semibold tracking-tight">{t(`${step}.heading`)}</h1>
        <p className="text-muted-foreground text-sm">{t(`${step}.body`)}</p>
        <div className="bg-muted mt-2 h-1 overflow-hidden rounded-full">
          <div
            className="bg-primary h-full rounded-full transition-all"
            style={{ width: `${((index + 1) / STEPS.length) * 100}%` }}
          />
        </div>
      </header>

      {step === "details" && (
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor="name">{t("fields.name")}</Label>
            <Input
              id="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={120}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor="address">{t("fields.address")}</Label>
            <Textarea
              id="address"
              value={address}
              onChange={(event) => setAddress(event.target.value)}
              rows={2}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="area">{t("fields.area")}</Label>
            <Input
              id="area"
              value={area}
              onChange={(event) => setArea(event.target.value)}
              placeholder={t("fields.areaPlaceholder")}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="phone">{t("fields.phone")}</Label>
            <Input
              id="phone"
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
              placeholder="+8801XXXXXXXXX"
            />
          </div>
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <Label htmlFor="description">{t("fields.description")}</Label>
            <Textarea
              id="description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={3}
            />
          </div>
        </div>
      )}

      {step === "location" && (
        <div className="flex flex-col gap-3">
          <TurfMap
            draggableMarker
            center={position}
            zoom={15}
            markers={[
              {
                id: "pin",
                latitude: position[0],
                longitude: position[1],
                label: name || t("fields.name"),
              },
            ]}
            onMove={(latitude, longitude) => setPosition([latitude, longitude])}
            className="h-80 w-full rounded-xl border"
          />
          <p className="text-muted-foreground text-xs">{t("location.hint")}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="latitude">{t("fields.latitude")}</Label>
              <Input
                id="latitude"
                type="number"
                step="0.000001"
                value={position[0]}
                onChange={(event) => setPosition([Number(event.target.value) || 0, position[1]])}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="longitude">{t("fields.longitude")}</Label>
              <Input
                id="longitude"
                type="number"
                step="0.000001"
                value={position[1]}
                onChange={(event) => setPosition([position[0], Number(event.target.value) || 0])}
              />
            </div>
          </div>
        </div>
      )}

      {step === "amenities" && (
        <div className="grid gap-2 sm:grid-cols-2">
          {amenities.map((amenity) => {
            const selected = chosen.includes(amenity.id);
            return (
              <Button
                key={amenity.id}
                type="button"
                variant={selected ? "default" : "outline"}
                size="sm"
                aria-pressed={selected}
                className="justify-start"
                onClick={() =>
                  setChosen((current) =>
                    selected ? current.filter((id) => id !== amenity.id) : [...current, amenity.id],
                  )
                }
              >
                <span aria-hidden className="mr-2">
                  {amenity.icon}
                </span>
                {amenity.label}
              </Button>
            );
          })}
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
          disabled={index === 0 || submitting}
          onClick={() => setStep(STEPS[index - 1])}
        >
          {t("back")}
        </Button>
        {index < STEPS.length - 1 ? (
          <Button
            type="button"
            size="sm"
            disabled={!canAdvance}
            onClick={() => setStep(STEPS[index + 1])}
          >
            {t("next")}
          </Button>
        ) : (
          <Button type="button" size="sm" disabled={submitting} onClick={submit}>
            {submitting ? t("saving") : t("createDraft")}
          </Button>
        )}
      </footer>
    </div>
  );
}
