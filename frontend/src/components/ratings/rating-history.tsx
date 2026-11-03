import { getTranslations } from "next-intl/server";
import { cn } from "cn";

import type { RatingChange } from "@/lib/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * The rating line, and what moved it.
 *
 * Drawn as an inline SVG rather than with a charting library: it is one series of at
 * most twenty points, and a chart library would be the heaviest thing on the page.
 */
export async function RatingHistory({ changes }: { changes: RatingChange[] }) {
  const t = await getTranslations("ratingHistory");
  if (changes.length === 0) return null;

  // Oldest first for the line; the list underneath stays newest-first.
  const series = [...changes].reverse();
  const values = series.map((change) => change.after_overall);
  const low = Math.max(1, Math.min(...values) - 3);
  const high = Math.min(99, Math.max(...values) + 3);
  const span = Math.max(1, high - low);

  const points = series.map((change, index) => {
    const x = series.length === 1 ? 50 : (index / (series.length - 1)) * 100;
    const y = 100 - ((change.after_overall - low) / span) * 100;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });

  return (
    <Card className="w-full max-w-xl" data-testid="rating-history">
      <CardHeader>
        <CardTitle className="text-sm">{t("heading")}</CardTitle>
        <p className="text-muted-foreground text-xs">{t("hint")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {/* One point is not a line: the list below says everything a single match has
            to say, and an empty chart box says nothing. */}
        {series.length > 1 && (
          <svg
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            className="h-24 w-full"
            role="img"
            aria-label={t("chartLabel", { from: values[0], to: values[values.length - 1] })}
          >
            <polyline
              points={points.join(" ")}
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              vectorEffect="non-scaling-stroke"
              className="text-primary"
            />
          </svg>
        )}

        <ol className="flex flex-col divide-y text-sm">
          {changes.map((change) => (
            <li key={String(change.id)} className="flex flex-col gap-1 py-2">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate">
                  {change.turf_name}
                  <span className="text-muted-foreground ml-1.5 text-xs">
                    {new Intl.DateTimeFormat("en-GB", {
                      timeZone: "Asia/Dhaka",
                      day: "numeric",
                      month: "short",
                    }).format(new Date(change.played_at))}
                  </span>
                </span>
                <span
                  className={cn(
                    "font-mono text-sm font-semibold tabular-nums",
                    change.delta > 0 && "text-emerald-600 dark:text-emerald-400",
                    change.delta < 0 && "text-destructive",
                  )}
                >
                  {change.delta > 0 ? "+" : ""}
                  {change.delta}
                </span>
              </div>
              <Why breakdown={change.breakdown} t={t} />
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}

type Translator = Awaited<ReturnType<typeof getTranslations<"ratingHistory">>>;

/** The engine's own explanation, in the words it stored. */
function Why({ breakdown, t }: { breakdown: unknown; t: Translator }) {
  if (!breakdown || typeof breakdown !== "object") return null;
  const data = breakdown as Record<string, unknown>;
  const components = (data.components ?? {}) as Record<string, string>;

  const parts: string[] = [];
  // Named one by one rather than through a computed key: next-intl types its keys, and
  // the three components the engine produces are a closed set.
  for (const [name, raw] of Object.entries(components)) {
    const value = Math.round(Number(raw));
    if (name === "stats") parts.push(t("component.stats", { value }));
    else if (name === "result") parts.push(t("component.result", { value }));
    else if (name === "peers") parts.push(t("component.peers", { value }));
  }
  if (Number(data.motm_bonus ?? 0) > 0) parts.push(t("motm"));
  if (Number(data.card_penalty ?? 0) > 0) {
    parts.push(t("cards", { points: Math.round(Number(data.card_penalty)) }));
  }
  if (data.verified_multiplier && Number(data.verified_multiplier) > 1) parts.push(t("verified"));
  if (data.provisional) parts.push(t("provisional"));

  if (parts.length === 0) return null;
  return <p className="text-muted-foreground text-xs">{parts.join(" · ")}</p>;
}
