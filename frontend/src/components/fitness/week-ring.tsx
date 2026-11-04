import { getTranslations } from "next-intl/server";
import { cn } from "cn";

/**
 * The week's progress as a ring.
 *
 * An inline SVG rather than a chart library: it is one arc, and a dependency for one arc
 * is a dependency for nothing.
 */
export async function WeekRing({
  percent,
  label,
  sublabel,
}: {
  percent: number;
  label: string;
  sublabel?: string;
}) {
  const t = await getTranslations("fitness");
  const clamped = Math.max(0, Math.min(100, percent));
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const filled = (clamped / 100) * circumference;

  return (
    <div className="flex items-center gap-4">
      <svg
        viewBox="0 0 100 100"
        className="size-24 -rotate-90"
        role="img"
        aria-label={t("ringLabel", { percent: clamped })}
      >
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          strokeWidth="8"
          className="text-muted stroke-current"
        />
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference - filled}`}
          className={cn(
            "stroke-current transition-[stroke-dasharray]",
            clamped >= 100 ? "text-emerald-500" : "text-primary",
          )}
        />
      </svg>

      <div className="min-w-0">
        <p className="font-mono text-2xl font-bold tabular-nums">{label}</p>
        {sublabel && <p className="text-muted-foreground text-sm">{sublabel}</p>}
      </div>
    </div>
  );
}
