"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";

import type {
  Ground,
  OperatingHours,
  OwnerTurf,
  SportFormat,
  Sport,
  TurfMembership,
} from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/** Monday-first, matching the backend's `date.weekday()` convention. */
const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6] as const;

type Busy = string | null;

/**
 * Everything an owner does to a turf after registering it: grounds, opening hours,
 * price rules, staff, and submitting for review.
 *
 * One client component rather than five, because the pieces constrain each other —
 * activating a ground depends on the hours *and* the prices, and submitting depends on
 * all three. Keeping them together means one `router.refresh()` reconciles the lot.
 */
export function ManageTurf({
  turf,
  sports,
  staff,
}: {
  turf: OwnerTurf;
  sports: Sport[];
  staff: TurfMembership[];
}) {
  const t = useTranslations("ownerManage");
  const router = useRouter();

  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const isOwner = turf.my_role === "owner";

  async function run(key: string, call: () => Promise<{ error?: unknown }>) {
    setBusy(key);
    setError(null);
    const { error: apiError } = await call();
    setBusy(null);
    if (apiError) {
      // The backend's validation messages are the useful part — price coverage gaps,
      // missing hours — so they are surfaced verbatim rather than flattened to "error".
      setError(describe(apiError) ?? t("failed"));
      return false;
    }
    router.refresh();
    return true;
  }

  return (
    <div className="flex flex-col gap-6">
      {error && (
        <p role="alert" className="text-destructive text-sm whitespace-pre-line">
          {error}
        </p>
      )}

      <ReviewPanel turf={turf} isOwner={isOwner} busy={busy} run={run} />
      <GroundsPanel turf={turf} sports={sports} isOwner={isOwner} busy={busy} run={run} />
      <HoursPanel turf={turf} isOwner={isOwner} busy={busy} run={run} />
      <StaffPanel turf={turf} staff={staff} isOwner={isOwner} busy={busy} run={run} />
    </div>
  );
}

/** Turn a DRF error body into something an owner can act on. */
function describe(error: unknown): string | null {
  if (!error || typeof error !== "object") return null;
  const parts: string[] = [];
  for (const [field, value] of Object.entries(error as Record<string, unknown>)) {
    const message = Array.isArray(value) ? value.join(" ") : String(value);
    parts.push(field === "detail" ? message : `${field}: ${message}`);
  }
  return parts.length > 0 ? parts.join("\n") : null;
}

