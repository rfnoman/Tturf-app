"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { cn } from "cn";

import type { ActivityLog, GoalProgress, Sport, Streak, WeeklySummary } from "@/lib/api/types";
import { useApiClient } from "@/lib/api/use-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatWhen } from "@/i18n/formats";

const GOAL_TYPES = ["matches_per_week", "minutes_per_week", "calories_per_week"] as const;

/**
 * The activity page: the last twelve weeks as bars, the history under it, and the two
 * things a player can change — their goals and what they did that the app missed.
 */
export function ActivityBoard({
  week,
  streak,
  goals,
  logs,
  sports,
}: {
  week?: WeeklySummary;
  streak?: Streak;
  goals: GoalProgress[];
  logs: ActivityLog[];
  sports: Sport[];
}) {
  const t = useTranslations("fitness");
  const locale = useLocale();
  const router = useRouter();
  const api = useApiClient();

  const [minutes, setMinutes] = useState("");
  const [sport, setSport] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Twelve weeks of minutes, oldest first, keyed by the Saturday each week began.
  const weeks = useMemo(() => {
    const buckets = new Map<string, number>();
    const today = new Date();

    for (let index = 11; index >= 0; index -= 1) {
      const day = new Date(today.getTime() - index * 7 * 86_400_000);
      buckets.set(weekKey(day), 0);
    }
    for (const log of logs) {
      const key = weekKey(new Date(`${log.happened_on}T12:00:00+06:00`));
      if (buckets.has(key)) buckets.set(key, (buckets.get(key) ?? 0) + log.minutes);
    }
    return [...buckets.entries()];
  }, [logs]);

  const tallest = Math.max(60, ...weeks.map(([, value]) => value));

  async function addActivity() {
    setBusy(true);
    setError(null);
    const { error: apiError } = await api.POST("/api/v1/me/activity", {
      body: {
        minutes: Number(minutes),
        ...(sport ? { sport } : {}),
        note,
      } as never,
    });
    setBusy(false);
    if (apiError) {
      setError(t("addFailed"));
      return;
    }
    setMinutes("");
    setNote("");
    router.refresh();
  }

  async function setGoal(type: string, target: number) {
    setBusy(true);
    setError(null);
    const { error: apiError } = await api.POST("/api/v1/me/goals", {
      body: { type, target } as never,
    });
    setBusy(false);
    if (apiError) {
      setError(t("goalFailed"));
      return;
    }
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-6">
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("lastTwelveWeeks")}</CardTitle>
          <p className="text-muted-foreground text-xs">
            {t("weekSummary", { matches: week?.matches ?? 0, calories: week?.calories ?? 0 })}
            {streak && streak.current > 0 && ` · ${t("streakWeeks", { count: streak.current })}`}
          </p>
        </CardHeader>
        <CardContent>
          <ol className="flex h-28 items-end gap-1" data-testid="week-chart">
            {weeks.map(([key, value]) => (
              <li
                key={key}
                className="flex flex-1 flex-col items-center justify-end gap-1"
                title={t("minutesOn", { minutes: value, week: key })}
              >
                <span
                  className={cn("w-full rounded-t", value > 0 ? "bg-primary" : "bg-muted")}
                  style={{ height: `${Math.max(2, (value / tallest) * 100)}%` }}
                />
              </li>
            ))}
          </ol>
          <p className="text-muted-foreground mt-2 text-xs">{t("chartHint")}</p>
        </CardContent>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("goals")}</CardTitle>
            <p className="text-muted-foreground text-xs">{t("goalsHint")}</p>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {GOAL_TYPES.map((type) => {
              const goal = goals.find((item) => item.type === type);
              return (
                <GoalRow
                  key={type}
                  type={type}
                  goal={goal}
                  busy={busy}
                  onSet={(target) => setGoal(type, target)}
                />
              );
            })}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">{t("addActivity")}</CardTitle>
            <p className="text-muted-foreground text-xs">{t("addActivityHint")}</p>
          </CardHeader>
          <CardContent className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="activity-minutes">{t("minutesLabel")}</Label>
              <Input
                id="activity-minutes"
                type="number"
                min={1}
                max={1440}
                value={minutes}
                onChange={(event) => setMinutes(event.target.value)}
                className="w-24"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="activity-sport">{t("sport")}</Label>
              <select
                id="activity-sport"
                value={sport}
                onChange={(event) => setSport(event.target.value)}
                className="border-input bg-background h-8 rounded-lg border px-2 text-sm"
              >
                <option value="">{t("otherExercise")}</option>
                {sports.map((item) => (
                  <option key={item.slug} value={item.slug}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex min-w-40 flex-1 flex-col gap-1.5">
              <Label htmlFor="activity-note">{t("note")}</Label>
              <Input
                id="activity-note"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder={t("notePlaceholder")}
              />
            </div>
            <Button size="sm" disabled={busy || !minutes} onClick={addActivity}>
              {t("add")}
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{t("history")}</CardTitle>
        </CardHeader>
        <CardContent>
          {logs.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("noActivity")}</p>
          ) : (
            <ul className="flex flex-col divide-y text-sm" data-testid="activity-history">
              {logs.map((log) => (
                <li key={String(log.id)} className="flex flex-wrap items-baseline gap-2 py-2">
                  <span className="font-mono text-xs tabular-nums">
                    {formatWhen(`${log.happened_on}T12:00:00+06:00`, locale, "dayMonth")}
                  </span>
                  <span className="min-w-0 flex-1 truncate">
                    {log.sport_name || t("otherExercise")}
                    {log.turf_name && (
                      <span className="text-muted-foreground"> · {log.turf_name}</span>
                    )}
                    {log.note && <span className="text-muted-foreground"> · {log.note}</span>}
                  </span>
                  <span className="font-mono tabular-nums">{log.minutes}m</span>
                  <span className="text-muted-foreground font-mono text-xs tabular-nums">
                    {log.est_calories} kcal
                  </span>
                  {log.is_estimate && (
                    <Badge variant="outline" className="text-[10px]">
                      {t("estimated")}
                    </Badge>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function GoalRow({
  type,
  goal,
  busy,
  onSet,
}: {
  type: string;
  goal?: GoalProgress;
  busy: boolean;
  onSet: (target: number) => void;
}) {
  const t = useTranslations("fitness");
  const [value, setValue] = useState(String(goal?.target ?? ""));

  return (
    <div className="flex flex-wrap items-end gap-2">
      <div className="flex min-w-32 flex-1 flex-col gap-1">
        <Label htmlFor={`goal-${type}`} className="text-xs">
          {t("goalType", { type })}
        </Label>
        {goal && (
          <span className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
            <span
              className="bg-primary block h-full rounded-full"
              style={{ width: `${goal.percent}%` }}
            />
          </span>
        )}
      </div>
      <Input
        id={`goal-${type}`}
        type="number"
        min={0}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        className="h-8 w-24"
      />
      <Button size="xs" disabled={busy} onClick={() => onSet(Number(value) || 0)}>
        {goal ? t("update") : t("set")}
      </Button>
    </div>
  );
}

/** The Saturday that starts the Dhaka week containing `day` (DECISIONS D56). */
function weekKey(day: Date): string {
  const dhaka = new Date(day.getTime());
  const weekday = dhaka.getUTCDay(); // 0 = Sunday … 6 = Saturday
  const back = (weekday + 1) % 7; // days since the most recent Saturday
  const start = new Date(dhaka.getTime() - back * 86_400_000);
  return start.toISOString().slice(0, 10);
}
