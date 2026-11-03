import { cn } from "cn";

/**
 * Colour band for a 1–99 rating.
 *
 * Deliberately coarse — four bands read at a glance on a crowded match board, where a
 * continuous gradient would not. Tailwind classes are spelled out in full because the
 * JIT compiler cannot see interpolated class names.
 */
export function ratingTone(value: number): string {
  if (value >= 80) return "text-emerald-600 dark:text-emerald-400";
  if (value >= 65) return "text-lime-600 dark:text-lime-400";
  if (value >= 50) return "text-amber-600 dark:text-amber-400";
  return "text-muted-foreground";
}

function barTone(value: number): string {
  if (value >= 80) return "bg-emerald-500";
  if (value >= 65) return "bg-lime-500";
  if (value >= 50) return "bg-amber-500";
  return "bg-muted-foreground/50";
}

/** One labelled 1–99 bar, used for both skills and shared attributes. */
export function RatingBar({
  label,
  value,
  className,
}: {
  label: string;
  value: number;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <span className="text-muted-foreground w-24 shrink-0 truncate text-xs" title={label}>
        {label}
      </span>
      <div
        className="bg-muted h-1.5 flex-1 overflow-hidden rounded-full"
        role="meter"
        aria-label={label}
        aria-valuenow={value}
        aria-valuemin={1}
        aria-valuemax={99}
      >
        <div
          className={cn("h-full rounded-full transition-all", barTone(value))}
          style={{ width: `${value}%` }}
        />
      </div>
      <span className="w-6 shrink-0 text-right font-mono text-xs tabular-nums">{value}</span>
    </div>
  );
}