function ReviewPanel({
  turf,
  isOwner,
  busy,
  run,
}: {
  turf: OwnerTurf;
  isOwner: boolean;
  busy: Busy;
  run: (key: string, call: () => Promise<{ error?: unknown }>) => Promise<boolean>;
}) {
  const t = useTranslations("ownerManage");
  const api = useApiClient();
  const submittable = turf.status === "draft" || turf.status === "rejected";

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="text-sm">{t("review")}</CardTitle>
          <p className="text-muted-foreground mt-1 text-xs">{t("reviewHint")}</p>
        </div>
        <Badge variant={turf.status === "approved" ? "default" : "secondary"}>
          {turf.status_label}
        </Badge>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {turf.rejection_reason && (
          <p className="text-destructive text-xs">{turf.rejection_reason}</p>
        )}
        {submittable && isOwner && (
          <Button
            size="sm"
            className="self-start"
            disabled={busy === "submit"}
            onClick={() =>
              run("submit", () =>
                api.POST("/api/v1/me/turfs/{slug}/submit", {
                  params: { path: { slug: turf.slug } },
                }),
              )
            }
          >
            {t("submit")}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function GroundsPanel({
  turf,
  sports,
  isOwner,
  busy,
  run,
}: {
  turf: OwnerTurf;
  sports: Sport[];
  isOwner: boolean;
  busy: Busy;
  run: (key: string, call: () => Promise<{ error?: unknown }>) => Promise<boolean>;
}) {
  const t = useTranslations("ownerManage");
  const api = useApiClient();
  const [name, setName] = useState("");
  const [maxPlayers, setMaxPlayers] = useState("10");
  const [slotMinutes, setSlotMinutes] = useState("60");
  const [formatIds, setFormatIds] = useState<string[]>([]);

  const formats: Array<SportFormat & { sportName: string; icon: string }> = sports.flatMap(
    (sport) =>
      sport.formats.map((format) => ({
        ...format,
        sportName: sport.name,
        icon: sport.icon ?? "",
      })),
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{t("grounds")}</CardTitle>
        <p className="text-muted-foreground text-xs">{t("groundsHint")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {turf.grounds.length === 0 ? (
          <p className="text-muted-foreground text-sm">{t("noGrounds")}</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {turf.grounds.map((ground) => (
              <GroundRow
                key={ground.id}
                turf={turf}
                ground={ground}
                isOwner={isOwner}
                busy={busy}
                run={run}
              />
            ))}
          </ul>
        )}

        {isOwner && (
          <div className="flex flex-col gap-3 border-t pt-4">
            <h3 className="text-xs font-semibold tracking-wide uppercase">{t("addGround")}</h3>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="ground-name">{t("groundName")}</Label>
                <Input
                  id="ground-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="ground-max">{t("maxPlayers")}</Label>
                <Input
                  id="ground-max"
                  type="number"
                  min={2}
                  value={maxPlayers}
                  onChange={(event) => setMaxPlayers(event.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="ground-slot">{t("slotMinutes")}</Label>
                <select
                  id="ground-slot"
                  value={slotMinutes}
                  onChange={(event) => setSlotMinutes(event.target.value)}
                  className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
                >
                  {[60, 90, 120].map((minutes) => (
                    <option key={minutes} value={minutes}>
                      {minutes}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label>{t("sportFormats")}</Label>
              <div className="flex flex-wrap gap-1.5">
                {formats.map((format) => {
                  const selected = formatIds.includes(format.id);
                  return (
                    <Button
                      key={format.id}
                      type="button"
                      size="xs"
                      variant={selected ? "default" : "outline"}
                      aria-pressed={selected}
                      onClick={() =>
                        setFormatIds((current) =>
                          selected
                            ? current.filter((id) => id !== format.id)
                            : [...current, format.id],
                        )
                      }
                    >
                      <span aria-hidden className="mr-1">
                        {format.icon}
                      </span>
                      {format.sportName} {format.name}
                    </Button>
                  );
                })}
              </div>
            </div>

            <Button
              size="sm"
              className="self-start"
              disabled={!name.trim() || formatIds.length === 0 || busy === "add-ground"}
              onClick={async () => {
                const ok = await run("add-ground", () =>
                  api.POST("/api/v1/me/turfs/{slug}/grounds", {
                    params: { path: { slug: turf.slug } },
                    body: {
                      name,
                      max_players: Number(maxPlayers),
                      slot_minutes: Number(slotMinutes),
                      sport_format_ids: formatIds,
                    } as never,
                  }),
                );
                if (ok) {
                  setName("");
                  setFormatIds([]);
                }
              }}
            >
              {t("addGround")}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function GroundRow({
  turf,
  ground,
  isOwner,
  busy,
  run,
}: {
  turf: OwnerTurf;
  ground: Ground;
  isOwner: boolean;
  busy: Busy;
  run: (key: string, call: () => Promise<{ error?: unknown }>) => Promise<boolean>;
}) {
  const t = useTranslations("ownerManage");
  const api = useApiClient();
  const [open, setOpen] = useState(false);
  const [weekdays, setWeekdays] = useState<number[]>([]);
  const [startTime, setStartTime] = useState("06:00");
  const [endTime, setEndTime] = useState("18:00");
  const [price, setPrice] = useState("1500");
  const [label, setLabel] = useState("");

  return (
    <li className="rounded-lg border">
      <div className="flex flex-wrap items-center justify-between gap-2 p-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{ground.name}</p>
          <p className="text-muted-foreground text-xs">
            {ground.sports.map((sport) => sport.name).join(" · ")} ·{" "}
            {t("slotLength", { minutes: ground.slot_minutes })} ·{" "}
            {t("capacity", { count: ground.max_players })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={ground.is_active ? "default" : "secondary"}>
            {ground.is_active ? t("active") : t("inactive")}
          </Badge>
          {isOwner && (
            <>
              <Button size="xs" variant="ghost" onClick={() => setOpen((value) => !value)}>
                {t("prices", { count: ground.price_rules.length })}
              </Button>
              <Button
                size="xs"
                variant={ground.is_active ? "outline" : "default"}
                disabled={busy === ground.id}
                onClick={() =>
                  run(ground.id, () =>
                    api.POST(
                      ground.is_active
                        ? "/api/v1/me/turfs/{slug}/grounds/{id}/deactivate"
                        : "/api/v1/me/turfs/{slug}/grounds/{id}/activate",
                      { params: { path: { slug: turf.slug, id: ground.id } } },
                    ),
                  )
                }
              >
                {ground.is_active ? t("deactivate") : t("activate")}
              </Button>
            </>
          )}
        </div>
      </div>

      {open && isOwner && (
        <div className="flex flex-col gap-3 border-t p-3">
          {ground.price_rules.length > 0 && (
            <ul className="flex flex-col gap-1 text-xs">
              {ground.price_rules.map((rule) => (
                <li key={rule.id} className="flex items-center justify-between gap-2">
                  <span>
                    {/* Optional on write (the model defaults to []), always present on read. */}
                    {(rule.weekdays ?? []).length === 0
                      ? t("everyDay")
                      : (rule.weekdays ?? [])
                          .map((day) => t(`weekdayShort.${day}`))
                          .join(", ")}{" "}
                    {rule.start_time.slice(0, 5)}–{rule.end_time.slice(0, 5)}{" "}
                    {rule.label && `(${rule.label})`}
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="font-mono tabular-nums">৳{rule.price}</span>
                    <Button
                      size="xs"
                      variant="ghost"
                      disabled={busy === rule.id}
                      onClick={() =>
                        run(rule.id, () =>
                          api.DELETE("/api/v1/me/turfs/{slug}/grounds/{ground_pk}/prices/{id}", {
                            params: {
                              path: { slug: turf.slug, ground_pk: ground.id, id: rule.id },
                            },
                          }),
                        )
                      }
                    >
                      {t("remove")}
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
          )}

          <div className="flex flex-wrap items-end gap-2">
            <div className="flex flex-col gap-1">
              <Label className="text-xs">{t("weekdays")}</Label>
              <div className="flex gap-1">
                {WEEKDAYS.map((day) => {
                  const selected = weekdays.includes(day);
                  return (
                    <Button
                      key={day}
                      type="button"
                      size="xs"
                      variant={selected ? "default" : "outline"}
                      aria-pressed={selected}
                      onClick={() =>
                        setWeekdays((current) =>
                          selected ? current.filter((d) => d !== day) : [...current, day],
                        )
                      }
                    >
                      {t(`weekdayShort.${day}`)}
                    </Button>
                  );
                })}
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor={`from-${ground.id}`} className="text-xs">
                {t("from")}
              </Label>
              <Input
                id={`from-${ground.id}`}
                type="time"
                value={startTime}
                onChange={(event) => setStartTime(event.target.value)}
                className="w-28"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor={`until-${ground.id}`} className="text-xs">
                {t("until")}
              </Label>
              <Input
                id={`until-${ground.id}`}
                type="time"
                value={endTime}
                onChange={(event) => setEndTime(event.target.value)}
                className="w-28"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor={`price-${ground.id}`} className="text-xs">
                {t("price")}
              </Label>
              <Input
                id={`price-${ground.id}`}
                type="number"
                min={0}
                value={price}
                onChange={(event) => setPrice(event.target.value)}
                className="w-28"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor={`label-${ground.id}`} className="text-xs">
                {t("label")}
              </Label>
              <Input
                id={`label-${ground.id}`}
                value={label}
                onChange={(event) => setLabel(event.target.value)}
                placeholder={t("labelPlaceholder")}
                className="w-28"
              />
            </div>
            <Button
              size="sm"
              disabled={busy === `price-${ground.id}`}
              onClick={async () => {
                const ok = await run(`price-${ground.id}`, () =>
                  api.POST("/api/v1/me/turfs/{slug}/grounds/{ground_pk}/prices", {
                    params: { path: { slug: turf.slug, ground_pk: ground.id } },
                    body: {
                      weekdays,
                      start_time: startTime,
                      end_time: endTime,
                      price,
                      label,
                    } as never,
                  }),
                );
                if (ok) setLabel("");
              }}
            >
              {t("addPrice")}
            </Button>
          </div>
          <p className="text-muted-foreground text-xs">{t("priceHint")}</p>
        </div>
      )}
    </li>
  );
}

function HoursPanel({
  turf,
  isOwner,
  busy,
  run,
}: {
  turf: OwnerTurf;
  isOwner: boolean;
  busy: Busy;
  run: (key: string, call: () => Promise<{ error?: unknown }>) => Promise<boolean>;
}) {
  const t = useTranslations("ownerManage");
  const api = useApiClient();
  const [openTime, setOpenTime] = useState("06:00");
  const [closeTime, setCloseTime] = useState("23:00");
  const [days, setDays] = useState<number[]>([...WEEKDAYS]);

  const byDay = new Map<number, OperatingHours[]>();
  for (const row of turf.operating_hours) {
    byDay.set(row.weekday, [...(byDay.get(row.weekday) ?? []), row]);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{t("hours")}</CardTitle>
        <p className="text-muted-foreground text-xs">{t("hoursHint")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ul className="flex flex-col gap-1 text-sm">
          {WEEKDAYS.map((day) => {
            const rows = byDay.get(day) ?? [];
            return (
              <li key={day} className="flex items-center justify-between gap-2 py-1">
                <span className="w-24 shrink-0 text-xs font-medium">{t(`weekday.${day}`)}</span>
                {rows.length === 0 ? (
                  <span className="text-muted-foreground flex-1 text-xs">{t("closed")}</span>
                ) : (
                  <span className="flex flex-1 flex-wrap gap-2">
                    {rows.map((row) => (
                      <span key={row.id} className="flex items-center gap-1 text-xs">
                        <span className="font-mono tabular-nums">
                          {row.open_time.slice(0, 5)}–{row.close_time.slice(0, 5)}
                        </span>
                        {row.crosses_midnight && (
                          <span className="text-muted-foreground">{t("nextDay")}</span>
                        )}
                        {isOwner && (
                          <Button
                            size="xs"
                            variant="ghost"
                            disabled={busy === row.id}
                            onClick={() =>
                              run(row.id, () =>
                                api.DELETE("/api/v1/me/turfs/{slug}/hours/{id}", {
                                  params: { path: { slug: turf.slug, id: row.id } },
                                }),
                              )
                            }
                          >
                            ×
                          </Button>
                        )}
                      </span>
                    ))}
                  </span>
                )}
              </li>
            );
          })}
        </ul>

        {isOwner && (
          <div className="flex flex-wrap items-end gap-2 border-t pt-4">
            <div className="flex flex-col gap-1">
              <Label className="text-xs">{t("weekdays")}</Label>
              <div className="flex gap-1">
                {WEEKDAYS.map((day) => {
                  const selected = days.includes(day);
                  return (
                    <Button
                      key={day}
                      type="button"
                      size="xs"
                      variant={selected ? "default" : "outline"}
                      aria-pressed={selected}
                      onClick={() =>
                        setDays((current) =>
                          selected ? current.filter((d) => d !== day) : [...current, day],
                        )
                      }
                    >
                      {t(`weekdayShort.${day}`)}
                    </Button>
                  );
                })}
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="opens" className="text-xs">
                {t("opens")}
              </Label>
              <Input
                id="opens"
                type="time"
                value={openTime}
                onChange={(event) => setOpenTime(event.target.value)}
                className="w-28"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="closes" className="text-xs">
                {t("closes")}
              </Label>
              <Input
                id="closes"
                type="time"
                value={closeTime}
                onChange={(event) => setCloseTime(event.target.value)}
                className="w-28"
              />
            </div>
            <Button
              size="sm"
              disabled={days.length === 0 || busy === "hours"}
              onClick={() =>
                run("hours", async () => {
                  // One request per selected day; the API models a row per weekday.
                  for (const day of days) {
                    const result = await api.POST("/api/v1/me/turfs/{slug}/hours", {
                      params: { path: { slug: turf.slug } },
                      body: {
                        weekday: day,
                        open_time: openTime,
                        close_time: closeTime,
                      } as never,
                    });
                    if (result.error) return result;
                  }
                  return {};
                })
              }
            >
              {t("setHours")}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function StaffPanel({
  turf,
  staff,
  isOwner,
  busy,
  run,
}: {
  turf: OwnerTurf;
  staff: TurfMembership[];
  isOwner: boolean;
  busy: Busy;
  run: (key: string, call: () => Promise<{ error?: unknown }>) => Promise<boolean>;
}) {
  const t = useTranslations("ownerManage");
  const api = useApiClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("cashier");

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{t("staff")}</CardTitle>
        <p className="text-muted-foreground text-xs">{t("staffHint")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <ul className="flex flex-col gap-2">
          {staff.map((member) => (
            <li
              key={member.id}
              className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm"
            >
              <span className="min-w-0">
                <span className="block truncate">
                  {member.user_name || member.user_email || member.invited_email}
                </span>
                <span className="text-muted-foreground text-xs">
                  {member.role_label} ·{" "}
                  {member.status === "active" ? t("staffActive") : t("staffInvited")}
                </span>
              </span>
              {isOwner && member.role !== "owner" && (
                <Button
                  size="xs"
                  variant="destructive"
                  disabled={busy === member.id}
                  onClick={() =>
                    run(member.id, () =>
                      api.DELETE("/api/v1/me/turfs/{slug}/staff/{membership_id}", {
                        params: { path: { slug: turf.slug, membership_id: member.id } },
                      }),
                    )
                  }
                >
                  {t("remove")}
                </Button>
              )}
            </li>
          ))}
        </ul>

        {isOwner && (
          <div className="flex flex-wrap items-end gap-2 border-t pt-4">
            <div className="flex flex-col gap-1">
              <Label htmlFor="staff-email" className="text-xs">
                {t("staffEmail")}
              </Label>
              <Input
                id="staff-email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="w-56"
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="staff-role" className="text-xs">
                {t("staffRole")}
              </Label>
              <select
                id="staff-role"
                value={role}
                onChange={(event) => setRole(event.target.value)}
                className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
              >
                <option value="cashier">{t("roleCashier")}</option>
                <option value="manager">{t("roleManager")}</option>
              </select>
            </div>
            <Button
              size="sm"
              disabled={!email.trim() || busy === "invite"}
              onClick={async () => {
                const ok = await run("invite", () =>
                  api.POST("/api/v1/me/turfs/{slug}/staff/invite", {
                    params: { path: { slug: turf.slug } },
                    body: { role, email } as never,
                  }),
                );
                if (ok) setEmail("");
              }}
            >
              {t("invite")}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
